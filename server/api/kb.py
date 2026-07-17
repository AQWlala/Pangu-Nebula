# server/api/kb.py
"""知识库 CRUD API"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from server.config_kb_cu import KBConfig
from server.kb.parser.validator import validate_frontmatter, ValidationError
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.service import (
    get_document_repo,
    get_inbox_writer,
    get_kb_config,
    get_vector_store,
)
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.repo import DocumentRepo

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])

logger = logging.getLogger(__name__)

# ===== v2.3.0 Phase 3-D: 解析器工厂 (借鉴 RAGFlow FACTORY 字典路由) =====
# 扩展名 -> 解析器实例 (延迟初始化, 容错可选依赖)
_PARSER_INSTANCES: dict = {}


def _get_parser(ext: str):
    """根据扩展名返回解析器实例 (单例缓存)。返回 None 表示回退为纯文本。"""
    ext = ext.lower()
    if ext in _PARSER_INSTANCES:
        return _PARSER_INSTANCES[ext]
    parser = None
    try:
        if ext in (".md", ".markdown", ".txt"):
            from server.kb.parser.markdown_parser import MarkdownParser
            parser = MarkdownParser()
        elif ext == ".pdf":
            from server.kb.parser.pdf_parser import PdfParser
            parser = PdfParser()
        elif ext in (".docx",):
            from server.kb.parser.office_parser import WordParser
            parser = WordParser()
        elif ext in (".xlsx", ".xls"):
            from server.kb.parser.office_parser import ExcelParser
            parser = ExcelParser()
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            from server.kb.parser.image_parser import ImageParser
            parser = ImageParser()
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析器加载失败 ext=%s: %s", ext, exc)
        parser = None
    _PARSER_INSTANCES[ext] = parser
    return parser


# ParserType 枚举 (借鉴 RAGFlow, 用于接口元数据)
PARSER_TYPES = {
    "markdown": {".md", ".markdown", ".txt"},
    "pdf": {".pdf"},
    "word": {".docx"},
    "excel": {".xlsx", ".xls"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"},
}


def _parse_file_to_md(file_path: Path) -> tuple[str, str, float]:
    """路由到对应解析器, 返回 (content_md, parser_name, confidence)。

    未知扩展名回退为纯文本读取 (utf-8, errors=ignore)。
    """
    ext = file_path.suffix.lower()
    parser = _get_parser(ext)
    if parser is None:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            return "", "fallback", 0.3
        return text, "fallback", 0.5
    try:
        result = parser.parse(file_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析失败 file=%s: %s", file_path.name, exc)
        return "", getattr(parser, "__class__", type("", (), {})).__name__.lower(), 0.0
    if not getattr(result, "success", False):
        # 解析失败时回退为空内容 (不阻塞批量导入)
        return "", getattr(result, "parser_name", "unknown"), 0.0
    return result.content, result.parser_name, result.confidence


def _stage_parsed_file(
    inbox: InboxWriter,
    original_filename: str,
    converted_md: str,
    parser_name: str,
    confidence: float,
    title: str | None = None,
    scope: str = "private",
    tags: list[str] | None = None,
) -> str:
    """构造 FrontMatter 并暂存到 _inbox, 返回 pending_id (同步, 由端点用 asyncio.to_thread 调用)。"""
    safe_title = (title or original_filename).strip()[:200] or original_filename
    checksum = f"sha256:{hashlib.sha256(converted_md.encode()).hexdigest()}"
    fm = FrontMatter(
        id=f"kb-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        title=safe_title,
        type="note",
        scope=scope,
        source_type="file_import",
        source_original_path=original_filename,
        confidence=confidence,
        checksum=checksum,
        tags=tags or [],
    )
    try:
        validate_frontmatter(fm)
    except ValidationError:
        # 校验失败时降级标题
        fm.title = f"import-{uuid.uuid4().hex[:6]}"
    return inbox.stage(
        original_filename=original_filename,
        converted_md=converted_md,
        frontmatter=fm,
        meta={"parser": parser_name, "source": "file_upload"},
    )


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


def _sync_fts5_index(
    meta_db: Path, doc_id: str, title: str, content: str, scope: str
) -> None:
    """Sync FTS5 index for a single document (designed to run in a worker thread)."""
    import sqlite3
    from server.kb.retrieval.hybrid import ensure_fts_table

    meta_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(meta_db)) as conn:
        ensure_fts_table(conn)
        # 先删除旧条目（支持重复审批同一文档的更新场景）
        conn.execute("DELETE FROM kb_documents_fts WHERE doc_id = ?", (doc_id,))
        conn.execute(
            "INSERT INTO kb_documents_fts (doc_id, title, content, scope) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, title, content, scope),
        )
        conn.commit()


@router.post("/import", response_model=ImportResponse)
async def import_document(
    req: ImportRequest,
    inbox: InboxWriter = Depends(get_inbox_writer),
):
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

    pending_id = await asyncio.to_thread(
        inbox.stage,
        original_filename="manual_input.md",
        converted_md=req.content,
        frontmatter=fm,
        meta={"parser": "manual", "source": "api"},
    )
    return ImportResponse(success=True, pending_id=pending_id, message="文档已暂存到 _inbox")


# ===== v2.3.0 Phase 3-D: 文件夹 zip 导入 + 文件级 CRUD =====


# zip 内单文件大小上限 (50MB), 防止解压炸弹
_ZIP_MEMBER_MAX_BYTES = 50 * 1024 * 1024
# zip 内文件总数上限, 防止解压炸弹
_ZIP_MAX_FILES = 500
# v2.3.1 P0-3: 单次上传文件大小上限 (50MB), 防止 OOM
_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def _safe_zip_extract(zip_bytes: bytes, dest: Path) -> list[Path]:
    """安全解压 zip 到 dest, 返回解压后的文件路径列表。

    防护:
    - 拒绝绝对路径 / 包含 .. 的成员 (路径穿越)
    - 限制单文件大小与总文件数
    - 限制总解压大小
    """
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total_size = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > _ZIP_MAX_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"zip 内文件数超限 ({len(members)} > {_ZIP_MAX_FILES})",
            )
        for member in members:
            # 路径穿越防护
            member_name = member.filename.replace("\\", "/")
            if member_name.startswith("/") or ".." in member_name.split("/"):
                logger.warning("zip 成员路径可疑, 跳过: %s", member.filename)
                continue
            if member.file_size > _ZIP_MEMBER_MAX_BYTES:
                logger.warning("zip 成员过大, 跳过: %s (%d bytes)", member.filename, member.file_size)
                continue
            total_size += member.file_size
            if total_size > _ZIP_MEMBER_MAX_BYTES * 10:
                raise HTTPException(status_code=400, detail="zip 解压总大小超限")
            target = dest / member_name
            # 确保目标在 dest 内
            try:
                target.resolve().relative_to(dest.resolve())
            except ValueError:
                logger.warning("zip 成员逃逸 dest, 跳过: %s", member.filename)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            extracted.append(target)
    return extracted


@router.post("/import/zip", summary="文件夹 zip 批量导入", description="上传 zip 文件, 解压后按扩展名路由解析器批量导入到 _inbox")
async def import_zip(
    file: UploadFile = File(..., description="zip 文件"),
    inbox: InboxWriter = Depends(get_inbox_writer),
):
    """v2.3.0 Phase 3-D: 文件夹 zip 批量导入

    接收 zip (multipart), 安全解压后按扩展名路由到 PARSER_FACTORY 解析,
    解析结果暂存到 _inbox, 返回汇总 {total, succeeded, failed, pending_ids, errors}。

    注意: 使用 /import/zip 路径以避免与现有 POST /import (JSON 单文档) 冲突, 保持向后兼容。
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 文件")
    # v2.3.1 P0-3: 限制读取大小, 超限返回 413 防止 OOM
    zip_bytes = await file.read(_UPLOAD_MAX_BYTES + 1)
    if len(zip_bytes) > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"zip 文件过大 (超过 {_UPLOAD_MAX_BYTES} bytes / 50MB 上限)",
        )
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="zip 文件为空")

    with tempfile.TemporaryDirectory(prefix="kb_zip_") as tmp:
        tmp_dir = Path(tmp)
        try:
            extracted = await asyncio.to_thread(_safe_zip_extract, zip_bytes, tmp_dir)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"zip 解压失败: {exc}")

        succeeded = 0
        failed = 0
        pending_ids: list[str] = []
        errors: list[dict] = []
        for fp in extracted:
            rel_name = str(fp.relative_to(tmp_dir))
            try:
                content_md, parser_name, confidence = await asyncio.to_thread(_parse_file_to_md, fp)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append({"file": rel_name, "error": f"parse failed: {exc}"})
                continue
            if not content_md.strip():
                failed += 1
                errors.append({"file": rel_name, "error": "empty content after parse"})
                continue
            try:
                title = fp.stem
                pending_id = await asyncio.to_thread(
                    _stage_parsed_file,
                    inbox,
                    rel_name,
                    content_md,
                    parser_name,
                    confidence,
                    title,
                )
                pending_ids.append(pending_id)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append({"file": rel_name, "error": f"stage failed: {exc}"})

    return {
        "ok": True,
        "data": {
            "total": len(extracted),
            "succeeded": succeeded,
            "failed": failed,
            "pending_ids": pending_ids,
            "errors": errors[:20],  # 限制返回条数
        },
        "error": None,
    }


@router.post("/files", summary="单文件上传", description="上传单个文件 (multipart), 按扩展名路由解析器后暂存到 _inbox")
async def upload_file(
    file: UploadFile = File(..., description="待导入文件"),
    inbox: InboxWriter = Depends(get_inbox_writer),
):
    """v2.3.0 Phase 3-D: 单文件上传 (multipart)

    支持扩展名: md/txt/pdf/docx/xlsx/png/jpg 等 (见 PARSER_TYPES)。
    未知扩展名回退为纯文本读取。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    # v2.3.1 P0-3: 限制读取大小, 超限返回 413 防止 OOM
    raw = await file.read(_UPLOAD_MAX_BYTES + 1)
    if len(raw) > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大 (超过 {_UPLOAD_MAX_BYTES} bytes / 50MB 上限)",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")

    with tempfile.TemporaryDirectory(prefix="kb_file_") as tmp:
        tmp_dir = Path(tmp)
        # 保留原始扩展名以便路由
        safe_name = Path(file.filename).name
        target = tmp_dir / safe_name
        target.write_bytes(raw)
        try:
            content_md, parser_name, confidence = await asyncio.to_thread(_parse_file_to_md, target)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"解析失败: {exc}")

    if not content_md.strip():
        raise HTTPException(status_code=400, detail="文件解析后内容为空")

    title = Path(file.filename).stem
    pending_id = await asyncio.to_thread(
        _stage_parsed_file,
        inbox,
        file.filename,
        content_md,
        parser_name,
        confidence,
        title,
    )
    return {
        "ok": True,
        "data": {
            "pending_id": pending_id,
            "filename": file.filename,
            "parser": parser_name,
            "confidence": confidence,
        },
        "error": None,
    }


class FileUpdateRequest(BaseModel):
    """文件更新请求 (重命名/移动)"""

    title: str | None = None
    scope: str | None = None
    tags: list[str] | None = None
    new_id: str | None = None  # 移动 (改 doc_id)

    @field_validator('scope')
    @classmethod
    def scope_valid(cls, v):
        if v is None:
            return v
        if v not in ('private', 'project', 'public'):
            raise ValueError('scope must be one of: private, project, public')
        return v


@router.delete("/files/{file_id}", summary="删除文件", description="根据 doc_id 删除知识库文件 (同时清理 FTS5 索引)")
async def delete_file(
    file_id: str,
    repo: DocumentRepo = Depends(get_document_repo),
    config: KBConfig = Depends(get_kb_config),
):
    """v2.3.0 Phase 3-D: 删除文件 (file_id = doc_id)"""
    if not await asyncio.to_thread(repo.exists, file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    await asyncio.to_thread(repo.delete, file_id)
    # 清理 FTS5 索引 (失败不阻塞删除)
    try:
        import sqlite3
        from server.kb.retrieval.hybrid import ensure_fts_table

        with sqlite3.connect(str(config.meta_db)) as conn:
            ensure_fts_table(conn)
            conn.execute("DELETE FROM kb_documents_fts WHERE doc_id = ?", (file_id,))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除 FTS5 索引失败 doc_id=%s: %s", file_id, exc)
    return {"ok": True, "data": {"id": file_id, "deleted": True}, "error": None}


@router.put("/files/{file_id}", summary="更新文件", description="重命名 (title) / 移动 (scope/new_id) / 更新标签")
async def update_file(
    file_id: str,
    req: FileUpdateRequest,
    repo: DocumentRepo = Depends(get_document_repo),
    config: KBConfig = Depends(get_kb_config),
):
    """v2.3.0 Phase 3-D: 更新文件 (重命名/移动)

    - title: 修改标题
    - scope: 修改作用域 (private/project/public)
    - tags: 修改标签
    - new_id: 移动 (改 doc_id, 旧文件删除, 新文件保存)
    """
    if not await asyncio.to_thread(repo.exists, file_id):
        raise HTTPException(status_code=404, detail="文件不存在")

    fm, body = await asyncio.to_thread(repo.read, file_id)

    # 应用字段更新
    if req.title is not None:
        fm.title = req.title.strip()[:200] or fm.title
    if req.scope is not None:
        fm.scope = req.scope
    if req.tags is not None:
        fm.tags = req.tags

    target_id = req.new_id.strip() if req.new_id else file_id
    if req.new_id and req.new_id != file_id:
        # 移动: 校验新 id 不存在, 保存新文件后删除旧文件
        if await asyncio.to_thread(repo.exists, req.new_id):
            raise HTTPException(status_code=409, detail=f"目标 id 已存在: {req.new_id}")
        fm.id = req.new_id
        await asyncio.to_thread(repo.save, fm, body)
        await asyncio.to_thread(repo.delete, file_id)
        # 同步 FTS5: 删除旧 doc_id
        try:
            import sqlite3
            from server.kb.retrieval.hybrid import ensure_fts_table

            with sqlite3.connect(str(config.meta_db)) as conn:
                ensure_fts_table(conn)
                conn.execute("DELETE FROM kb_documents_fts WHERE doc_id = ?", (file_id,))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("FTS5 同步失败 (move): %s", exc)
    else:
        # 原地更新 (repo.save 覆盖)
        await asyncio.to_thread(repo.save, fm, body)

    return {
        "ok": True,
        "data": {
            "id": target_id,
            "title": fm.title,
            "scope": fm.scope,
            "tags": fm.tags,
        },
        "error": None,
    }


@router.get("/inbox")
async def list_inbox(inbox: InboxWriter = Depends(get_inbox_writer)):
    pending = await asyncio.to_thread(inbox.list_pending)
    return {"pending": pending}


@router.post("/inbox/{pending_id}/approve")
async def approve_document(
    pending_id: str,
    inbox: InboxWriter = Depends(get_inbox_writer),
    repo: DocumentRepo = Depends(get_document_repo),
    store: ChromaVectorStore = Depends(get_vector_store),
    config: KBConfig = Depends(get_kb_config),
):
    pending = await asyncio.to_thread(inbox.get_pending, pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="待审核项不存在")

    fm_content = pending["frontmatter"] + "\n\n# placeholder"
    fm, _ = parse_frontmatter(fm_content)
    if not fm:
        raise HTTPException(status_code=500, detail="front matter 解析失败")

    await asyncio.to_thread(repo.save, fm, pending["converted_md"])
    await asyncio.to_thread(inbox.remove_pending, pending_id)

    # After saving the document, trigger indexing so the document is searchable
    try:
        from server.kb.retrieval.indexer import Indexer

        indexer = Indexer(
            repo=repo, vector_store=store, indexes_dir=config.indexes_dir
        )
        await asyncio.to_thread(indexer.build_index)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Indexing failed after approval: {e}"
        )
        # Don't fail the approval if indexing fails

    # Sync FTS5 full-text index so keyword search uses FTS5 instead of brute-force
    try:
        await asyncio.to_thread(
            _sync_fts5_index,
            config.meta_db,
            fm.id,
            fm.title,
            pending["converted_md"],
            fm.scope,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"FTS5 sync failed after approval: {e}"
        )
        # FTS5 失败不应中断审批流程

    return {"success": True, "doc_id": fm.id, "message": "文档已审核通过并保存"}


@router.delete("/inbox/{pending_id}")
async def reject_document(
    pending_id: str,
    inbox: InboxWriter = Depends(get_inbox_writer),
):
    await asyncio.to_thread(inbox.remove_pending, pending_id)
    return {"success": True, "message": "已拒绝并移除"}


@router.get("/status")
async def kb_status():
    """v2.2.0 Phase 4: 知识库状态摘要 — 供 KnowledgePanel 展示。

    返回 KnowledgeService.get_status() 的结果:
    - store_type: "lance" | "chroma"
    - chunk_count: 向量记录数
    - persist_dir: 持久化目录
    """
    from server.services.knowledge_service import knowledge_service

    try:
        return {"ok": True, "data": knowledge_service.get_status(), "error": None}
    except Exception as exc:
        return {
            "ok": False,
            "data": {"store_type": "unknown", "chunk_count": 0, "persist_dir": ""},
            "error": str(exc),
        }


@router.get("/documents")
async def list_documents(
    scope: str | None = None,
    repo: DocumentRepo = Depends(get_document_repo),
):
    doc_ids = await asyncio.to_thread(repo.list_all)
    docs = []
    for doc_id in doc_ids:
        fm, _ = await asyncio.to_thread(repo.read, doc_id)
        if scope and fm.scope != scope:
            continue
        docs.append({"id": fm.id, "title": fm.title, "type": fm.type, "scope": fm.scope})
    # v2.2.0: 添加 ok/data/error 包装以兼容 apiGet,保留 documents 字段向后兼容
    return {"ok": True, "data": {"documents": docs}, "documents": docs, "error": None}


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    scope: str | None = None,
    repo: DocumentRepo = Depends(get_document_repo),
):
    if not await asyncio.to_thread(repo.exists, doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    fm, body = await asyncio.to_thread(repo.read, doc_id)
    if scope and fm.scope != scope:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": fm.id, "title": fm.title, "type": fm.type,
        "scope": fm.scope, "confidence": fm.confidence,
        "tags": fm.tags, "content": body,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    scope: str | None = None,
    repo: DocumentRepo = Depends(get_document_repo),
):
    if not await asyncio.to_thread(repo.exists, doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    if scope:
        fm, _ = await asyncio.to_thread(repo.read, doc_id)
        if fm.scope != scope:
            raise HTTPException(status_code=404, detail="文档不存在")
    await asyncio.to_thread(repo.delete, doc_id)
    return {"success": True, "message": "文档已删除"}


@router.get("/search")
async def search_documents(
    query: str,
    scope: str = "private",
    top_k: int = 5,
    repo: DocumentRepo = Depends(get_document_repo),
    store: ChromaVectorStore = Depends(get_vector_store),
):
    """混合检索文档"""
    if not query or not query.strip():
        return JSONResponse(status_code=400, content={"error": "query must not be empty"})
    top_k = max(1, min(50, top_k))  # Clamp to [1, 50]
    from server.kb.retrieval.hybrid import HybridSearcher

    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = await asyncio.to_thread(
        searcher.search, query=query, scope=scope, top_k=top_k
    )
    search_results = [{
        "doc_id": r.doc_id, "title": r.title, "chunk_text": r.chunk_text,
        "score": r.score, "source_method": r.source_method, "scope": r.scope, "tags": r.tags,
    } for r in results]
    # v2.2.0: 添加 ok/data/error 包装以兼容 apiGet,保留 results 字段向后兼容
    return {"ok": True, "data": {"results": search_results}, "results": search_results, "error": None}
