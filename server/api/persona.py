from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services import active_state, persona_service
from .models import PersonaCreate, PersonaGenerateRequest, PersonaUpdate

router = APIRouter(prefix="/persona", tags=["persona"])


@router.get("")
async def list_personas(session: AsyncSession = Depends(get_session)):
    data = await persona_service.list_personas(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/active")
async def get_active_persona(session: AsyncSession = Depends(get_session)):
    persona_id = active_state.get_active_persona_id()
    if persona_id is None:
        return {"ok": True, "data": None, "error": None}
    data = await persona_service.get_persona(session, persona_id)
    return {"ok": True, "data": data, "error": None}


@router.post("")
async def create_persona(req: PersonaCreate, session: AsyncSession = Depends(get_session)):
    data = await persona_service.create_persona(session, req.model_dump())
    return {"ok": True, "data": data, "error": None}


@router.post("/generate")
async def generate_persona(req: PersonaGenerateRequest):
    try:
        data = await persona_service.generate_persona_with_ai(
            description=req.description,
            model_provider=req.model_provider,
            model_name=req.model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.get("/{persona_id}")
async def get_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    data = await persona_service.get_persona(session, persona_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    return {"ok": True, "data": data, "error": None}


@router.put("/{persona_id}")
async def update_persona(
    persona_id: int, req: PersonaUpdate, session: AsyncSession = Depends(get_session)
):
    data = await persona_service.update_persona(
        session, persona_id, req.model_dump(exclude_unset=True)
    )
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    return {"ok": True, "data": data, "error": None}


@router.delete("/{persona_id}")
async def delete_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await persona_service.delete_persona(session, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    if active_state.get_active_persona_id() == persona_id:
        active_state.clear_active_persona_id()
    return {"ok": True, "data": {"id": persona_id, "deleted": True}, "error": None}


@router.post("/{persona_id}/activate")
async def activate_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    data = await persona_service.get_persona(session, persona_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    active_state.set_active_persona_id(persona_id)
    return {"ok": True, "data": {"active_persona_id": persona_id}, "error": None}
