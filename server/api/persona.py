from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services import active_state, persona_service
from .models import PersonaCreate, PersonaGenerateRequest, PersonaUpdate

router = APIRouter(prefix="/persona", tags=["persona"])


@router.get("", summary="列出 Persona", description="列出所有 Persona 配置")
async def list_personas(session: AsyncSession = Depends(get_session)):
    data = await persona_service.list_personas(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/active", summary="获取当前激活的 Persona", description="获取当前会话激活的 Persona,未设置时返回 null")
async def get_active_persona(session: AsyncSession = Depends(get_session)):
    persona_id = active_state.get_active_persona_id()
    if persona_id is None:
        return {"ok": True, "data": None, "error": None}
    data = await persona_service.get_persona(session, persona_id)
    return {"ok": True, "data": data, "error": None}


@router.post("", summary="创建 Persona", description="创建一个新的 Persona 配置,包括 system_prompt、模型参数等")
async def create_persona(req: PersonaCreate, session: AsyncSession = Depends(get_session)):
    data = await persona_service.create_persona(session, req.model_dump())
    return {"ok": True, "data": data, "error": None}


@router.post("/generate", summary="AI 生成 Persona", description="通过自然语言描述让 AI 自动生成 Persona 配置")
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


@router.get("/{persona_id}", summary="获取 Persona", description="根据 ID 获取单个 Persona 配置")
async def get_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    data = await persona_service.get_persona(session, persona_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    return {"ok": True, "data": data, "error": None}


@router.put("/{persona_id}", summary="更新 Persona", description="更新指定 Persona 的字段(部分更新)")
async def update_persona(
    persona_id: int, req: PersonaUpdate, session: AsyncSession = Depends(get_session)
):
    data = await persona_service.update_persona(
        session, persona_id, req.model_dump(exclude_unset=True)
    )
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    return {"ok": True, "data": data, "error": None}


@router.delete("/{persona_id}", summary="删除 Persona", description="删除指定 Persona,若为当前激活则会清除激活状态")
async def delete_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await persona_service.delete_persona(session, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    if active_state.get_active_persona_id() == persona_id:
        active_state.clear_active_persona_id()
    return {"ok": True, "data": {"id": persona_id, "deleted": True}, "error": None}


@router.post("/{persona_id}/activate", summary="激活 Persona", description="将指定 Persona 设为当前会话激活的角色")
async def activate_persona(persona_id: int, session: AsyncSession = Depends(get_session)):
    data = await persona_service.get_persona(session, persona_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Persona not found"})
    active_state.set_active_persona_id(persona_id)
    return {"ok": True, "data": {"active_persona_id": persona_id}, "error": None}
