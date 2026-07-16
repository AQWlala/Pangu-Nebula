"""终端模式 API (T5.7)

提供 PTY/CLI 终端会话管理:
- 创建/关闭终端会话
- 向终端写入命令
- 读取终端输出
- 调整终端大小
- 列出活跃会话

所有端点返回统一格式 {"ok", "data", "error"}。
依赖 ptyprocess/winpty 可选,缺失时自动降级为 mock 模式。
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..services.terminal_service import TerminalService


def verify_terminal_access(request: Request) -> None:
    """F2: 路由级鉴权依赖(纵深防御)

    检查 Authorization Bearer token 是否匹配 sidecar_token。
    - pywebview 模式(sidecar_token 为空): 允许访问(向后兼容)
    - tauri 模式(sidecar_token 已设置): 要求有效 Bearer token

    即使 sidecar_token_auth middleware 被绕过或移除,此依赖仍提供保护。
    鉴权失败返回 401。
    """
    from ..main import settings

    token = settings.sidecar_token
    if not token:
        # pywebview 模式: 无 token 配置,允许访问
        return
    # tauri 模式: 验证 Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if secrets.compare_digest(provided, token):
            return
    raise HTTPException(
        status_code=401,
        detail={
            "ok": False,
            "data": None,
            "error": "Unauthorized: invalid or missing Bearer token",
        },
    )


router = APIRouter(
    prefix="/terminal",
    tags=["terminal"],
    dependencies=[Depends(verify_terminal_access)],
)

_terminal = TerminalService()


class SessionCreateRequest(BaseModel):
    """创建终端会话请求"""

    shell: str = "powershell"
    cols: int = 80
    rows: int = 24


class WriteRequest(BaseModel):
    """向终端写入数据请求"""

    data: str


class ResizeRequest(BaseModel):
    """调整终端大小请求"""

    cols: int = 80
    rows: int = 24


@router.get("", summary="终端模块信息", description="返回 PTY/CLI 终端模式服务的模块信息和端点列表")
async def terminal_info():
    """终端模块信息(静态路由在前)"""
    return {
        "ok": True,
        "data": {
            "name": "terminal",
            "description": "PTY/CLI 终端模式服务",
            "endpoints": [
                "GET /terminal",
                "GET /terminal/status",
                "POST /terminal/session",
                "POST /terminal/{session_id}/write",
                "GET /terminal/{session_id}/read",
                "POST /terminal/{session_id}/resize",
                "DELETE /terminal/{session_id}",
                "GET /terminal/sessions",
            ],
        },
        "error": None,
    }


@router.get("/status", summary="终端服务状态", description="获取终端服务状态(包括 ptyprocess/winpty 可用性)")
async def terminal_status():
    """获取终端服务状态(静态路由在前)"""
    return {"ok": True, "data": _terminal.get_status(), "error": None}


@router.get("/sessions", summary="列出活跃会话", description="列出当前所有活跃的终端会话")
async def list_sessions():
    """列出活跃会话(静态路由在前)"""
    sessions = await _terminal.list_sessions()
    return {"ok": True, "data": sessions, "error": None}


@router.post("/session", summary="创建终端会话", description="创建一个新的终端会话,可指定 shell 类型、列数和行数")
async def create_session(req: SessionCreateRequest):
    """创建终端会话"""
    result = await _terminal.create_session(shell=req.shell, cols=req.cols, rows=req.rows)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/{session_id}/write", summary="写入终端", description="向指定终端会话写入数据(命令、按键等)")
async def write_to_session(session_id: str, req: WriteRequest):
    """向终端会话写入数据"""
    result = await _terminal.write(session_id, req.data)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/{session_id}/read", summary="读取终端输出", description="读取指定终端会话的输出,可设置超时时间")
async def read_from_session(session_id: str, timeout: float = 1.0):
    """读取终端会话输出"""
    result = await _terminal.read(session_id, timeout=timeout)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/{session_id}/resize", summary="调整终端大小", description="调整指定终端会话的列数和行数")
async def resize_session(session_id: str, req: ResizeRequest):
    """调整终端会话大小"""
    result = await _terminal.resize(session_id, req.cols, req.rows)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.delete("/{session_id}", summary="关闭终端会话", description="关闭指定的终端会话")
async def close_session(session_id: str):
    """关闭终端会话"""
    result = await _terminal.close_session(session_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result
