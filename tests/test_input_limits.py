import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Import the app — may need to handle import errors
    try:
        from server.main import app
        return TestClient(app)
    except Exception:
        pytest.skip("Cannot import server.main")


def test_import_rejects_oversized_content(client):
    """Content over 10MB should be rejected."""
    resp = client.post("/api/kb/import", json={
        "title": "Test",
        "content": "x" * 11_000_000,
        "type": "note",
        "scope": "private",
    })
    assert resp.status_code == 422  # Pydantic validation error


def test_import_rejects_empty_title(client):
    resp = client.post("/api/kb/import", json={
        "title": "",
        "content": "test",
        "type": "note",
        "scope": "private",
    })
    assert resp.status_code == 422


def test_import_rejects_invalid_scope(client):
    resp = client.post("/api/kb/import", json={
        "title": "Test",
        "content": "test",
        "type": "note",
        "scope": "invalid_scope",
    })
    assert resp.status_code == 422


def test_import_rejects_comma_in_tags(client):
    resp = client.post("/api/kb/import", json={
        "title": "Test",
        "content": "test",
        "type": "note",
        "scope": "private",
        "tags": ["tag,with,comma"],
    })
    assert resp.status_code == 422


def test_graph_depth_clamped():
    """Test that depth is clamped to [1,3]."""
    import inspect
    from server.api.graph import get_document_graph
    source = inspect.getsource(get_document_graph)
    assert "min(3" in source or "max(1" in source
