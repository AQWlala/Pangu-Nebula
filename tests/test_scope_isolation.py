# tests/test_scope_isolation.py
"""T4 — scope 隔离测试

验证 S2 给 ``list_documents`` / ``get_document`` / ``delete_document`` 增加的
``scope`` 过滤参数能正确隔离 ``private`` / ``project`` / ``public`` 三类文档，
防止跨 scope 泄漏或误删。

关键约束：
- 使用 ``tmp_path`` fixture，绝不写入用户 home 目录。
- 因 A1 对 ``KBConfig.__post_init__`` 的调整，``kb_root`` 使用
  ``field(default_factory=...)``，``monkeypatch.setattr(KBConfig, "kb_root", ...)``
  会抛 ``AttributeError``。故遵循 ``tests/test_config_fix.py`` 的构造器模式：
  ``KBConfig(kb_root=tmp_path / "kb")``，并 monkeypatch ``server.kb.service.get_kb_config``
  （P4+Q3 后配置函数由 ``server.api.kb._get_config`` 迁至此处）使其返回该实例。
"""
import pytest
from httpx import AsyncClient, ASGITransport

from server.main import app
from server.config_kb_cu import KBConfig


@pytest.fixture
async def client():
    """异步测试客户端，与 ``test_m1_api.py`` 保持一致的写法。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def kb_config(tmp_path, monkeypatch):
    """将 KB 路径重定向到 tmp_path，遵循构造器模式（见 test_config_fix.py）。

    通过 monkeypatch ``server.kb.service.get_kb_config``（P4+Q3 后由
    ``server.api.kb._get_config`` 迁至此处）让所有端点使用同一个
    指向 tmp_path 的 KBConfig 实例，避免触及用户 home 目录。
    """
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    monkeypatch.setattr("server.kb.service.get_kb_config", lambda: config)
    return config


async def _import_and_approve(client, scope: str, title: str) -> str:
    """导入一篇指定 scope 的文档并审批通过，返回 doc_id。"""
    resp = await client.post("/api/kb/import", json={
        "content": f"# {title}\n\n正文内容 {title}",
        "title": title,
        "type": "note",
        "scope": scope,
    })
    assert resp.status_code == 200, resp.text
    pending_id = resp.json()["pending_id"]

    approve_resp = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    assert approve_resp.status_code == 200, approve_resp.text
    return approve_resp.json()["doc_id"]


# ---------------------------------------------------------------------------
# Test 1-3: list_documents 按 scope 过滤
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_documents_scope_private(client, kb_config):
    """scope=private 只返回 private 文档。"""
    priv_id = await _import_and_approve(client, "private", "私有文档")
    await _import_and_approve(client, "project", "项目文档")
    await _import_and_approve(client, "public", "公开文档")

    resp = await client.get("/api/kb/documents?scope=private")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    scopes = {d["scope"] for d in docs}
    assert scopes == {"private"}, f"应仅含 private，实际: {scopes}"
    ids = {d["id"] for d in docs}
    assert priv_id in ids


@pytest.mark.asyncio
async def test_list_documents_scope_project(client, kb_config):
    """scope=project 只返回 project 文档。"""
    await _import_and_approve(client, "private", "私有文档")
    proj_id = await _import_and_approve(client, "project", "项目文档")
    await _import_and_approve(client, "public", "公开文档")

    resp = await client.get("/api/kb/documents?scope=project")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    scopes = {d["scope"] for d in docs}
    assert scopes == {"project"}, f"应仅含 project，实际: {scopes}"
    ids = {d["id"] for d in docs}
    assert proj_id in ids


@pytest.mark.asyncio
async def test_list_documents_scope_public(client, kb_config):
    """scope=public 只返回 public 文档。"""
    await _import_and_approve(client, "private", "私有文档")
    await _import_and_approve(client, "project", "项目文档")
    pub_id = await _import_and_approve(client, "public", "公开文档")

    resp = await client.get("/api/kb/documents?scope=public")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    scopes = {d["scope"] for d in docs}
    assert scopes == {"public"}, f"应仅含 public，实际: {scopes}"
    ids = {d["id"] for d in docs}
    assert pub_id in ids


# ---------------------------------------------------------------------------
# Test 4: 不带 scope 返回全部（向后兼容）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_documents_no_scope_returns_all(client, kb_config):
    """不带 scope 参数返回全部文档（向后兼容）。"""
    await _import_and_approve(client, "private", "私有文档")
    await _import_and_approve(client, "project", "项目文档")
    await _import_and_approve(client, "public", "公开文档")

    resp = await client.get("/api/kb/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    scopes = {d["scope"] for d in docs}
    assert scopes == {"private", "project", "public"}, f"应含三种 scope，实际: {scopes}"
    assert len(docs) == 3


# ---------------------------------------------------------------------------
# Test 5-6: get_document 的 scope 校验
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_document_mismatched_scope_returns_404(client, kb_config):
    """get_document 用不匹配的 scope 查询应返回 404，防止跨 scope 泄漏。"""
    priv_id = await _import_and_approve(client, "private", "私有文档")

    resp = await client.get(f"/api/kb/documents/{priv_id}?scope=public")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_document_matching_scope_returns_200(client, kb_config):
    """get_document 用匹配的 scope 查询应返回 200。"""
    priv_id = await _import_and_approve(client, "private", "私有文档")

    resp = await client.get(f"/api/kb/documents/{priv_id}?scope=private")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == priv_id
    assert data["scope"] == "private"


# ---------------------------------------------------------------------------
# Test 7: delete_document 的 scope 校验（防止跨 scope 误删）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_document_mismatched_scope_returns_404(client, kb_config):
    """delete_document 用不匹配的 scope 应返回 404，且文档不被删除。"""
    priv_id = await _import_and_approve(client, "private", "私有文档")

    # 用 public scope 尝试删除 private 文档 —— 应被拒绝
    resp = await client.delete(f"/api/kb/documents/{priv_id}?scope=public")
    assert resp.status_code == 404

    # 文档应仍然存在（用匹配的 scope 或不带 scope 验证）
    verify_resp = await client.get(f"/api/kb/documents/{priv_id}?scope=private")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["id"] == priv_id
