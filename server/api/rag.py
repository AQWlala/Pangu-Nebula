"""RAG 检索 API 路由 (T2.8)。

为 Wiki 内容提供语义检索接口,支持:
- 索引构建(全量重建 / 单页索引 / 单页移除)
- 语义检索(返回 top-k 相关条目及相似度)
- L3 验证(判断查询是否在索引中有足够相似的匹配)
- 索引状态查询

注意: 本路由文件不注册到 server/main.py,由主线程统一处理路由注册。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..db.orm import WikiPage
from ..services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])
# 模块级单例: 索引在内存中持久化,跨请求复用
_service = RAGService()


class RAGIndexRequest(BaseModel):
    """单页索引请求体(可选字段,用于直接传入内容而非查库)"""

    title: str | None = None
    content: str | None = None


class RAGVerifyRequest(BaseModel):
    """L3 验证请求体"""

    query: str
    threshold: float | None = None


@router.get("", summary="RAG 模块信息", description="返回 RAG 语义检索模块的信息和端点列表")
async def module_info():
    return {
        "ok": True,
        "data": {
            "module": "rag",
            "description": "Wiki 语义检索索引(TF-IDF + 余弦相似度 mock)",
            "endpoints": [
                "GET /rag",
                "POST /rag/index",
                "POST /rag/index/{wiki_id}",
                "DELETE /rag/index/{wiki_id}",
                "GET /rag/search",
                "POST /rag/verify",
                "GET /rag/status",
            ],
        },
        "error": None,
    }


@router.post(
    "/index",
    summary="全量重建索引",
    description="遍历所有 WikiPage 重建 RAG 索引,清空旧索引后重新构建",
)
async def rebuild_index(session: AsyncSession = Depends(get_session)):
    _service.clear()
    result = await _service.index_all_wiki_pages(session)
    return {"ok": True, "data": result, "error": None}


@router.post(
    "/index/{wiki_id}",
    summary="索引单个 Wiki 页面",
    description="根据 wiki_id 从数据库读取内容并加入索引;若请求体提供 title/content 则使用请求体",
)
async def index_single(
    wiki_id: int,
    req: RAGIndexRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    title = req.title if req and req.title else None
    content = req.content if req and req.content is not None else None

    # 若未提供 title/content,从数据库读取
    if title is None or content is None:
        page = await session.get(WikiPage, wiki_id)
        if page is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "data": None, "error": f"WikiPage {wiki_id} not found"},
            )
        if title is None:
            title = page.title or ""
        if content is None:
            content = page.plain_text or page.content or ""

    if not content.strip():
        return {
            "ok": False,
            "data": None,
            "error": "content is empty, nothing to index",
        }

    doc = _service.index_wiki_page(wiki_id, title, content)
    return {
        "ok": True,
        "data": {
            "doc_id": doc.doc_id,
            "wiki_id": doc.wiki_id,
            "title": doc.title,
            "indexed_at": doc.indexed_at,
        },
        "error": None,
    }


@router.delete(
    "/index/{wiki_id}",
    summary="移除单个 Wiki 页面索引",
    description="根据 wiki_id 从 RAG 索引中移除该文档",
)
async def remove_single(wiki_id: int):
    doc_id = f"wiki:{wiki_id}"
    removed = _service.remove_document(doc_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"doc {doc_id} not in index"},
        )
    return {"ok": True, "data": {"removed": doc_id}, "error": None}


@router.get(
    "/search",
    summary="语义检索",
    description="根据查询文本检索 top-k 最相关的 Wiki 页面,返回相似度分数",
)
async def search(
    q: str = Query(..., description="查询文本"),
    top_k: int = Query(5, ge=1, le=50, description="返回结果数量上限"),
):
    results = _service.search(q, top_k=top_k)
    return {
        "ok": True,
        "data": {
            "query": q,
            "top_k": top_k,
            "count": len(results),
            "results": [
                {
                    "doc_id": r.doc_id,
                    "wiki_id": r.wiki_id,
                    "title": r.title,
                    "content_preview": r.content_preview,
                    "score": r.score,
                }
                for r in results
            ],
        },
        "error": None,
    }


@router.post(
    "/verify",
    summary="L3 语义验证",
    description="判断查询是否在索引中有足够相似的匹配(用于 L3 语义层验证)",
)
async def verify(req: RAGVerifyRequest):
    result = _service.verify(req.query, threshold=req.threshold)
    return {
        "ok": True,
        "data": {
            "verified": result.verified,
            "best_score": result.best_score,
            "threshold": result.threshold,
            "best_match": {
                "doc_id": result.best_match.doc_id,
                "wiki_id": result.best_match.wiki_id,
                "title": result.best_match.title,
                "content_preview": result.best_match.content_preview,
                "score": result.best_match.score,
            }
            if result.best_match
            else None,
        },
        "error": None,
    }


@router.get(
    "/status",
    summary="索引状态",
    description="返回 RAG 索引的状态摘要(文档数、词表大小、已索引文档列表)",
)
async def status():
    data = _service.get_status()
    return {"ok": True, "data": data, "error": None}
