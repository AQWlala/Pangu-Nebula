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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.terminal_service import TerminalService

router = APIRouter(prefix="/terminal", tags=["terminal"])

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


@router.get("")
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


@router.get("/status")
async def terminal_status():
    """获取终端服务状态(静态路由在前)"""
    return {"ok": True, "data": _terminal.get_status(), "error": None}


@router.get("/sessions")
async def list_sessions():
    """列出活跃会话(静态路由在前)"""
    sessions = await _terminal.list_sessions()
    return {"ok": True, "data": sessions, "error": None}


@router.post("/session")
async def create_session(req: SessionCreateRequest):
    """创建终端会话"""
    result = await _terminal.create_session(shell=req.shell, cols=req.cols, rows=req.rows)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/{session_id}/write")
async def write_to_session(session_id: str, req: WriteRequest):
    """向终端会话写入数据"""
    result = await _terminal.write(session_id, req.data)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/{session_id}/read")
async def read_from_session(session_id: str, timeout: float = 1.0):
    """读取终端会话输出"""
    result = await _terminal.read(session_id, timeout=timeout)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/{session_id}/resize")
async def resize_session(session_id: str, req: ResizeRequest):
    """调整终端会话大小"""
    result = await _terminal.resize(session_id, req.cols, req.rows)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.delete("/{session_id}")
async def close_session(session_id: str):
    """关闭终端会话"""
    result = await _terminal.close_session(session_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result
