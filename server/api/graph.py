# server/api/graph.py
"""知识图谱查询 API"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from server.kb.graph.kuzu_store import KuzuGraphStore
from server.kb.service import get_document_repo, get_graph_store
from server.kb.storage.repo import DocumentRepo

router = APIRouter(prefix="/api/graph", tags=["knowledge-graph"])


@router.get("/documents")
async def get_document_graph(
    scope: str = "private",
    depth: int = 2,
    store: KuzuGraphStore = Depends(get_graph_store),
):
    depth = max(1, min(3, depth))  # Clamp to [1, 3]
    docs = await asyncio.to_thread(store.list_documents, scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document",
              "scope": d["scope"], "doc_type": d["type"], "confidence": d["confidence"]} for d in docs]
    # 单次 Cypher 查询获取所有关系，消除 N+1 调用（之前为每个 doc 调用一次 get_relations）。
    all_relations = await asyncio.to_thread(store.get_all_relations, scope=scope)
    edges = [
        {
            "source": rel["source_doc_id"],
            "target": rel["target_doc_id"],
            "relation_type": rel["relation_type"],
            "weight": rel["confidence"],
        }
        for rel in all_relations
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/entities")
async def get_entity_graph(scope: str = "private", min_weight: float = 0.5):
    return {"nodes": [], "edges": []}


@router.get("/timeline")
async def get_timeline_graph(
    scope: str = "private",
    store: KuzuGraphStore = Depends(get_graph_store),
):
    docs = await asyncio.to_thread(store.list_documents, scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document", "scope": d["scope"]} for d in docs]
    return {"nodes": nodes, "edges": []}


@router.post("/rebuild")
async def rebuild_graph(
    scope: str | None = None,
    store: KuzuGraphStore = Depends(get_graph_store),
    repo: DocumentRepo = Depends(get_document_repo),
):
    from server.kb.graph.relation_extractor import RelationExtractor

    # 收集所有文档并写入节点
    documents = []
    count = 0
    for doc_id in await asyncio.to_thread(repo.list_all):
        fm, _ = await asyncio.to_thread(repo.read, doc_id)
        if scope and fm.scope != scope:
            continue
        await asyncio.to_thread(
            store.add_document, fm.id, fm.title, fm.type, fm.scope, fm.confidence, fm.id
        )
        documents.append(fm)
        count += 1

    # 基于共享 tags/categories 推荐并写入关系边
    extractor = RelationExtractor()
    relation_count = 0
    for i, doc in enumerate(documents):
        candidates = extractor.recommend_relations(doc, documents[i + 1:])
        for rel in candidates:
            try:
                await asyncio.to_thread(
                    store.add_relation,
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    rel_type=rel.relation_type,
                    weight=rel.confidence,
                )
                relation_count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to add relation: {e}")

    return {"success": True, "indexed_count": count, "relation_count": relation_count}
