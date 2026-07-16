# server/api/kb.py
"""知识库 CRUD API"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import hashlib

from server.config_kb_cu import KBConfig
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter
from server.kb.parser.validator import validate_frontmatter, ValidationError

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class ImportRequest(BaseModel):
    content: str
    title: str
    type: str = "note"
    scope: str = "private"
    tags: list[str] = []
    categories: list[str] = []


class ImportResponse(BaseModel):
    success: bool
    pending_id: str
    message: str = ""


def _get_config() -> KBConfig:
    config = KBConfig()
    config.ensure_dirs()
    return config


@router.post("/import", response_model=ImportResponse)
async def import_document(req: ImportRequest):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)

    checksum = f"sha256:{hashlib.sha256(req.content.encode()).hexdigest()}"
    fm = FrontMatter(
        id=f"kb-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        title=req.title, type=req.type, scope=req.scope,
        source_type="manual", confidence=0.95, checksum=checksum,
        tags=req.tags, categories=req.categories,
    )

    try:
        validate_frontmatter(fm)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pending_id = inbox.stage(
        original_filename="manual_input.md",
        converted_md=req.content,
        frontmatter=fm,
        meta={"parser": "manual", "source": "api"},
    )
    return ImportResponse(success=True, pending_id=pending_id, message="文档已暂存到 _inbox")


@router.get("/inbox")
async def list_inbox():
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    return {"pending": inbox.list_pending()}


@router.post("/inbox/{pending_id}/approve")
async def approve_document(pending_id: str):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    repo = DocumentRepo(documents_dir=config.documents_dir)

    pending = inbox.get_pending(pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="待审核项不存在")

    fm_content = pending["frontmatter"] + "\n\n# placeholder"
    fm, _ = parse_frontmatter(fm_content)
    if not fm:
        raise HTTPException(status_code=500, detail="front matter 解析失败")

    repo.save(fm, pending["converted_md"])
    inbox.remove_pending(pending_id)
    return {"success": True, "doc_id": fm.id, "message": "文档已审核通过并保存"}


@router.delete("/inbox/{pending_id}")
async def reject_document(pending_id: str):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    inbox.remove_pending(pending_id)
    return {"success": True, "message": "已拒绝并移除"}


@router.get("/documents")
async def list_documents():
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    return {"documents": repo.list_all()}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    fm, body = repo.read(doc_id)
    return {
        "id": fm.id, "title": fm.title, "type": fm.type,
        "scope": fm.scope, "confidence": fm.confidence,
        "tags": fm.tags, "content": body,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    repo.delete(doc_id)
    return {"success": True, "message": "文档已删除"}
