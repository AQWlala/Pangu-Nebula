# tests/test_async_optimization.py
"""P4+Q3 — async optimization and kb/service.py Depends() tests.

Tests:
1. get_vector_store returns the same instance from app.state (Depends singleton)
2. get_vector_store falls back to per-request construction when app.state is empty
3. _cleanup_old_tasks() removes tasks older than 24h
4. _cleanup_old_tasks() keeps recent tasks
5. Async endpoints use asyncio.to_thread for sync I/O (verified via thread identity)
"""
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from server.main import app


# ---------------------------------------------------------------------------
# Helper: lightweight mock Request for unit-testing Depends() callables.
# Unlike MagicMock (which auto-creates attributes), this only exposes what
# we explicitly set — so getattr(..., "vector_store", None) correctly
# returns None when the attribute is absent.
# ---------------------------------------------------------------------------

class _MockState:
    pass


class _MockApp:
    def __init__(self):
        self.state = _MockState()


class _MockRequest:
    def __init__(self):
        self.app = _MockApp()


def _clear_app_state_singletons():
    """Remove KB singleton stores from app.state to avoid cross-test pollution."""
    for attr in ("vector_store", "graph_store", "kb_config"):
        if hasattr(app.state, attr):
            try:
                delattr(app.state, attr)
            except (AttributeError, KeyError):
                pass


# ---------------------------------------------------------------------------
# Test 1: get_vector_store returns the singleton from app.state
# ---------------------------------------------------------------------------

def test_get_vector_store_returns_singleton_from_app_state(tmp_path):
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.service import get_vector_store

    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    request = _MockRequest()
    request.app.state.vector_store = store

    result = get_vector_store(request)
    assert result is store, "Should return the exact same instance from app.state"


# ---------------------------------------------------------------------------
# Test 2: get_vector_store falls back to per-request construction
# ---------------------------------------------------------------------------

def test_get_vector_store_falls_back_to_per_request_construction(tmp_path, monkeypatch):
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.service import get_vector_store
    from server.config_kb_cu import KBConfig

    # Build a config pointing at tmp_path and patch get_kb_config so the
    # fallback path uses tmp_path instead of ~/.pangu-nebula.
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda: config)

    request = _MockRequest()
    # _MockState has no vector_store attribute → fallback path triggers

    result = get_vector_store(request)
    assert isinstance(result, ChromaVectorStore)
    assert result.persist_dir == config.chroma_dir


# ---------------------------------------------------------------------------
# Test 3: _cleanup_old_tasks removes tasks older than 24h
# ---------------------------------------------------------------------------

def test_cleanup_old_tasks_removes_expired():
    from server.api.cu import _cleanup_old_tasks, _tasks

    # Save and restore _tasks to avoid polluting other tests
    original = dict(_tasks)
    _tasks.clear()
    try:
        _tasks["old-25h"] = {
            "task_id": "old-25h",
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat() + "Z",
            "status": "completed",
        }
        _tasks["old-48h"] = {
            "task_id": "old-48h",
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat() + "Z",
            "status": "completed",
        }

        _cleanup_old_tasks()

        assert "old-25h" not in _tasks, "25h-old task should be removed"
        assert "old-48h" not in _tasks, "48h-old task should be removed"
    finally:
        _tasks.clear()
        _tasks.update(original)


# ---------------------------------------------------------------------------
# Test 4: _cleanup_old_tasks keeps recent tasks
# ---------------------------------------------------------------------------

def test_cleanup_old_tasks_keeps_recent():
    from server.api.cu import _cleanup_old_tasks, _tasks

    original = dict(_tasks)
    _tasks.clear()
    try:
        _tasks["just-created"] = {
            "task_id": "just-created",
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
            "status": "created",
        }
        _tasks["1h-old"] = {
            "task_id": "1h-old",
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat() + "Z",
            "status": "executing",
        }
        _tasks["23h-old"] = {
            "task_id": "23h-old",
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat() + "Z",
            "status": "completed",
        }

        _cleanup_old_tasks()

        assert "just-created" in _tasks, "Just-created task should be kept"
        assert "1h-old" in _tasks, "1h-old task should be kept (within 24h TTL)"
        assert "23h-old" in _tasks, "23h-old task should be kept (within 24h TTL)"
    finally:
        _tasks.clear()
        _tasks.update(original)


# ---------------------------------------------------------------------------
# Test 5: Async endpoints use asyncio.to_thread for sync I/O
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_endpoint_runs_io_in_worker_thread(tmp_path, monkeypatch):
    """Verify that inbox.stage() is dispatched to a worker thread via asyncio.to_thread."""
    from server.config_kb_cu import KBConfig
    from server.kb.storage.inbox import InboxWriter

    # Point get_kb_config at tmp_path so no writes hit ~/.pangu-nebula
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda: config)

    # Ensure no stale lifespan singletons interfere
    _clear_app_state_singletons()

    main_thread_id = threading.get_ident()
    captured_thread_ids: list[int] = []
    original_stage = InboxWriter.stage

    def _tracking_stage(self, *args, **kwargs):
        captured_thread_ids.append(threading.get_ident())
        return original_stage(self, *args, **kwargs)

    try:
        with patch.object(InboxWriter, "stage", _tracking_stage):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/kb/import", json={
                    "content": "# Async Test\n\nContent for thread verification.",
                    "title": "Async Test Doc",
                    "type": "note",
                    "scope": "private",
                })

        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}: {response.text}"
        assert len(captured_thread_ids) > 0, "inbox.stage() should have been called"
        for tid in captured_thread_ids:
            assert tid != main_thread_id, \
                "inbox.stage() must run in a worker thread, not the event loop thread"
    finally:
        _clear_app_state_singletons()
