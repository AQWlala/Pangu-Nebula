"""Phase 10A: MCP Pydantic 请求模型

分离自 api/models.py,避免修改现有 models.py。
"""

from pydantic import BaseModel


class McpConnectRequest(BaseModel):
    """连接 MCP 服务器请求"""

    name: str
    command: str
    args: list[str] = []
    env: dict = {}


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
