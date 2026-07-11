"""MCP 客户端 (Phase 10A)

实现 JSON-RPC 2.0 over stdio 的 MCP 客户端,通过 subprocess 启动外部 MCP 服务器进程,
使用 stdin/stdout 进行通信。

通信协议:
- 每条 JSON-RPC 消息以换行符分隔(NDJSON)
- 请求格式: {"jsonrpc": "2.0", "id": <int>, "method": "...", "params": {...}}
- 响应格式: {"jsonrpc": "2.0", "id": <int>, "result": {...}}
           或 {"jsonrpc": "2.0", "id": <int>, "error": {"code": ..., "message": ...}}

模块级单例: `mcp_client = MCPClient()`
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any


class _ServerConnection:
    """单个 MCP 服务器连接的运行时状态(非持久化)"""

    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str]):
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.process: asyncio.subprocess.Process | None = None
        self.server_info: dict[str, Any] = {}
        self.connected = False


class MCPClient:
    """MCP 客户端,管理多个 MCP 服务器连接

    通过 asyncio.create_subprocess_exec 启动 MCP 服务器进程,
    使用 JSON-RPC 2.0 协议 over stdin/stdout 通信。
    所有方法均为 async,超时默认 30 秒。
    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(self):
        self._servers: dict[str, _ServerConnection] = {}
        self._request_id = 0

    def _next_id(self) -> int:
        """生成递增的请求 id"""
        self._request_id += 1
        return self._request_id

    async def _send_request(
        self, process: asyncio.subprocess.Process, method: str, params: dict | None = None
    ) -> dict[str, Any]:
        """发送 JSON-RPC 2.0 请求并等待响应

        将请求序列化为 JSON 并写入进程 stdin,然后读取 stdout 响应。
        """
        request_id = self._next_id()
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        payload = json.dumps(request) + "\n"
        if process.stdin is None:
            raise RuntimeError("进程 stdin 不可用")
        process.stdin.write(payload.encode("utf-8"))
        await process.stdin.drain()

        response = await self._read_response(process)
        if response.get("id") != request_id:
            raise RuntimeError(
                f"响应 id 不匹配: 期望 {request_id}, 收到 {response.get('id')}"
            )
        if "error" in response:
            err = response["error"]
            raise RuntimeError(f"MCP 错误 [{err.get('code')}]: {err.get('message')}")
        return response.get("result", {})

    async def _read_response(self, process: asyncio.subprocess.Process) -> dict[str, Any]:
        """从进程 stdout 读取一行 JSON-RPC 响应(跳过无 id 的通知消息)"""
        if process.stdout is None:
            raise RuntimeError("进程 stdout 不可用")
        while True:
            line = await process.stdout.readline()
            if not line:
                raise RuntimeError("MCP 服务器已关闭连接")
            msg = json.loads(line.decode("utf-8").strip())
            # 跳过通知(无 id 的消息),只返回带 id 的响应
            if "id" in msg:
                return msg

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        """终止子进程:先 terminate,超时后 kill"""
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass

    def _get_connection(self, name: str) -> _ServerConnection:
        """获取已连接的服务器,未连接时抛出 ValueError"""
        if name not in self._servers:
            raise ValueError(f"服务器 '{name}' 未连接")
        conn = self._servers[name]
        if not conn.connected or conn.process is None:
            raise RuntimeError(f"服务器 '{name}' 连接已断开")
        return conn

    async def connect_server(
        self, name: str, command: str, args: list[str] | None = None, env: dict | None = None
    ) -> dict[str, Any]:
        """连接 MCP 服务器:启动子进程并执行 initialize 握手

        Args:
            name: 服务器名称(唯一标识)
            command: 可执行命令路径
            args: 命令参数列表
            env: 额外环境变量(与当前环境合并)

        Returns:
            连接信息字典,包含 name/command/args/connected/server_info
        """
        if name in self._servers and self._servers[name].connected:
            raise ValueError(f"服务器 '{name}' 已连接")

        args = args or []
        env = env or {}

        # 合并环境变量:当前环境 + 额外变量
        if env:
            full_env = dict(os.environ)
            full_env.update({k: str(v) for k, v in env.items()})
            env_arg: dict[str, str] | None = full_env
        else:
            env_arg = None

        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_arg,
        )

        conn = _ServerConnection(name, command, args, env)
        conn.process = process
        self._servers[name] = conn

        try:
            # 执行 MCP initialize 握手
            result = await asyncio.wait_for(
                self._send_request(
                    process,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "pangu-nebula", "version": "1.0.0"},
                    },
                ),
                timeout=self.DEFAULT_TIMEOUT,
            )
            conn.server_info = result
            # 发送 initialized 通知(无 id,无需等待响应)
            if process.stdin is not None:
                notification = json.dumps(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                ) + "\n"
                process.stdin.write(notification.encode("utf-8"))
                await process.stdin.drain()
            conn.connected = True
        except Exception:
            # 握手失败,清理进程与记录
            await self._terminate(process)
            del self._servers[name]
            raise

        return {
            "name": name,
            "command": command,
            "args": args,
            "connected": True,
            "server_info": conn.server_info,
        }

    async def disconnect_server(self, name: str) -> dict[str, Any]:
        """断开 MCP 服务器连接,终止子进程"""
        if name not in self._servers:
            raise ValueError(f"服务器 '{name}' 未连接")
        conn = self._servers[name]
        if conn.process:
            await self._terminate(conn.process)
        del self._servers[name]
        return {"name": name, "disconnected": True}

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """调用 MCP 服务器的 tools/list 方法,返回工具列表"""
        conn = self._get_connection(server_name)
        result = await asyncio.wait_for(
            self._send_request(conn.process, "tools/list", {}),
            timeout=self.DEFAULT_TIMEOUT,
        )
        return result.get("tools", [])

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict | None = None
    ) -> dict[str, Any]:
        """调用 MCP 服务器的 tools/call 方法

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            MCP 标准响应,通常为 {content: [{type: "text", text: ...}]}
        """
        conn = self._get_connection(server_name)
        result = await asyncio.wait_for(
            self._send_request(
                conn.process,
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
            ),
            timeout=self.DEFAULT_TIMEOUT,
        )
        return result

    def list_servers(self) -> list[dict[str, Any]]:
        """列出已连接的 MCP 服务器"""
        return [
            {
                "name": conn.name,
                "command": conn.command,
                "args": conn.args,
                "connected": conn.connected,
                "server_info": conn.server_info,
            }
            for conn in self._servers.values()
        ]

    def get_server_info(self, name: str) -> dict[str, Any]:
        """获取单个服务器信息"""
        if name not in self._servers:
            raise ValueError(f"服务器 '{name}' 未连接")
        conn = self._servers[name]
        return {
            "name": conn.name,
            "command": conn.command,
            "args": conn.args,
            "connected": conn.connected,
            "server_info": conn.server_info,
        }


mcp_client = MCPClient()
