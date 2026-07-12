from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services.memory_service import memory_service
from .models import MemoryCreate, MemoryUpdate, MemorySearchQuery

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", summary="创建记忆", description="创建一条新的记忆条目,可指定层级、标题、HTML 内容、重要性和标签")
async def create_memory(req: MemoryCreate, session: AsyncSession = Depends(get_session)):
    data = await memory_service.create_memory(
        session,
        persona_id=req.persona_id,
        layer=req.layer,
        title=req.title,
        html_content=req.html_content,
        importance=req.importance,
        tags=req.tags,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("", summary="列出记忆", description="按 Persona、层级、标签过滤并分页列出记忆条目")
async def list_memories(
    persona_id: int | None = None,
    layer: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
):
    data = await memory_service.list_memories(
        session,
        persona_id=persona_id,
        layer=layer,
        tag=tag,
        page=page,
        page_size=page_size,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("/search", summary="搜索记忆", description="通过关键词搜索记忆,支持按 Persona 和层级过滤")
async def search_memories(req: MemorySearchQuery, session: AsyncSession = Depends(get_session)):
    data = await memory_service.search_memories(
        session,
        req.query,
        persona_id=req.persona_id,
        layer=req.layer,
        limit=req.limit,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/graph", summary="获取记忆图谱", description="返回记忆之间的链接图谱(节点 + 边),可按 Persona 和层级过滤")
async def get_memory_graph(
    persona_id: int | None = None,
    layer: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    data = await memory_service.get_linked_graph(
        session, persona_id=persona_id, layer=layer
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/{memory_id}", summary="获取记忆", description="根据 ID 获取单条记忆详情")
async def get_memory(memory_id: int, session: AsyncSession = Depends(get_session)):
    data = await memory_service.get_memory(session, memory_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Memory not found"}
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{memory_id}", summary="更新记忆", description="更新指定记忆的字段(部分更新)")
async def update_memory(
    memory_id: int, req: MemoryUpdate, session: AsyncSession = Depends(get_session)
):
    data = await memory_service.update_memory(
        session, memory_id, **req.model_dump(exclude_unset=True)
    )
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Memory not found"}
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/{memory_id}", summary="删除记忆", description="删除指定记忆条目")
async def delete_memory(memory_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await memory_service.delete_memory(session, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Memory not found"}
        )
    return {"ok": True, "data": {"id": memory_id, "deleted": True}, "error": None}


@router.get("/{memory_id}/backlinks", summary="获取反向链接", description="返回指向指定记忆的所有反向链接")
async def get_backlinks(memory_id: int, session: AsyncSession = Depends(get_session)):
    data = await memory_service.get_backlinks(session, memory_id)
    return {"ok": True, "data": data, "error": None}
