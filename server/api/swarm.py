import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services.swarm_service import SwarmService
from .models import SwarmCreate, SwarmUpdate

router = APIRouter(prefix="/swarm", tags=["swarm"])
_service = SwarmService()


@router.post("")
async def create_swarm(req: SwarmCreate, session: AsyncSession = Depends(get_session)):
    data = await _service.create_swarm(session, req.persona_id, req.goal, req.title)
    return {"ok": True, "data": data, "error": None}


@router.get("")
async def list_swarms(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    data = await _service.list_swarms(session, page, page_size)
    return {"ok": True, "data": data, "error": None}


@router.get("/{swarm_id}")
async def get_swarm(swarm_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.get_swarm(session, swarm_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Swarm not found"})
    return {"ok": True, "data": data, "error": None}


@router.put("/{swarm_id}")
async def update_swarm(
    swarm_id: int, req: SwarmUpdate, session: AsyncSession = Depends(get_session)
):
    data = await _service.update_swarm(session, swarm_id, **req.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Swarm not found"})
    return {"ok": True, "data": data, "error": None}


@router.delete("/{swarm_id}")
async def delete_swarm(swarm_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await _service.delete_swarm(session, swarm_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Swarm not found"})
    return {"ok": True, "data": {"id": swarm_id, "deleted": True}, "error": None}


@router.post("/{swarm_id}/run")
async def run_swarm(swarm_id: int, session: AsyncSession = Depends(get_session)):
    swarm = await _service.get_swarm(session, swarm_id)
    if swarm is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Swarm not found"})

    async def event_stream():
        async for event in _service.run_swarm(swarm_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{swarm_id}/cancel")
async def cancel_swarm(swarm_id: int, session: AsyncSession = Depends(get_session)):
    swarm = await _service.get_swarm(session, swarm_id)
    if swarm is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Swarm not found"})
    await _service.update_swarm_status(session, swarm_id, "cancelled")
    return {"ok": True, "data": {"id": swarm_id, "status": "cancelled"}, "error": None}
