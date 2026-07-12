"""MCP API 端点 (Phase 10A)

提供 MCP 客户端(连接外部 MCP 服务器)和服务端(暴露内部工具)的 REST API。

端点总览:
- GET    /mcp                       - 模块信息
- GET    /mcp/servers               - 列出已连接的 MCP 客户端服务器
- POST   /mcp/servers               - 连接新 MCP 服务器
- GET    /mcp/tools                 - 列出本机 MCP 服务端注册的工具
- POST   /mcp/tools                 - 注册新工具
- POST   /mcp/rpc                   - JSON-RPC 入口
- DELETE /mcp/servers/{name}        - 断开 MCP 服务器
- GET    /mcp/servers/{name}        - 获取服务器信息
- GET    /mcp/servers/{name}/tools  - 列出服务器工具
- POST   /mcp/servers/{name}/call   - 调用服务器工具
- DELETE /mcp/tools/{tool_name}     - 注销工具

路由顺序注意: 静态路径(servers, tools, rpc)必须在动态路径
(servers/{name}, tools/{tool_name})之前注册。
"""

from fastapi import APIRouter, HTTPException

from ..services.mcp_client import mcp_client
from ..services.mcp_server import mcp_server
from .models_mcp import McpCallToolRequest, McpConnectRequest, McpRegisterToolRequest

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ===== 模块信息 =====


@router.get("", summary="MCP 模块信息", description="获取 MCP 模块信息,包括已连接服务器数和已注册工具数")
async def get_mcp():
    """获取 MCP 模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "mcp",
            "phase": "10A",
            "features": ["mcp_client", "mcp_server", "json_rpc"],
            "connected_servers": len(mcp_client.list_servers()),
            "registered_tools": len(mcp_server.list_tools()),
        },
        "error": None,
    }


# ===== 静态路径: 服务器管理 =====


@router.get("/servers", summary="列出 MCP 服务器", description="列出已连接的 MCP 客户端服务器")
async def list_servers():
    """列出已连接的 MCP 客户端服务器"""
    return {"ok": True, "data": mcp_client.list_servers(), "error": None}


@router.post("/servers", summary="连接 MCP 服务器", description="连接新 MCP 服务器(启动子进程并执行 initialize 握手)")
async def connect_server(req: McpConnectRequest):
    """连接新 MCP 服务器(启动子进程并执行 initialize 握手)"""
    try:
        result = await mcp_client.connect_server(
            name=req.name, command=req.command, args=req.args, env=req.env
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


# ===== 静态路径: 本机工具管理 =====


@router.get("/tools")
async def list_tools():
    """列出本机 MCP 服务端注册的工具"""
    return {"ok": True, "data": mcp_server.list_tools(), "error": None}


@router.post("/tools")
async def register_tool(req: McpRegisterToolRequest):
    """注册新工具(handler_code 暂不执行,使用占位 handler)"""
    try:
        # handler_code 暂不动态执行,使用占位 handler 返回提示
        async def _placeholder(**kwargs):
            return f"工具 '{req.name}' 已注册,但 handler_code 尚未实现"

        result = mcp_server.register_tool(
            name=req.name,
            description=req.description,
            input_schema=req.input_schema,
            handler=_placeholder,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


# ===== 静态路径: JSON-RPC 入口 =====


@router.post("/rpc")
async def rpc_endpoint(body: dict):
    """JSON-RPC 入口,调用 mcp_server.handle_request 处理原始请求"""
    try:
        response = await mcp_server.handle_request(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": response, "error": None}


# ===== 动态路径: 服务器操作(静态路径在前) =====


@router.delete("/servers/{name}")
async def disconnect_server(name: str):
    """断开 MCP 服务器,终止子进程"""
    try:
        result = await mcp_client.disconnect_server(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/servers/{name}")
async def get_server(name: str):
    """获取服务器信息"""
    try:
        result = mcp_client.get_server_info(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/servers/{name}/tools")
async def list_server_tools(name: str):
    """列出指定服务器的工具(tools/list)"""
    try:
        result = await mcp_client.list_tools(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.post("/servers/{name}/call")
async def call_server_tool(name: str, req: McpCallToolRequest):
    """调用指定服务器的工具(tools/call)"""
    try:
        result = await mcp_client.call_tool(name, req.tool_name, req.arguments)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


# ===== 动态路径: 工具操作 =====


@router.delete("/tools/{tool_name}")
async def unregister_tool(tool_name: str):
    """注销工具"""
    try:
        result = mcp_server.unregister_tool(tool_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}
