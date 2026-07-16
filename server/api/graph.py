# server/api/graph.py
"""知识图谱查询 API"""
from __future__ import annotations
from fastapi import APIRouter
from server.config_kb_cu import KBConfig
from server.kb.graph.kuzu_store import KuzuGraphStore

router = APIRouter(prefix="/api/graph", tags=["knowledge-graph"])


def _get_store() -> KuzuGraphStore:
    config = KBConfig()
    # 注意：不调用 ensure_dirs()，因为 KuzuGraphStore 会自行创建父目录，
    # 且 kuzu 0.11.3 不允许 db_dir 本身预先存在为目录。
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    return store


@router.get("/documents")
async def get_document_graph(scope: str = "private", depth: int = 2):
    depth = max(1, min(3, depth))  # Clamp to [1, 3]
    store = _get_store()
    docs = store.list_documents(scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document",
              "scope": d["scope"], "doc_type": d["type"], "confidence": d["confidence"]} for d in docs]
    edges = []
    for doc in docs:
        for rel in store.get_relations(doc["id"]):
            edges.append({"source": doc["id"], "target": rel["target_id"],
                          "relation_type": rel["rel_type"], "weight": rel["weight"]})
    return {"nodes": nodes, "edges": edges}


@router.get("/entities")
async def get_entity_graph(scope: str = "private", min_weight: float = 0.5):
    return {"nodes": [], "edges": []}


@router.get("/timeline")
async def get_timeline_graph(scope: str = "private"):
    store = _get_store()
    docs = store.list_documents(scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document", "scope": d["scope"]} for d in docs]
    return {"nodes": nodes, "edges": []}


@router.post("/rebuild")
async def rebuild_graph(scope: str | None = None):
    config = KBConfig()
    # 只创建 documents_dir（KuzuGraphStore 自行处理 kuzu_dir 父目录）
    config.documents_dir.mkdir(parents=True, exist_ok=True)
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    from server.kb.storage.repo import DocumentRepo
    repo = DocumentRepo(documents_dir=config.documents_dir)
    count = 0
    for doc_id in repo.list_all():
        fm, _ = repo.read(doc_id)
        if scope and fm.scope != scope:
            continue
        store.add_document(fm.id, fm.title, fm.type, fm.scope, fm.confidence, fm.id)
        count += 1
    return {"success": True, "indexed_count": count}
