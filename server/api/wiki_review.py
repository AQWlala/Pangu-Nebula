from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services.wiki_review_service import WikiReviewService

router = APIRouter(prefix="/wiki-review", tags=["wiki-review"])
_service = WikiReviewService()


class WikiReviewSubmit(BaseModel):
    wiki_id: int
    title: str
    proposed_content: str
    current_content: str | None = None
    scope: str = "default"


class WikiReviewAction(BaseModel):
    review_note: str = ""


class URLSnapshotRequest(BaseModel):
    url: str


@router.get("", summary="Wiki 审核 模块信息", description="返回知识库安全写回审核模块的信息和端点列表")
async def module_info():
    return {
        "ok": True,
        "data": {
            "module": "wiki-review",
            "description": "知识库安全写回审核",
            "endpoints": [
                "POST /wiki-review", "GET /wiki-review/list",
                "GET /wiki-review/{id}", "GET /wiki-review/{id}/diff",
                "POST /wiki-review/{id}/merge", "POST /wiki-review/{id}/discard",
                "POST /wiki-review/snapshot",
            ],
        },
        "error": None,
    }


@router.post("", summary="提交审核", description="将 Wiki 写回内容提交审核,包含 proposed_content 与 current_content")
async def submit_for_review(
    req: WikiReviewSubmit, session: AsyncSession = Depends(get_session)
):
    data = await _service.submit_for_review(
        session,
        req.wiki_id,
        req.title,
        req.proposed_content,
        req.current_content,
        req.scope,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/list", summary="列出待审核项", description="按 scope 过滤并列出待审核条目")
async def list_pending(
    scope: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    data = await _service.list_pending(session, scope=scope)
    return {"ok": True, "data": data, "error": None}


@router.post("/snapshot", summary="快照 URL", description="抓取指定 URL 的内容快照,用于审核比对")
async def snapshot_url(
    req: URLSnapshotRequest, session: AsyncSession = Depends(get_session)
):
    data = await _service.snapshot_url(session, req.url)
    return {"ok": True, "data": data, "error": None}


@router.get("/{item_id}", summary="获取审核条目", description="根据 ID 获取单个审核条目详情")
async def get_review_item(
    item_id: int, session: AsyncSession = Depends(get_session)
):
    data = await _service.get_review_item(session, item_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Review item not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/{item_id}/diff", summary="获取差异", description="返回审核条目的内容差异(新增/删除/修改)")
async def get_diff(item_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.get_diff(session, item_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Review item not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{item_id}/merge", summary="合并审核条目", description="将审核条目的内容合并到 Wiki,可附审核备注")
async def merge_item(
    item_id: int,
    req: WikiReviewAction,
    session: AsyncSession = Depends(get_session),
):
    data = await _service.merge(session, item_id, req.review_note)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Review item not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{item_id}/discard", summary="丢弃审核条目", description="丢弃审核条目的内容,可附审核备注")
async def discard_item(
    item_id: int,
    req: WikiReviewAction,
    session: AsyncSession = Depends(get_session),
):
    data = await _service.discard(session, item_id, req.review_note)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Review item not found"},
        )
    return {"ok": True, "data": data, "error": None}
