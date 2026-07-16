# tests/test_m1_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def kb_config(tmp_path, monkeypatch):
    """将 KB 路径重定向到 tmp_path，遵循构造器模式（见 test_config_fix.py）。

    A1 将 ``kb_root`` 改为 ``field(default_factory=...)``，故
    ``monkeypatch.setattr(KBConfig, "kb_root", ...)`` 会抛 ``AttributeError``。
    正确做法：构造 ``KBConfig(kb_root=tmp_path / "kb")`` 并 monkeypatch
    ``server.kb.service.get_kb_config``（P4+Q3 后配置函数迁至此处）使其返回该实例。
    """
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda: config)
    return config


@pytest.mark.asyncio
async def test_kb_import_document(client, kb_config):
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
async def test_kb_list_pending(client, kb_config):
    response = await client.get("/api/kb/inbox")
    assert response.status_code == 200
    data = response.json()
    assert "pending" in data
    assert isinstance(data["pending"], list)

@pytest.mark.asyncio
async def test_kb_approve_document(client, kb_config):
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
async def test_kb_list_documents(client, kb_config):
    response = await client.get("/api/kb/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data


# ---------------------------------------------------------------------------
# T2 — DELETE inbox / GET document / DELETE document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_delete_inbox(client, kb_config):
    """DELETE /api/kb/inbox/{pending_id} 移除待审核文档。"""
    import_resp = await client.post("/api/kb/import", json={
        "content": "# 待删除文档",
        "title": "待删除文档",
        "type": "note",
        "scope": "private",
    })
    pending_id = import_resp.json()["pending_id"]

    # 确认出现在 inbox 列表中
    list_resp = await client.get("/api/kb/inbox")
    assert pending_id in list_resp.json()["pending"]

    # 删除
    delete_resp = await client.delete(f"/api/kb/inbox/{pending_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    # 确认已从 inbox 中移除
    list_resp2 = await client.get("/api/kb/inbox")
    assert pending_id not in list_resp2.json()["pending"]


@pytest.mark.asyncio
async def test_kb_get_document(client, kb_config):
    """GET /api/kb/documents/{doc_id} 返回文档内容。"""
    import_resp = await client.post("/api/kb/import", json={
        "content": "# 获取文档测试\n\n正文内容",
        "title": "获取文档测试",
        "type": "note",
        "scope": "private",
    })
    pending_id = import_resp.json()["pending_id"]
    approve_resp = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    doc_id = approve_resp.json()["doc_id"]

    resp = await client.get(f"/api/kb/documents/{doc_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == doc_id
    assert data["title"] == "获取文档测试"
    assert "content" in data
    assert "正文内容" in data["content"]


@pytest.mark.asyncio
async def test_kb_delete_document(client, kb_config):
    """DELETE /api/kb/documents/{doc_id} 删除已审批文档。"""
    import_resp = await client.post("/api/kb/import", json={
        "content": "# 删除文档测试",
        "title": "删除文档测试",
        "type": "note",
        "scope": "private",
    })
    pending_id = import_resp.json()["pending_id"]
    approve_resp = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    doc_id = approve_resp.json()["doc_id"]

    # 删除
    del_resp = await client.delete(f"/api/kb/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 确认已删除
    get_resp = await client.get(f"/api/kb/documents/{doc_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# T2 — 404 路径
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_get_document_404(client, kb_config):
    """GET /api/kb/documents/nonexistent 返回 404。"""
    resp = await client.get("/api/kb/documents/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kb_delete_document_404(client, kb_config):
    """DELETE /api/kb/documents/nonexistent 返回 404。"""
    resp = await client.delete("/api/kb/documents/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T2 — 输入验证（S4 添加的 Pydantic validators）
# Pydantic v2 的 @field_validator 校验失败由 FastAPI 默认返回 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kb_import_empty_title_rejected(client, kb_config):
    """POST /api/kb/import 空 title 应被拒绝。"""
    resp = await client.post("/api/kb/import", json={
        "content": "内容",
        "title": "",
        "type": "note",
        "scope": "private",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_kb_import_content_too_large_rejected(client, kb_config):
    """POST /api/kb/import content 超过 10MB 应被拒绝。"""
    large_content = "x" * (10_000_001)
    resp = await client.post("/api/kb/import", json={
        "content": large_content,
        "title": "大文档",
        "type": "note",
        "scope": "private",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_kb_import_tags_with_comma_rejected(client, kb_config):
    """POST /api/kb/import tags 含逗号应被拒绝。"""
    resp = await client.post("/api/kb/import", json={
        "content": "内容",
        "title": "逗号标签",
        "type": "note",
        "scope": "private",
        "tags": ["tag,with,comma"],
    })
    assert resp.status_code == 422
