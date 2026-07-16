# tests/test_e2e_kb.py
"""T5 — KB 全链路端到端集成测试

验证知识库文档的完整生命周期：
  import → approve → search → graph rebuild

关键约束：
- 使用 tmp_path fixture，绝不写入用户 home 目录。
- 通过构造器模式 KBConfig(kb_root=tmp_path / "kb")。
- Monkeypatch server.kb.service.get_kb_config 使其返回测试配置。
- 使用 app.dependency_overrides 覆盖 Depends(get_kb_config)。
- 设置 app.state.graph_store / vector_store 指向 tmp_path 的实例。
"""
import pytest
from httpx import AsyncClient, ASGITransport

from server.main import app
from server.config_kb_cu import KBConfig


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def kb_env(tmp_path, monkeypatch):
    """Set up KB config + stores pointing to tmp_path.

    - Patches server.kb.service.get_kb_config for internal calls in
      get_document_repo / get_inbox_writer / get_vector_store.
    - Uses app.dependency_overrides to override Depends(get_kb_config)
      in the approve endpoint (Depends captures the function object at
      import time, so monkeypatching the module attr is not enough).
    - Sets app.state.graph_store for get_graph_store (which uses
      KBConfig() directly, not get_kb_config()).
    - Sets app.state.vector_store for get_vector_store consistency.
    """
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()

    # 1. Patch get_kb_config in service module for internal calls
    import server.kb.service as service_module
    monkeypatch.setattr(service_module, "get_kb_config", lambda: config)

    # 2. Override Depends(get_kb_config) for the approve endpoint
    import server.api.kb as kb_module
    _original_get_kb_config = kb_module.get_kb_config
    app.dependency_overrides[_original_get_kb_config] = lambda: config

    # 3. Set up graph store singleton (get_graph_store uses KBConfig() directly)
    from server.kb.graph.kuzu_store import KuzuGraphStore
    graph_store = KuzuGraphStore(db_dir=config.kuzu_dir)
    graph_store.init_schema()
    app.state.graph_store = graph_store

    # 4. Set up vector store singleton
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    vector_store = ChromaVectorStore(persist_dir=config.chroma_dir)
    app.state.vector_store = vector_store

    yield config

    # Cleanup singletons and overrides
    graph_store.close()
    vector_store.close()
    app.dependency_overrides.pop(_original_get_kb_config, None)
    if hasattr(app.state, "graph_store"):
        del app.state.graph_store
    if hasattr(app.state, "vector_store"):
        del app.state.vector_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _import_doc(client, title, content, tags):
    """Import a document and return the pending_id."""
    resp = await client.post("/api/kb/import", json={
        "content": content,
        "title": title,
        "type": "note",
        "scope": "private",
        "tags": tags,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["pending_id"]


async def _approve_doc(client, pending_id):
    """Approve a pending document and return the doc_id."""
    resp = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    assert resp.status_code == 200, resp.text
    return resp.json()["doc_id"]


# ---------------------------------------------------------------------------
# Test: KB full flow — import → approve → search → graph rebuild
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_full_flow_import_approve_search_graph(client, kb_env):
    """KB 全链路：import → approve → search → graph rebuild。"""
    documents = [
        {
            "title": "Python 基础教程",
            "content": "# Python 基础教程\n\nPython 是一门简洁优雅的编程语言，适合初学者入门编程。",
            "tags": ["python", "programming", "tutorial"],
        },
        {
            "title": "Python 进阶编程",
            "content": "# Python 进阶编程\n\n深入探讨 Python 的高级特性与编程最佳实践。",
            "tags": ["python", "programming", "advanced"],
        },
        {
            "title": "Python 实战指南",
            "content": "# Python 实战指南\n\n通过实际项目掌握 Python 编程技巧与工程实践。",
            "tags": ["python", "programming", "guide"],
        },
    ]

    # ------------------------------------------------------------------
    # Step 1: POST /api/kb/import — 导入 3 篇带重叠 tags 的文档
    # ------------------------------------------------------------------
    pending_ids = []
    for doc in documents:
        pid = await _import_doc(client, doc["title"], doc["content"], doc["tags"])
        pending_ids.append(pid)
    assert len(pending_ids) == 3

    # ------------------------------------------------------------------
    # Step 2: GET /api/kb/inbox — 查看待审核文档
    # ------------------------------------------------------------------
    inbox_resp = await client.get("/api/kb/inbox")
    assert inbox_resp.status_code == 200
    pending_list = inbox_resp.json()["pending"]
    assert len(pending_list) == 3, f"应有 3 个待审核项，实际 {len(pending_list)}"

    # ------------------------------------------------------------------
    # Step 3: POST /api/kb/inbox/{id}/approve — 审批通过
    # ------------------------------------------------------------------
    doc_ids = []
    for pid in pending_ids:
        doc_id = await _approve_doc(client, pid)
        doc_ids.append(doc_id)
    assert len(doc_ids) == 3

    # ------------------------------------------------------------------
    # Step 4: GET /api/kb/search — 搜索文档
    # ------------------------------------------------------------------
    search_resp = await client.get("/api/kb/search", params={
        "query": "Python",
        "scope": "private",
        "top_k": 10,
    })
    assert search_resp.status_code == 200, search_resp.text
    results = search_resp.json()["results"]
    found_ids = {r["doc_id"] for r in results}
    # 至少有一篇文档被搜索到
    assert len(found_ids & set(doc_ids)) >= 1, \
        f"搜索应找到已审批的文档，found={found_ids}, approved={set(doc_ids)}"

    # ------------------------------------------------------------------
    # Step 5: POST /api/graph/rebuild — 重建图谱
    # ------------------------------------------------------------------
    rebuild_resp = await client.post("/api/graph/rebuild", params={"scope": "private"})
    assert rebuild_resp.status_code == 200, rebuild_resp.text
    rebuild_data = rebuild_resp.json()
    assert rebuild_data["success"] is True
    assert rebuild_data["indexed_count"] == 3, \
        f"应索引 3 个文档，实际 {rebuild_data['indexed_count']}"
    # 重叠 tags (Jaccard >= 0.5) 应产生至少 1 条关系
    assert rebuild_data["relation_count"] >= 1, \
        f"重叠 tags 应产生至少 1 条关系，实际 {rebuild_data['relation_count']}"

    # ------------------------------------------------------------------
    # Step 6: GET /api/graph/documents — 验证图谱节点与边
    # ------------------------------------------------------------------
    graph_resp = await client.get("/api/graph/documents", params={
        "scope": "private",
        "depth": 2,
    })
    assert graph_resp.status_code == 200, graph_resp.text
    graph_data = graph_resp.json()
    nodes = graph_data["nodes"]
    edges = graph_data["edges"]

    # 3 个文档都应作为节点出现
    node_ids = {n["id"] for n in nodes}
    assert len(node_ids & set(doc_ids)) == 3, \
        f"3 个文档都应作为图谱节点，node_ids={node_ids}, doc_ids={set(doc_ids)}"

    # 至少有 1 条边
    assert len(edges) >= 1, f"应至少有 1 条关系边，实际 {len(edges)}"

    # 边的 source/target 应在已审批的文档 ID 范围内
    for edge in edges:
        assert edge["source"] in node_ids, \
            f"边的 source {edge['source']} 不在节点集合中"
        assert edge["target"] in node_ids, \
            f"边的 target {edge['target']} 不在节点集合中"


@pytest.mark.asyncio
async def test_kb_search_empty_query_returns_400(client, kb_env):
    """空查询应返回 400。"""
    resp = await client.get("/api/kb/search", params={"query": "", "scope": "private"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_kb_approve_nonexistent_returns_404(client, kb_env):
    """审批不存在的 pending_id 应返回 404。"""
    # pending_id format: pending-YYYYMMDDHHMMSS-XXXXXXXX
    resp = await client.post("/api/kb/inbox/pending-20000101000000-00000000/approve")
    assert resp.status_code == 404
