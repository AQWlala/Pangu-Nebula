# tests/test_m2_api.py
import pytest
from httpx import AsyncClient, ASGITransport

# chromadb 是可选依赖（搜索端点需要），未安装时跳过
pytest.importorskip("chromadb")

from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_search_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda *a, **kw: config)

    import_resp = await client.post("/api/kb/import", json={
        "content": "# Python 编程\n\nPython 是一门编程语言",
        "title": "Python 编程", "type": "note", "scope": "private", "tags": ["python"],
    })
    pending_id = import_resp.json()["pending_id"]
    await client.post(f"/api/kb/inbox/{pending_id}/approve")

    response = await client.get("/api/kb/search", params={"query": "Python", "scope": "private", "top_k": 5})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
