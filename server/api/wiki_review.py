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


@router.get("")
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


@router.post("")
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


@router.get("/list")
async def list_pending(
    scope: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    data = await _service.list_pending(session, scope=scope)
    return {"ok": True, "data": data, "error": None}


@router.post("/snapshot")
async def snapshot_url(
    req: URLSnapshotRequest, session: AsyncSession = Depends(get_session)
):
    data = await _service.snapshot_url(session, req.url)
    return {"ok": True, "data": data, "error": None}


@router.get("/{item_id}")
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


@router.get("/{item_id}/diff")
async def get_diff(item_id: int, session: AsyncSession = Depends(get_session)):
    data = await _service.get_diff(session, item_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Review item not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{item_id}/merge")
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


@router.post("/{item_id}/discard")
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
