# tests/test_m3_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def kb_graph_setup(tmp_path, monkeypatch):
    """Isolated KB config + graph store for graph API tests.

    Uses the constructor pattern ``KBConfig(kb_root=tmp_path / "kb")`` instead
    of monkeypatching class attributes, which fails for dataclass fields
    declared with ``field(default_factory=...)`` — e.g. ``kb_root`` has no
    class-level attribute so ``monkeypatch.setattr(KBConfig, "kb_root", ...)``
    raises ``AttributeError``.
    """
    from server.config_kb_cu import KBConfig
    from server.kb.graph.kuzu_store import KuzuGraphStore

    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    # Patch the service-layer config factory so get_document_repo /
    # get_inbox_writer / get_vector_store (which call get_kb_config() by
    # name at call-time) all resolve to tmp_path.
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda *a, **kw: config)

    # get_graph_store checks app.state.graph_store first; inject a pre-built
    # store so all graph endpoints share the same tmp_path DB.  Patching
    # server.kb.service.get_graph_store would NOT work because Depends() in
    # server.api.graph already captured the original function object at
    # module-import time.
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    app.state.graph_store = store
    try:
        yield config, store
    finally:
        if hasattr(app.state, "graph_store"):
            del app.state.graph_store


@pytest.mark.asyncio
async def test_graph_documents_endpoint(client, kb_graph_setup):
    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_graph_rebuild_endpoint(client, kb_graph_setup):
    response = await client.post("/api/graph/rebuild", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_graph_entities_endpoint(client, kb_graph_setup):
    """GET /api/graph/entities returns entity graph shape."""
    response = await client.get("/api/graph/entities", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_graph_timeline_endpoint(client, kb_graph_setup):
    """GET /api/graph/timeline returns timeline nodes from the store."""
    _, store = kb_graph_setup
    store.add_document("kb-tl-001", "Timeline Doc", "note", "private", 0.9, "doc.md")
    response = await client.get("/api/graph/timeline", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "kb-tl-001"


@pytest.mark.asyncio
async def test_graph_rebuild_endpoint_full(client, kb_graph_setup):
    """POST /api/graph/rebuild rebuilds graph from documents and verifies data enters the graph."""
    from server.kb.storage.frontmatter import FrontMatter
    from server.kb.storage.repo import DocumentRepo

    config, _ = kb_graph_setup
    repo = DocumentRepo(documents_dir=config.documents_dir)

    # 3 documents with overlapping tags to produce relations (Jaccard >= 0.5)
    fm1 = FrontMatter(
        id="kb-rebuild-001", title="Python Basics", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc1", tags=["python", "ai", "ml"],
    )
    fm2 = FrontMatter(
        id="kb-rebuild-002", title="Advanced Python", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc2", tags=["python", "ai", "data"],
    )
    fm3 = FrontMatter(
        id="kb-rebuild-003", title="Python NLP", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc3", tags=["python", "ml", "nlp"],
    )
    repo.save(fm1, "Python basics content")
    repo.save(fm2, "Advanced Python content")
    repo.save(fm3, "Python NLP content")

    # Call rebuild
    response = await client.post("/api/graph/rebuild", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["indexed_count"] == 3
    assert data["relation_count"] > 0

    # Verify all 3 documents appear as nodes
    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert node_ids == {"kb-rebuild-001", "kb-rebuild-002", "kb-rebuild-003"}


@pytest.mark.asyncio
async def test_graph_documents_empty(client, kb_graph_setup):
    """GET /api/graph/documents with no documents returns empty response (not 404)."""
    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == []
    assert data["edges"] == []


@pytest.mark.asyncio
async def test_graph_documents_scope_filter(client, kb_graph_setup):
    """GET /api/graph/documents?scope=private returns only private docs."""
    _, store = kb_graph_setup
    store.add_document("kb-scope-001", "Private Doc 1", "note", "private", 0.9, "d1.md")
    store.add_document("kb-scope-002", "Private Doc 2", "note", "private", 0.9, "d2.md")
    store.add_document("kb-scope-003", "Public Doc", "note", "public", 0.9, "d3.md")

    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert "kb-scope-001" in node_ids
    assert "kb-scope-002" in node_ids
    assert "kb-scope-003" not in node_ids


def test_relation_extractor_recommend():
    from server.kb.graph.relation_extractor import RelationExtractor
    from server.kb.storage.frontmatter import FrontMatter
    extractor = RelationExtractor()
    source = FrontMatter(
        id="kb-001", title="源文档", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc1", tags=["python", "ai", "ml"],
    )
    candidates = [
        FrontMatter(
            id="kb-002", title="相关文档", type="note",
            scope="private", source_type="manual", confidence=0.9,
            checksum="sha256:abc2", tags=["python", "ai", "data"],
        ),
        FrontMatter(
            id="kb-003", title="扩展文档", type="note",
            scope="private", source_type="manual", confidence=0.9,
            checksum="sha256:abc3", tags=["python", "ml", "nlp"],
        ),
    ]
    recommendations = extractor.recommend_relations(source, candidates)
    assert len(recommendations) > 0
    assert all(r.confidence > 0 for r in recommendations)
