# tests/test_m3_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_graph_documents_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kuzu_dir", tmp_path / "kuzu")
    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_graph_rebuild_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "kuzu_dir", tmp_path / "kb" / "indexes" / "kuzu")
    response = await client.post("/api/graph/rebuild", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_relation_extractor_recommend():
    from server.kb.graph.relation_extractor import RelationExtractor
    extractor = RelationExtractor()
    recommendations = extractor.recommend_relations(
        doc_id="kb-001",
        similar_docs=[
            {"doc_id": "kb-002", "title": "相关文档", "score": 0.85},
            {"doc_id": "kb-003", "title": "扩展文档", "score": 0.75},
        ],
    )
    assert len(recommendations) > 0
    assert all(r.confidence > 0 for r in recommendations)
