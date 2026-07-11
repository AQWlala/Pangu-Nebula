"""MCP 服务端 (Phase 10A)

将内部工具注册暴露给外部 Agent 调用,实现 JSON-RPC 2.0 协议。

支持的 JSON-RPC 方法:
- initialize: 返回协议版本、能力声明和服务器信息
- ping: 心跳检测
- tools/list: 列出所有已注册工具
- tools/call: 调用指定工具,返回 MCP 标准内容格式

模块级单例: `mcp_server = MCPServer()`
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable


ToolHandler = Callable[..., Awaitable[Any]]


class MCPServer:
    """MCP 服务端,将内部工具暴露给外部 Agent 调用

    工具以 (name, description, input_schema, handler) 四元组注册,
    handler 为 async 可调用对象,接收关键字参数并返回任意可序列化结果。
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "pangu-nebula"
    SERVER_VERSION = "1.0.0"

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_builtin_tools()

    # ------------------------------------------------------------------
    # 内置工具
    # ------------------------------------------------------------------

    def _register_builtin_tools(self) -> None:
        """注册内置工具:ping 和 list_providers"""
        self.register_tool(
            name="ping",
            description="健康检查工具,返回 pong",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=self._ping_handler,
        )
        self.register_tool(
            name="list_providers",
            description="列出所有已注册的 LLM 提供商及其能力",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=self._list_providers_handler,
        )

    async def _ping_handler(self, **kwargs: Any) -> str:
        """ping 工具处理器"""
        return "pong"

    async def _list_providers_handler(self, **kwargs: Any) -> str:
        """list_providers 工具处理器,调用 providers.registry.list_providers()"""
        # 延迟导入避免循环依赖
        from ..providers import registry

        providers = registry.list_providers()
        return json.dumps(providers, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 工具注册/注销
    # ------------------------------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: ToolHandler,
    ) -> dict[str, Any]:
        """注册工具

        Args:
            name: 工具名称(唯一)
            description: 工具描述
            input_schema: JSON Schema 格式的输入参数定义
            handler: async 工具处理函数

        Returns:
            注册结果字典
        """
        if name in self._tools:
            raise ValueError(f"工具 '{name}' 已注册")
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }
        return {"name": name, "registered": True}

    def unregister_tool(self, name: str) -> dict[str, Any]:
        """注销工具"""
        if name not in self._tools:
            raise ValueError(f"工具 '{name}' 未注册")
        del self._tools[name]
        return {"name": name, "unregistered": True}

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有已注册工具(不含 handler 内部字段)"""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in self._tools.values()
        ]

    def get_registered_tools(self) -> list[str]:
        """获取已注册工具名列表"""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # JSON-RPC 请求处理
    # ------------------------------------------------------------------

    async def handle_request(self, request: dict) -> dict[str, Any]:
        """处理 JSON-RPC 2.0 请求,返回响应

        支持方法: initialize, ping, tools/list, tools/call。
        未知方法返回 -32601 错误,内部异常返回 -32603 错误。
        """
        method = request.get("method", "")
        request_id = request.get("id")
        params = request.get("params", {}) or {}

        try:
            if method == "initialize":
                result: dict[str, Any] = {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION,
                    },
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {}) or {}
                result = await self._call_tool(tool_name, arguments)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"未知方法: {method}"},
                }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict[str, Any]:
        """调用工具 handler 并返回 MCP 标准 content 格式

        返回: {content: [{type: "text", text: ...}]}
        """
        if tool_name not in self._tools:
            raise ValueError(f"工具 '{tool_name}' 未注册")
        handler = self._tools[tool_name]["handler"]
        output = await handler(**arguments)
        # 若 handler 已返回 MCP content 格式则直接返回
        if isinstance(output, dict) and "content" in output:
            return output
        # 统一转换为 MCP content 格式
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}]}


mcp_server = MCPServer()
