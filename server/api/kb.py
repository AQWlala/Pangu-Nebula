# server/api/kb.py
"""知识库 CRUD API"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
import hashlib
import uuid

from server.config_kb_cu import KBConfig
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter
from server.kb.parser.validator import validate_frontmatter, ValidationError
from server.kb.retrieval.vectorstore import ChromaVectorStore

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class ImportRequest(BaseModel):
    content: str = Field(..., max_length=10_000_000)  # 10MB
    title: str = Field(..., max_length=200)
    type: str = "note"
    scope: str = "private"
    tags: list[str] = []
    categories: list[str] = []

    @field_validator('title')
    @classmethod
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('title must not be empty')
        return v.strip()

    @field_validator('content')
    @classmethod
    def content_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('content must not be empty')
        return v

    @field_validator('tags', 'categories')
    @classmethod
    def tags_no_comma(cls, v):
        for item in v:
            if ',' in item:
                raise ValueError(f'tag/category must not contain comma: {item}')
            if len(item) > 32:
                raise ValueError(f'tag/category must not exceed 32 chars: {item}')
        return v

    @field_validator('scope')
    @classmethod
    def scope_valid(cls, v):
        if v not in ('private', 'project', 'public'):
            raise ValueError('scope must be one of: private, project, public')
        return v


class ImportResponse(BaseModel):
    success: bool
    pending_id: str
    message: str = ""


def _get_config() -> KBConfig:
    config = KBConfig()
    config.ensure_dirs()
    return config


def _get_vector_store(request: Request) -> ChromaVectorStore:
    """Return the singleton ChromaVectorStore from app.state when available.

    Falls back to per-request construction when the lifespan did not
    initialize a singleton (e.g. in tests that bypass lifespan).
    """
    store = getattr(request.app.state, "vector_store", None)
    if store is not None:
        return store
    config = _get_config()
    return ChromaVectorStore(persist_dir=config.chroma_dir)


@router.post("/import", response_model=ImportResponse)
async def import_document(req: ImportRequest):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)

    checksum = f"sha256:{hashlib.sha256(req.content.encode()).hexdigest()}"
    fm = FrontMatter(
        id=f"kb-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
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
async def approve_document(pending_id: str, request: Request):
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

    # After saving the document, trigger indexing so the document is searchable
    try:
        from server.kb.retrieval.indexer import Indexer

        store = _get_vector_store(request)
        indexer = Indexer(
            repo=repo, vector_store=store, indexes_dir=config.indexes_dir
        )
        indexer.build_index()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Indexing failed after approval: {e}"
        )
        # Don't fail the approval if indexing fails

    return {"success": True, "doc_id": fm.id, "message": "文档已审核通过并保存"}


@router.delete("/inbox/{pending_id}")
async def reject_document(pending_id: str):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    inbox.remove_pending(pending_id)
    return {"success": True, "message": "已拒绝并移除"}


@router.get("/documents")
async def list_documents(scope: str | None = None):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    doc_ids = repo.list_all()
    docs = []
    for doc_id in doc_ids:
        fm, _ = repo.read(doc_id)
        if scope and fm.scope != scope:
            continue
        docs.append({"id": fm.id, "title": fm.title, "type": fm.type, "scope": fm.scope})
    return {"documents": docs}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, scope: str | None = None):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    fm, body = repo.read(doc_id)
    if scope and fm.scope != scope:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": fm.id, "title": fm.title, "type": fm.type,
        "scope": fm.scope, "confidence": fm.confidence,
        "tags": fm.tags, "content": body,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, scope: str | None = None):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    if scope:
        fm, _ = repo.read(doc_id)
        if fm.scope != scope:
            raise HTTPException(status_code=404, detail="文档不存在")
    repo.delete(doc_id)
    return {"success": True, "message": "文档已删除"}


@router.get("/search")
async def search_documents(query: str, scope: str = "private", top_k: int = 5, request: Request = None):
    """混合检索文档"""
    if not query or not query.strip():
        return JSONResponse(status_code=400, content={"error": "query must not be empty"})
    top_k = max(1, min(50, top_k))  # Clamp to [1, 50]
    from server.kb.retrieval.hybrid import HybridSearcher
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    store = _get_vector_store(request)
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search(query=query, scope=scope, top_k=top_k)
    return {"results": [{
        "doc_id": r.doc_id, "title": r.title, "chunk_text": r.chunk_text,
        "score": r.score, "source_method": r.source_method, "scope": r.scope, "tags": r.tags,
    } for r in results]}
