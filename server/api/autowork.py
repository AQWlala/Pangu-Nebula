from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services.autowork_service import AutoWorkService

router = APIRouter(prefix="/autowork", tags=["autowork"])
_service = AutoWorkService()


class AutoWorkCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 0
    config: dict = {}


class AutoWorkClaim(BaseModel):
    assigned_to: str


class AutoWorkComplete(BaseModel):
    result: str


class AutoWorkFail(BaseModel):
    error: str


@router.get("", summary="AutoWork 模块信息", description="返回无人值守任务框架的模块信息和端点列表")
async def module_info():
    return {
        "ok": True,
        "data": {
            "module": "autowork",
            "description": "无人值守任务框架",
            "endpoints": [
                "POST /autowork", "GET /autowork/list", "GET /autowork/kanban",
                "GET /autowork/{id}", "POST /autowork/{id}/claim",
                "POST /autowork/{id}/complete", "POST /autowork/{id}/fail",
                "POST /autowork/{id}/pause", "POST /autowork/{id}/resume",
            ],
        },
        "error": None,
    }


@router.post("", summary="创建无人值守任务", description="创建一个新的无人值守任务会话,包含标题、描述、优先级和配置")
async def create_session(req: AutoWorkCreate, session: AsyncSession = Depends(get_session)):
    data = await _service.create_session(
        session, req.title, req.description, req.config
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/list", summary="列出任务会话", description="按状态过滤并列出所有任务会话")
async def list_sessions(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    data = await _service.list_sessions(session, status=status)
    return {"ok": True, "data": data, "error": None}


@router.get("/kanban", summary="获取看板视图", description="返回按状态分组的看板视图数据")
async def get_kanban(session: AsyncSession = Depends(get_session)):
    data = await _service.get_kanban(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/{session_id}", summary="获取任务会话", description="根据 ID 获取单个任务会话详情")
async def get_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.get_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/claim", summary="认领任务", description="将任务会话分配给指定执行者")
async def claim_session(
    session_id: int, req: AutoWorkClaim, session: AsyncSession = Depends(get_session)
):
    data = await _service.claim_session(session, session_id, req.assigned_to)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/complete", summary="完成任务", description="标记任务会话为已完成,并提交结果")
async def complete_session(
    session_id: int, req: AutoWorkComplete, session: AsyncSession = Depends(get_session)
):
    data = await _service.complete_session(session, session_id, req.result)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/fail", summary="标记任务失败", description="标记任务会话为失败,并提交错误信息")
async def fail_session(
    session_id: int, req: AutoWorkFail, session: AsyncSession = Depends(get_session)
):
    data = await _service.fail_session(session, session_id, req.error)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/pause", summary="暂停任务", description="将任务会话状态置为暂停")
async def pause_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.pause_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/resume", summary="恢复任务", description="将暂停的任务会话恢复执行")
async def resume_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.resume_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}
