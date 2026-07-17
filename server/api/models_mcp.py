"""Phase 10A: MCP Pydantic 请求模型

分离自 api/models.py,避免修改现有 models.py。
"""

from typing import Literal

from pydantic import BaseModel


class McpConnectRequest(BaseModel):
    """连接 MCP 服务器请求"""

    name: str
    command: str
    args: list[str] = []
    env: dict = {}
    # v2.3.0 Phase 3-C: transport 字段 (前端已发送, 后端之前静默丢弃)
    # stdio: 子进程 + stdin/stdout (默认, 当前 MCPClient 实现)
    # sse:  HTTP+SSE 远程服务器 (占位, 后续扩展)
    transport: Literal["stdio", "sse"] = "stdio"


class McpCallToolRequest(BaseModel):
    """调用 MCP 工具请求"""

    tool_name: str
    arguments: dict = {}


class McpRegisterToolRequest(BaseModel):
    """注册 MCP 工具请求"""

    name: str
    description: str
    input_schema: dict = {}
    handler_code: str = ""
