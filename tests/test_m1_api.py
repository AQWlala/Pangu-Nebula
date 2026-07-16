# tests/test_m1_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_kb_import_document(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "kb" / "_inbox")

    response = await client.post("/api/kb/import", json={
        "content": "# 测试文档\n\n这是导入的内容",
        "title": "测试文档",
        "type": "note",
        "scope": "private",
        "tags": ["test"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "pending_id" in data

@pytest.mark.asyncio
async def test_kb_list_pending(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "_inbox")

    response = await client.get("/api/kb/inbox")
    assert response.status_code == 200
    data = response.json()
    assert "pending" in data
    assert isinstance(data["pending"], list)

@pytest.mark.asyncio
async def test_kb_approve_document(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "kb" / "_inbox")

    import_resp = await client.post("/api/kb/import", json={
        "content": "# 审核测试",
        "title": "审核测试",
        "type": "note",
        "scope": "private",
    })
    pending_id = import_resp.json()["pending_id"]

    response = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "doc_id" in data

@pytest.mark.asyncio
async def test_kb_list_documents(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "documents")

    response = await client.get("/api/kb/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
