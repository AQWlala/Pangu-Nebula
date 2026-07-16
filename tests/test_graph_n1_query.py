# tests/test_graph_n1_query.py
"""验证 KuzuGraphStore.get_all_relations 单查询消除 N+1，以及 graph API 响应格式未变。"""
import pytest
from httpx import ASGITransport, AsyncClient

# kuzu 是可选依赖，未安装时跳过而非报错
pytest.importorskip("kuzu")

from server.kb.graph.kuzu_store import KuzuGraphStore
from server.main import app


@pytest.fixture
def store(tmp_path):
    s = KuzuGraphStore(db_dir=tmp_path / "kuzu")
    s.init_schema()
    return s


def _seed_three_docs(store: KuzuGraphStore) -> None:
    """写入 3 个文档（2 个 private + 1 个 public），并建立 2 条 private 关系。"""
    store.add_document("kb-n1-001", "文档一", "note", "private", 0.9, "doc1.md")
    store.add_document("kb-n1-002", "文档二", "note", "private", 0.8, "doc2.md")
    store.add_document("kb-n1-003", "文档三", "note", "private", 0.7, "doc3.md")
    store.add_document("kb-n1-004", "公开文档", "note", "public", 0.6, "doc4.md")
    store.add_relation("kb-n1-001", "kb-n1-002", "References", 0.85)
    store.add_relation("kb-n1-002", "kb-n1-003", "Extends", 0.7)


def test_get_all_relations_returns_all_in_single_query(store):
    """Test 1: get_all_relations() 一次返回全部关系。"""
    _seed_three_docs(store)
    rels = store.get_all_relations()
    assert len(rels) == 2, f"应返回 2 条关系，实际 {len(rels)}"

    # 字段完整性
    required_keys = {
        "source_doc_id", "source_title", "relation_type",
        "confidence", "target_doc_id", "target_title",
    }
    for r in rels:
        assert required_keys.issubset(r.keys()), f"缺少字段: {required_keys - set(r.keys())}"

    pairs = {(r["source_doc_id"], r["target_doc_id"], r["relation_type"]) for r in rels}
    assert ("kb-n1-001", "kb-n1-002", "References") in pairs
    assert ("kb-n1-002", "kb-n1-003", "Extends") in pairs

    # title 也被正确返回
    title_map = {(r["source_doc_id"], r["target_doc_id"]): (r["source_title"], r["target_title"]) for r in rels}
    assert title_map[("kb-n1-001", "kb-n1-002")] == ("文档一", "文档二")


def test_get_all_relations_filters_by_scope(store):
    """Test 2: scope='private' 时仅返回 private 关系。"""
    _seed_three_docs(store)
    # public 文档与 private 文档之间建立一条 cross-scope 关系
    store.add_relation("kb-n1-001", "kb-n1-004", "References", 0.5)

    all_rels = store.get_all_relations()
    assert len(all_rels) == 3, "无 scope 过滤时应包含跨 scope 关系"

    private_rels = store.get_all_relations(scope="private")
    assert len(private_rels) == 2, f"scope=private 应只返回 2 条，实际 {len(private_rels)}"
    for r in private_rels:
        assert r["source_doc_id"].startswith("kb-n1-00")
        assert r["target_doc_id"] != "kb-n1-004", "不应包含 public 目标"


def test_get_all_relations_empty_graph_returns_empty(store):
    """Test 3: 空图返回空列表。"""
    rels = store.get_all_relations()
    assert rels == []
    rels_scoped = store.get_all_relations(scope="private")
    assert rels_scoped == []


@pytest.mark.asyncio
async def test_get_document_graph_response_shape_unchanged(store, tmp_path, monkeypatch):
    """Test 4: 重构后 /api/graph/documents 响应结构保持向后兼容。"""
    from server.config_kb_cu import KBConfig

    _seed_three_docs(store)

    # 让 _get_graph_store 复用已 seed 好的 store，避免重新初始化空库
    monkeypatch.setattr(KBConfig, "kuzu_dir", tmp_path / "kuzu")
    app.state.graph_store = store
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/graph/documents", params={"scope": "private"})
        assert response.status_code == 200
        data = response.json()

        # 向后兼容：必须包含 nodes 和 edges
        assert "nodes" in data
        assert "edges" in data

        # nodes 字段结构
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) == 3, "private scope 应有 3 个文档节点"
        node_keys = set(data["nodes"][0].keys())
        assert {"id", "label", "type", "scope", "doc_type", "confidence"}.issubset(node_keys)

        # edges 字段结构与重构前一致：source/target/relation_type/weight
        assert isinstance(data["edges"], list)
        assert len(data["edges"]) == 2, f"应有 2 条边，实际 {len(data['edges'])}"
        edge_keys = set(data["edges"][0].keys())
        assert {"source", "target", "relation_type", "weight"}.issubset(edge_keys)

        edge_pairs = {(e["source"], e["target"], e["relation_type"]) for e in data["edges"]}
        assert ("kb-n1-001", "kb-n1-002", "References") in edge_pairs
        assert ("kb-n1-002", "kb-n1-003", "Extends") in edge_pairs
    finally:
        # 清理 app.state，避免污染其它测试
        if hasattr(app.state, "graph_store"):
            del app.state.graph_store
