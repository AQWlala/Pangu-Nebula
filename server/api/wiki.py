from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.wiki_service import wiki_service
from .models import WikiCreate, WikiUpdate, WikiCompileRequest

router = APIRouter(prefix="/wiki", tags=["wiki"])


class WikiSearchRequest(BaseModel):
    """Wiki 搜索请求体"""

    query: str
    persona_id: int | None = None
    limit: int = 10


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


@router.post("/compile", summary="编译 Wiki", description="从对话编译 Wiki 笔记 (必须在 /{wiki_id} 之前注册)")
async def compile_wiki(req: WikiCompileRequest):
    """从对话编译 Wiki 笔记 (必须在 /{wiki_id} 之前注册)"""
    result = await wiki_service.compile_from_conversation(
        conversation_id=req.conversation_id,
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
