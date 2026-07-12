"""ACP 外部 Agent 适配器测试 (T3.5)

覆盖:
1. 适配器注册表完整(3 个适配器)
2. Claude Code 适配器: 注册 + 调用 memory/swarm/skill + 日志
3. Codex 适配器: 注册 + 调用 memory/swarm/skill
4. Gemini CLI 适配器: 注册 + 调用 memory/swarm/skill
5. 适配器未注册时调用应抛 RuntimeError
6. 适配器 info() 元信息正确
7. get_adapter / list_adapters 工厂函数
8. 适配器管理 API 路由(直接挂载到 FastAPI app)
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.db.orm import Base
# 触发 acp_models 注册到 Base.metadata
from server.db import acp_models  # noqa: F401
from server.services.acp_service import ACPService
from server.services.acp_adapters import (
    ACPAdapter,
    ADAPTER_REGISTRY,
    ClaudeCodeAdapter,
    CodexAdapter,
    GeminiCLIAdapter,
    get_adapter,
    list_adapters,
)
from server.api import acp_adapters as acp_adapters_api


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def adapter_session_factory():
    """创建测试用 session factory,并 patch 到 ACPService 与适配器 API 模块"""
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # patch ACPService 模块中的 async_session
    import server.services.acp_service as acp_mod
    original_svc = acp_mod.async_session
    acp_mod.async_session = session_factory

    # patch 适配器 API 模块中的 _service(共享同一 session factory)
    original_api_service = acp_adapters_api._service
    acp_adapters_api._service = ACPService()

    # 清空适配器缓存
    original_cache = dict(acp_adapters_api._adapter_cache)
    acp_adapters_api._adapter_cache.clear()

    try:
        yield session_factory
    finally:
        acp_mod.async_session = original_svc
        acp_adapters_api._service = original_api_service
        acp_adapters_api._adapter_cache.clear()
        acp_adapters_api._adapter_cache.update(original_cache)
    await engine.dispose()


@pytest.fixture(scope="function")
def adapters_app():
    """构造一个临时 FastAPI app 挂载适配器路由(不修改主 app)"""
    app = FastAPI()
    app.include_router(acp_adapters_api.router)
    return app


# ===== 1. 适配器注册表完整性 =====


def test_adapter_registry_complete():
    """适配器注册表应包含 3 个适配器"""
    assert "claude_code" in ADAPTER_REGISTRY
    assert "codex" in ADAPTER_REGISTRY
    assert "gemini_cli" in ADAPTER_REGISTRY
    assert len(ADAPTER_REGISTRY) >= 3


def test_list_adapters_returns_three():
    """list_adapters 应返回 3 个适配器元信息"""
    adapters = list_adapters()
    names = {a["name"] for a in adapters}
    assert {"claude_code", "codex", "gemini_cli"}.issubset(names)
    for a in adapters:
        assert "display_name" in a
        assert "capabilities" in a
        assert "memory" in a["capabilities"]
        assert "swarm" in a["capabilities"]
        assert "skills" in a["capabilities"]


# ===== 2. Claude Code 适配器 =====


@pytest.mark.asyncio
async def test_claude_code_adapter_register(adapter_session_factory):
    """Claude Code 适配器注册"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    agent = await adapter.register()

    assert agent["id"] is not None
    assert agent["name"] == "Claude Code"
    assert agent["agent_type"] == "claude_code"
    assert agent["endpoint"] == "cli://claude-code"
    assert "memory" in agent["capabilities"]
    assert agent["enabled"] is True
    assert adapter.agent_id == agent["id"]


@pytest.mark.asyncio
async def test_claude_code_adapter_call_memory(adapter_session_factory):
    """Claude Code 适配器调用记忆系统"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    await adapter.register()

    # search
    result = await adapter.call_memory("hello world", action="search")
    assert result["ok"] is True
    assert result["mock"] is True
    assert result["action"] == "search"
    assert result["query"] == "hello world"

    # read
    result = await adapter.call_memory("42", action="read")
    assert result["ok"] is True
    assert result["action"] == "read"

    # write
    result = await adapter.call_memory("new memory", action="write")
    assert result["ok"] is True
    assert result["action"] == "write"


@pytest.mark.asyncio
async def test_claude_code_adapter_call_swarm(adapter_session_factory):
    """Claude Code 适配器调用蜂群"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    await adapter.register()

    result = await adapter.call_swarm(
        "Build a REST API", config={"persona_id": 1, "worker_count": 5}
    )
    assert result["ok"] is True
    assert result["mock"] is True
    assert result["task"] == "Build a REST API"
    assert result["worker_count"] == 5
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_claude_code_adapter_call_skill(adapter_session_factory):
    """Claude Code 适配器调用技能"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    await adapter.register()

    result = await adapter.call_skill("summarizer", input={"text": "hello"})
    assert result["ok"] is True
    assert result["mock"] is True
    assert result["skill"] == "summarizer"


@pytest.mark.asyncio
async def test_claude_code_adapter_logs(adapter_session_factory):
    """Claude Code 适配器获取调用日志"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    await adapter.register()

    # 产生若干调用
    await adapter.call_memory("q1", action="search")
    await adapter.call_swarm("task 1")
    await adapter.call_skill("skill-1")

    logs = await adapter.get_logs(limit=100)
    assert len(logs) == 3
    actions = {log["action"] for log in logs}
    assert "call_memory" in actions
    assert "call_swarm" in actions
    assert "call_skill" in actions


# ===== 3. Codex 适配器 =====


@pytest.mark.asyncio
async def test_codex_adapter_register_and_call(adapter_session_factory):
    """Codex 适配器注册并调用各项能力"""
    service = ACPService()
    adapter = CodexAdapter(service=service)
    agent = await adapter.register()

    assert agent["agent_type"] == "codex"
    assert agent["name"] == "Codex CLI"
    assert agent["endpoint"] == "cli://codex"

    # memory
    mem = await adapter.call_memory("codex query", action="search")
    assert mem["ok"] is True
    assert mem["mock"] is True

    # swarm
    swarm = await adapter.call_swarm("Codex task")
    assert swarm["ok"] is True
    assert swarm["task"] == "Codex task"

    # skill
    skill = await adapter.call_skill("code-review", input={"file": "a.py"})
    assert skill["ok"] is True
    assert skill["skill"] == "code-review"


# ===== 4. Gemini CLI 适配器 =====


@pytest.mark.asyncio
async def test_gemini_cli_adapter_register_and_call(adapter_session_factory):
    """Gemini CLI 适配器注册并调用各项能力"""
    service = ACPService()
    adapter = GeminiCLIAdapter(service=service)
    agent = await adapter.register()

    assert agent["agent_type"] == "gemini_cli"
    assert agent["name"] == "Gemini CLI"
    assert agent["endpoint"] == "cli://gemini"

    # memory
    mem = await adapter.call_memory("gemini query", action="search")
    assert mem["ok"] is True
    assert mem["mock"] is True

    # swarm
    swarm = await adapter.call_swarm("Gemini task")
    assert swarm["ok"] is True
    assert swarm["task"] == "Gemini task"

    # skill
    skill = await adapter.call_skill("json-formatter", input={"data": "{}"})
    assert skill["ok"] is True
    assert skill["skill"] == "json-formatter"


# ===== 5. 未注册时调用应抛 RuntimeError =====


@pytest.mark.asyncio
async def test_adapter_not_registered_raises(adapter_session_factory):
    """适配器未注册时调用应抛 RuntimeError"""
    service = ACPService()
    adapter = ClaudeCodeAdapter(service=service)
    # 未调用 register 直接 call
    with pytest.raises(RuntimeError, match="尚未注册"):
        await adapter.call_memory("q")
    with pytest.raises(RuntimeError, match="尚未注册"):
        await adapter.call_swarm("t")
    with pytest.raises(RuntimeError, match="尚未注册"):
        await adapter.call_skill("s")
    with pytest.raises(RuntimeError, match="尚未注册"):
        await adapter.get_logs()


# ===== 6. info() 元信息 =====


def test_adapter_info():
    """适配器 info() 元信息正确"""
    adapter = ClaudeCodeAdapter(service=None)
    info = adapter.info()
    assert info["name"] == "claude_code"
    assert info["display_name"] == "Claude Code"
    assert info["default_endpoint"] == "cli://claude-code"
    assert "memory" in info["capabilities"]
    assert info["registered"] is False
    assert info["agent_id"] is None


# ===== 7. get_adapter 工厂函数 =====


def test_get_adapter_unknown():
    """get_adapter 对未知名称应抛 KeyError"""
    with pytest.raises(KeyError, match="未知适配器"):
        get_adapter("nonexistent_agent")


@pytest.mark.asyncio
async def test_get_adapter_with_auth_token(adapter_session_factory):
    """get_adapter 支持 auth_token 参数"""
    service = ACPService()
    adapter = get_adapter("claude_code", service=service, auth_token="secret-xyz")
    assert adapter.auth_token == "secret-xyz"
    agent = await adapter.register()
    assert agent["auth_token"] == "secret-xyz"


# ===== 8. 适配器管理 API =====


def test_api_list_adapters(adapters_app):
    """API: 列出所有适配器"""
    client = TestClient(adapters_app)
    resp = client.get("/acp-adapters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    names = {a["name"] for a in body["data"]}
    assert {"claude_code", "codex", "gemini_cli"}.issubset(names)


def test_api_get_adapter_info(adapters_app):
    """API: 获取单个适配器详情"""
    client = TestClient(adapters_app)
    resp = client.get("/acp-adapters/claude_code")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["name"] == "claude_code"
    assert body["data"]["display_name"] == "Claude Code"


def test_api_get_adapter_unknown(adapters_app):
    """API: 获取未知适配器应 404"""
    client = TestClient(adapters_app)
    resp = client.get("/acp-adapters/nonexistent")
    assert resp.status_code == 404


def test_api_call_without_register(adapters_app):
    """API: 未注册的适配器调用应 404"""
    client = TestClient(adapters_app)
    resp = client.post(
        "/acp-adapters/claude_code/call/memory",
        json={"query": "q", "action": "search"},
    )
    assert resp.status_code == 404
