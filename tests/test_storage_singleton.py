# tests/test_storage_singleton.py
"""P1 — Singleton-ize ChromaVectorStore / KuzuGraphStore in app.state.

Tests:
1. lifespan startup initializes app.state.vector_store & app.state.graph_store
2. Multiple requests reuse the same store instances (no per-request construction)
3. lifespan shutdown calls close() on the singleton stores
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def kb_config(tmp_path):
    """A KBConfig pointing at tmp_path instead of the real home directory."""
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    return config


@pytest.fixture
def clean_app_state(kb_config, monkeypatch):
    """Inject a tmp_path KBConfig into app.state and clean up afterwards.

    - Mocks init_db to avoid real database side effects during lifespan.
    - Mocks ChromaVectorStore/KuzuGraphStore __init__ to avoid requiring
      chromadb/kuzu optional dependencies — the test verifies singleton
      lifecycle logic, not store internals.
    - Pre-sets app.state.kb_config so lifespan uses tmp_path, not ~/.pangu-nebula.
    - Tears down app.state.vector_store / graph_store / kb_config after each test
      so other tests (which bypass lifespan) fall back to per-request construction.
    """
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.graph.kuzu_store import KuzuGraphStore

    # Mock __init__ so instantiation doesn't require chromadb/kuzu.
    # Set minimal internal attributes so downstream method calls don't crash.
    def _mock_vs_init(self, **kw):
        self._client = None
        self._collection = None

    def _mock_gs_init(self, **kw):
        self._conn = None
        self._db = None

    monkeypatch.setattr(ChromaVectorStore, "__init__", _mock_vs_init)
    monkeypatch.setattr(KuzuGraphStore, "__init__", _mock_gs_init)
    monkeypatch.setattr(KuzuGraphStore, "init_schema", lambda self: None)
    # Mock DB-querying methods to return empty results (avoids needing kuzu)
    monkeypatch.setattr(KuzuGraphStore, "list_documents", lambda self, **kw: [])
    monkeypatch.setattr(KuzuGraphStore, "get_all_relations", lambda self, **kw: [])

    async def _noop_init_db():
        pass

    monkeypatch.setattr("server.main.init_db", _noop_init_db)
    monkeypatch.setattr(app.state, "kb_config", kb_config, raising=False)
    # Clear any stale singleton stores left over from a previous test/run
    for _attr in ("vector_store", "graph_store"):
        if hasattr(app.state, _attr):
            delattr(app.state, _attr)
    yield
    # Remove singleton stores so later tests (which bypass lifespan) fall back
    # to per-request construction. kb_config is owned by monkeypatch and will
    # be restored by its teardown — do not delete it here.
    for _attr in ("vector_store", "graph_store"):
        if hasattr(app.state, _attr):
            try:
                delattr(app.state, _attr)
            except (AttributeError, KeyError):
                pass


# ---------------------------------------------------------------------------
# Test 1: lifespan startup initializes the singleton stores
# ---------------------------------------------------------------------------

def test_lifespan_initializes_stores(clean_app_state):
    with TestClient(app) as client:
        assert hasattr(app.state, "vector_store")
        assert hasattr(app.state, "graph_store")
        assert app.state.vector_store is not None
        assert app.state.graph_store is not None

        from server.kb.retrieval.vectorstore import ChromaVectorStore
        from server.kb.graph.kuzu_store import KuzuGraphStore
        assert isinstance(app.state.vector_store, ChromaVectorStore)
        assert isinstance(app.state.graph_store, KuzuGraphStore)


# ---------------------------------------------------------------------------
# Test 2: multiple requests reuse the same store instances
# ---------------------------------------------------------------------------

def test_requests_reuse_same_store(clean_app_state):
    with TestClient(app) as client:
        vs_id_before = id(app.state.vector_store)
        gs_id_before = id(app.state.graph_store)

        # Two requests to the graph endpoint — must not create new stores
        r1 = client.get("/api/graph/documents", params={"scope": "private"})
        r2 = client.get("/api/graph/documents", params={"scope": "private"})
        assert r1.status_code == 200
        assert r2.status_code == 200

        # Same store instances reused across requests
        assert id(app.state.vector_store) == vs_id_before
        assert id(app.state.graph_store) == gs_id_before


def test_requests_do_not_construct_new_stores(clean_app_state):
    """No new ChromaVectorStore/KuzuGraphStore instances during requests."""
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.graph.kuzu_store import KuzuGraphStore
    from unittest.mock import MagicMock

    with TestClient(app) as client:
        # Replace __init__ with a no-op mock to count calls.
        # No wraps — original __init__ requires chromadb/kuzu which may be absent.
        with patch.object(ChromaVectorStore, "__init__",
                          return_value=None) as vs_init, \
             patch.object(KuzuGraphStore, "__init__",
                          return_value=None) as gs_init:
            client.get("/api/graph/documents", params={"scope": "private"})
            client.get("/api/graph/timeline", params={"scope": "private"})

        assert vs_init.call_count == 0, "ChromaVectorStore should not be re-instantiated"
        assert gs_init.call_count == 0, "KuzuGraphStore should not be re-instantiated"


# ---------------------------------------------------------------------------
# Test 3: lifespan shutdown calls close() on the singleton stores
# ---------------------------------------------------------------------------

def test_shutdown_calls_close(clean_app_state):
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.graph.kuzu_store import KuzuGraphStore

    with patch.object(ChromaVectorStore, "close") as vs_close_mock, \
         patch.object(KuzuGraphStore, "close") as gs_close_mock:
        with TestClient(app) as client:
            # Stores exist during lifespan
            assert app.state.vector_store is not None
            assert app.state.graph_store is not None
        # Exiting the TestClient context triggers lifespan shutdown

    assert vs_close_mock.called, "ChromaVectorStore.close() was not called on shutdown"
    assert gs_close_mock.called, "KuzuGraphStore.close() was not called on shutdown"
