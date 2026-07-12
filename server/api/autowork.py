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


@router.get("")
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


@router.post("")
async def create_session(req: AutoWorkCreate, session: AsyncSession = Depends(get_session)):
    data = await _service.create_session(
        session, req.title, req.description, req.config
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/list")
async def list_sessions(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    data = await _service.list_sessions(session, status=status)
    return {"ok": True, "data": data, "error": None}


@router.get("/kanban")
async def get_kanban(session: AsyncSession = Depends(get_session)):
    data = await _service.get_kanban(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/{session_id}")
async def get_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.get_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/claim")
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


@router.post("/{session_id}/complete")
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


@router.post("/{session_id}/fail")
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


@router.post("/{session_id}/pause")
async def pause_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.pause_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/resume")
async def resume_session(session_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.resume_session(session, session_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Session not found"},
        )
    return {"ok": True, "data": data, "error": None}
