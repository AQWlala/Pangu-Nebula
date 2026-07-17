from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db.engine import async_session
from ..db.orm import Conversation, Message
from ..services.wiki_service import wiki_service
from .models import WikiCreate, WikiUpdate, WikiCompileRequest
from sqlalchemy import select, func

router = APIRouter(prefix="/wiki", tags=["wiki"])


class WikiSearchRequest(BaseModel):
    """Wiki 搜索请求体"""

    query: str
    persona_id: int | None = None
    limit: int = 10


@router.get("/conversations", summary="列出可编译对话", description="列出所有可选对话 (用于 Wiki 编译选择器), 按更新时间倒序返回, 含消息数")
async def list_conversations_for_wiki():
    """v2.3.0 Phase 3-D: 列出可选对话 (用于 Wiki 编译选择器)

    返回 [{id, title, persona_id, created_at, updated_at, message_count}]
    必须在 /{wiki_id} 之前注册, 避免路径冲突。
    """
    async with async_session() as session:
        # 聚合消息数, 一次查询
        stmt = (
            select(
                Conversation,
                func.count(Message.id).label("message_count"),
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        )
        rows = (await session.execute(stmt)).all()

    data = [
            {
                "id": conv.id,
                "title": conv.title or f"对话 #{conv.id}",
                "persona_id": conv.persona_id,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": int(msg_count or 0),
            }
            for conv, msg_count in rows
        ]
    return {"ok": True, "data": data, "error": None}


@router.get("", summary="列出 Wiki", description="列出 Wiki 页面 (支持 persona_id/tag/status 过滤 + 分页)")
async def list_wikis(
    persona_id: int | None = None,
    tag: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """列出 Wiki 页面 (支持 persona_id/tag/status 过滤 + 分页)"""
    data = await wiki_service.list_wikis(
        persona_id=persona_id,
        tag=tag,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("", summary="创建 Wiki", description="手动创建 Wiki 页面")
async def create_wiki(req: WikiCreate):
    """手动创建 Wiki 页面"""
    data = await wiki_service.create_wiki(
        title=req.title,
        content=req.content,
        html_content=req.html_content,
        persona_id=req.persona_id,
        tags=req.tags,
        source_conversation_id=req.source_conversation_id,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("/compile", summary="编译 Wiki", description="从对话编译 Wiki 笔记 (必须在 /{wiki_id} 之前注册; v2.3.0 支持多对话)")
async def compile_wiki(req: WikiCompileRequest):
    """从对话编译 Wiki 笔记 (必须在 /{wiki_id} 之前注册)

    v2.3.0 Phase 3-D: 支持 conversation_ids (多对话) 与 conversation_id (单对话, 向后兼容)。
    """
    if not req.conversation_ids and req.conversation_id is None:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": "conversation_id 或 conversation_ids 至少提供一个"},
        )
    result = await wiki_service.compile_from_conversation(
        conversation_id=req.conversation_id,
        conversation_ids=req.conversation_ids,
        persona_id=req.persona_id,
        title=req.title,
        tags=req.tags,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result)
    return result


@router.post("/search", summary="搜索 Wiki", description="搜索 Wiki 页面 (必须在 /{wiki_id} 之前注册)")
async def search_wikis(req: WikiSearchRequest):
    """搜索 Wiki 页面 (必须在 /{wiki_id} 之前注册)"""
    data = await wiki_service.search_wikis(
        req.query,
        persona_id=req.persona_id,
        limit=req.limit,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/{wiki_id}", summary="获取 Wiki", description="获取单个 Wiki 页面")
async def get_wiki(wiki_id: int):
    """获取单个 Wiki 页面"""
    data = await wiki_service.get_wiki(wiki_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Wiki not found"}
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{wiki_id}", summary="更新 Wiki", description="更新 Wiki 页面")
async def update_wiki(wiki_id: int, req: WikiUpdate):
    """更新 Wiki 页面"""
    data = await wiki_service.update_wiki(wiki_id, **req.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Wiki not found"}
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/{wiki_id}", summary="删除 Wiki", description="删除 Wiki 页面")
async def delete_wiki(wiki_id: int):
    """删除 Wiki 页面"""
    deleted = await wiki_service.delete_wiki(wiki_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Wiki not found"}
        )
    return {"ok": True, "data": {"id": wiki_id, "deleted": True}, "error": None}
