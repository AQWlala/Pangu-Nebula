"""MCP API 端点 (Phase 10A)

提供 MCP 客户端(连接外部 MCP 服务器)和服务端(暴露内部工具)的 REST API。

端点总览:
- GET    /mcp                            - 模块信息
- GET    /mcp/servers                    - 列出已连接的 MCP 客户端服务器
- POST   /mcp/servers                    - 连接新 MCP 服务器 (含 transport 字段)
- GET    /mcp/tools                      - 列出本机 MCP 服务端注册的工具
- POST   /mcp/tools                      - 注册新工具
- POST   /mcp/rpc                        - JSON-RPC 入口
- DELETE /mcp/servers/{name}             - 断开 MCP 服务器
- GET    /mcp/servers/{name}             - 获取服务器信息
- GET    /mcp/servers/{name}/tools       - 列出服务器工具
- POST   /mcp/servers/{name}/call        - 调用服务器工具
- GET    /mcp/servers/{name}/health      - MCP 服务器健康检查 (Phase 3-C)
- GET    /mcp/servers/{name}/security-audit - MCP 安全审计 (Phase 3-C)
- DELETE /mcp/tools/{tool_name}          - 注销工具
- GET    /mcp/marketplace/search         - 搜索 MCP 市场 (Phase 3-C)
- POST   /mcp/marketplace/install        - 安装 MCP 服务器 (Phase 3-C)

路由顺序注意: 静态路径(servers, tools, rpc, marketplace)必须在动态路径
(servers/{name}, tools/{tool_name})之前注册。
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.event_bus import get_event_bus
from ..services.mcp_client import mcp_client
from ..services.mcp_marketplace import get_mcp_marketplace
from ..services.mcp_server import mcp_server
from .models_mcp import McpCallToolRequest, McpConnectRequest, McpRegisterToolRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ===== v2.3.0 Phase 3-C: MCP 事件发布 =====


async def _publish_mcp_connected(server_id: str, transport: str) -> None:
    """发布 mcp.connected 事件 (异常吞掉, 不阻断连接主流程)"""
    try:
        bus = get_event_bus()
        await bus.publish(
            "mcp.connected",
            {"server_id": server_id, "transport": transport},
            source="mcp_api",
        )
    except Exception:
        logger.debug("publish mcp.connected 失败 server_id=%s", server_id, exc_info=True)


async def _publish_mcp_disconnected(server_id: str) -> None:
    """发布 mcp.disconnected 事件 (异常吞掉)"""
    try:
        bus = get_event_bus()
        await bus.publish(
            "mcp.disconnected",
            {"server_id": server_id},
            source="mcp_api",
        )
    except Exception:
        logger.debug("publish mcp.disconnected 失败 server_id=%s", server_id, exc_info=True)


# ===== Phase 3-C: MCP 市场化请求模型 =====


class McpMarketplaceInstallRequest(BaseModel):
    """MCP 市场安装请求"""

    server_name: str = Field(..., description="服务器名称 (Smithery 索引中的 name)")
    transport: str = Field(default="stdio", description="传输类型: stdio/sse")
    config: dict = Field(default={}, description="安装配置 (command/args/env for stdio, url for sse)")


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


@router.post("/servers", summary="连接 MCP 服务器", description="连接新 MCP 服务器(启动子进程并执行 initialize 握手, 支持 transport 字段)")
async def connect_server(req: McpConnectRequest):
    """连接新 MCP 服务器(启动子进程并执行 initialize 握手)

    Phase 3-C: 接收 transport 字段 (stdio/sse)。当前 MCPClient 仅实现 stdio,
    sse 为占位 (后续扩展)。连接成功后发布 mcp.connected 事件。
    """
    # sse 传输暂未实现, 显式拒绝以避免静默错误
    if req.transport == "sse":
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": "sse 传输暂未实现 (占位), 请使用 stdio"},
        )
    try:
        result = await mcp_client.connect_server(
            name=req.name, command=req.command, args=req.args, env=req.env
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    # Phase 3-C: 发布 mcp.connected 事件 (前端 store 监听以更新 skillsMcp.mcpServers)
    await _publish_mcp_connected(req.name, req.transport)
    # 将 transport 写入返回结果 (前端可据此区分 stdio/sse)
    result["transport"] = req.transport
    return {"ok": True, "data": result, "error": None}


# ===== 静态路径: 本机工具管理 =====


@router.get("/tools", summary="列出本机 MCP 工具", description="列出本机 MCP 服务端注册的所有工具")
async def list_tools():
    """列出本机 MCP 服务端注册的工具"""
    return {"ok": True, "data": mcp_server.list_tools(), "error": None}


@router.post("/tools", summary="注册 MCP 工具", description="注册新工具到本机 MCP 服务端 (handler_code 暂不执行,使用占位 handler)")
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


@router.post("/rpc", summary="MCP JSON-RPC 入口", description="JSON-RPC 入口,调用 mcp_server.handle_request 处理原始请求")
async def rpc_endpoint(body: dict):
    """JSON-RPC 入口,调用 mcp_server.handle_request 处理原始请求"""
    try:
        response = await mcp_server.handle_request(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": response, "error": None}


# ===== 静态路径: Phase 3-C MCP 市场 (Smithery 索引) =====


@router.get("/marketplace/search", summary="搜索 MCP 市场", description="搜索 MCP 服务器市场 (Smithery 索引)")
async def search_mcp_marketplace(
    q: str = Query(default="", description="搜索关键词"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量上限"),
):
    """搜索 MCP 服务器市场 (调 mcp_marketplace)"""
    marketplace = get_mcp_marketplace()
    results = await marketplace.search_servers(query=q, limit=limit)
    return {
        "ok": True,
        "data": {"query": q, "count": len(results), "servers": results},
        "error": None,
    }


@router.post("/marketplace/install", summary="安装 MCP 服务器", description="从 MCP 市场安装服务器 (含 transport 字段)")
async def install_mcp_from_marketplace(req: McpMarketplaceInstallRequest):
    """从 MCP 市场安装服务器 (调 mcp_marketplace)

    含 transport 字段 (stdio/sse)。安装成功后应发布 mcp.connected 事件。
    """
    marketplace = get_mcp_marketplace()
    result = await marketplace.install_server(
        server_name=req.server_name,
        transport=req.transport,
        config=req.config,
    )
    if not result.get("success", False):
        return {"ok": False, "data": result, "error": result.get("error")}
    # 安装成功后发布 mcp.connected 事件 (若 marketplace 返回了 server_id 则用之)
    server_id = result.get("server_id") or req.server_name
    await _publish_mcp_connected(server_id, req.transport)
    return {"ok": True, "data": result, "error": None}


# ===== 动态路径: 服务器操作(静态路径在前) =====


@router.delete("/servers/{name}", summary="断开 MCP 服务器", description="断开 MCP 服务器连接,终止子进程,发布 mcp.disconnected 事件")
async def disconnect_server(name: str):
    """断开 MCP 服务器,终止子进程"""
    try:
        result = await mcp_client.disconnect_server(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    # Phase 3-C: 发布 mcp.disconnected 事件
    await _publish_mcp_disconnected(name)
    return {"ok": True, "data": result, "error": None}


@router.get("/servers/{name}", summary="获取 MCP 服务器信息", description="获取指定 MCP 服务器的连接信息和状态")
async def get_server(name: str):
    """获取服务器信息"""
    try:
        result = mcp_client.get_server_info(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/servers/{name}/tools", summary="列出服务器工具", description="列出指定 MCP 服务器注册的所有工具 (tools/list)")
async def list_server_tools(name: str):
    """列出指定服务器的工具(tools/list)"""
    try:
        result = await mcp_client.list_tools(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.post("/servers/{name}/call", summary="调用服务器工具", description="调用指定 MCP 服务器的工具 (tools/call)")
async def call_server_tool(name: str, req: McpCallToolRequest):
    """调用指定服务器的工具(tools/call)"""
    try:
        result = await mcp_client.call_tool(name, req.tool_name, req.arguments)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


# ===== Phase 3-C: MCP 健康检查 + 安全审计 =====


@router.get("/servers/{name}/health", summary="MCP 服务器健康检查", description="对指定 MCP 服务器执行健康检查 (调 mcp_marketplace)")
async def check_server_health(name: str):
    """MCP 服务器健康检查"""
    marketplace = get_mcp_marketplace()
    result = await marketplace.health_check(server_id=name)
    return {"ok": True, "data": result, "error": None}


@router.get("/servers/{name}/security-audit", summary="MCP 安全审计", description="对指定 MCP 服务器执行安全审计 (prompt injection + 命令白名单)")
async def audit_server_security(name: str):
    """MCP 安全审计 (prompt injection 检测 + 命令白名单)"""
    marketplace = get_mcp_marketplace()
    result = await marketplace.security_audit(server_id=name)
    return {"ok": True, "data": result, "error": None}


# ===== 动态路径: 工具操作 =====


@router.delete("/tools/{tool_name}", summary="注销 MCP 工具", description="从本机 MCP 服务端注销指定工具")
async def unregister_tool(tool_name: str):
    """注销工具"""
    try:
        result = mcp_server.unregister_tool(tool_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}
