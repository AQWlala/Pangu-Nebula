"""ACP 协议 + 蜂群强化 + WeCom 渠道测试 (T3.1-T3.7)

覆盖:
1. 注册外部 Agent
2. 列出 Agent
3. 启用/禁用 Agent
4. ACP call memory (mock)
5. ACP call swarm (mock)
6. ACP 调用日志
7. WeComChannel 可实例化
8. WeComChannel 无 webhook 时 send_text 返回 mock
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from server.db.orm import Base
# 触发 acp_models 注册到 Base.metadata
from server.db import acp_models  # noqa: F401
from server.services.acp_service import ACPService
from server.services.wecom_channel import WeComChannel


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def acp_session_factory():
    """创建测试用 session factory,并 patch 到 ACPService 模块

    ACPService 内部使用 `async_session` 创建会话,
    此 fixture 用 monkeypatch 替换为测试 session factory。
    """
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # patch ACPService 模块中的 async_session
    import server.services.acp_service as acp_mod
    original = acp_mod.async_session
    acp_mod.async_session = session_factory
    try:
        yield session_factory
    finally:
        acp_mod.async_session = original
    await engine.dispose()


# ===== 1. 注册外部 Agent =====


@pytest.mark.asyncio
async def test_register_agent(acp_session_factory):
    """注册外部 Agent"""
    service = ACPService()
    result = await service.register_agent(
        name="Claude Code",
        agent_type="claude_code",
        endpoint="https://example.com/claude",
        capabilities=["code", "review"],
        auth_token="secret-token-123",
    )
    assert result["id"] is not None
    assert result["name"] == "Claude Code"
    assert result["agent_type"] == "claude_code"
    assert result["endpoint"] == "https://example.com/claude"
    assert result["capabilities"] == ["code", "review"]
    assert result["auth_token"] == "secret-token-123"
    assert result["enabled"] is True
    assert result["call_count"] == 0


# ===== 2. 列出 Agent =====


@pytest.mark.asyncio
async def test_list_agents(acp_session_factory):
    """列出 Agent"""
    service = ACPService()
    # 注册多个 Agent
    await service.register_agent(name="Agent A", agent_type="generic")
    await service.register_agent(name="Agent B", agent_type="codex")
    await service.register_agent(name="Agent C", agent_type="gemini_cli")

    # 默认只列出启用的
    agents = await service.list_agents(enabled_only=True)
    assert len(agents) == 3
    names = {a["name"] for a in agents}
    assert names == {"Agent A", "Agent B", "Agent C"}

    # 禁用一个后再列出
    first_id = agents[0]["id"]
    await service.disable_agent(first_id)
    enabled_agents = await service.list_agents(enabled_only=True)
    assert len(enabled_agents) == 2

    # enabled_only=False 应返回全部
    all_agents = await service.list_agents(enabled_only=False)
    assert len(all_agents) == 3


# ===== 3. 启用/禁用 Agent =====


@pytest.mark.asyncio
async def test_enable_disable_agent(acp_session_factory):
    """启用/禁用 Agent"""
    service = ACPService()
    agent = await service.register_agent(name="Test Agent", agent_type="generic")
    agent_id = agent["id"]

    # 禁用
    disabled = await service.disable_agent(agent_id)
    assert disabled["ok"] is True
    assert disabled["agent"]["enabled"] is False

    # 验证已禁用
    fetched = await service.get_agent(agent_id)
    assert fetched["enabled"] is False

    # 启用
    enabled = await service.enable_agent(agent_id)
    assert enabled["ok"] is True
    assert enabled["agent"]["enabled"] is True

    # 验证已启用
    fetched = await service.get_agent(agent_id)
    assert fetched["enabled"] is True


# ===== 4. ACP call memory (mock) =====


@pytest.mark.asyncio
async def test_acp_call_memory(acp_session_factory):
    """ACP call memory (mock)"""
    service = ACPService()
    agent = await service.register_agent(name="Memory Agent", agent_type="claude_code")
    agent_id = agent["id"]

    # read
    result = await service.call_memory(agent_id, "read", {"memory_id": 42})
    assert result["ok"] is True
    assert result["action"] == "read"
    assert result["mock"] is True
    assert result["memory_id"] == 42

    # write
    result = await service.call_memory(
        agent_id, "write", {"title": "New Memory", "layer": "L3", "content": "<p>hello</p>"}
    )
    assert result["ok"] is True
    assert result["action"] == "write"
    assert result["mock"] is True
    assert result["title"] == "New Memory"

    # search
    result = await service.call_memory(agent_id, "search", {"query": "hello"})
    assert result["ok"] is True
    assert result["action"] == "search"
    assert result["mock"] is True
    assert result["query"] == "hello"


# ===== 5. ACP call swarm (mock) =====


@pytest.mark.asyncio
async def test_acp_call_swarm(acp_session_factory):
    """ACP call swarm (mock)"""
    service = ACPService()
    agent = await service.register_agent(name="Swarm Agent", agent_type="codex")
    agent_id = agent["id"]

    result = await service.call_swarm(
        agent_id,
        task="Build a REST API",
        config={"persona_id": 1, "worker_count": 5},
    )
    assert result["ok"] is True
    assert result["mock"] is True
    assert result["task"] == "Build a REST API"
    assert result["persona_id"] == 1
    assert result["worker_count"] == 5
    assert result["status"] == "pending"


# ===== 6. ACP 调用日志 =====


@pytest.mark.asyncio
async def test_acp_call_logs(acp_session_factory):
    """ACP 调用日志"""
    service = ACPService()
    agent = await service.register_agent(name="Logged Agent", agent_type="gemini_cli")
    agent_id = agent["id"]

    # 执行几次调用以产生日志
    await service.call_memory(agent_id, "read", {"memory_id": 1})
    await service.call_swarm(agent_id, "task 1", {})
    await service.call_skill(agent_id, "summarizer", {})

    # 获取该 Agent 的日志
    logs = await service.get_call_logs(agent_id=agent_id, limit=100)
    assert len(logs) == 3
    # 日志按时间倒序,最新在前
    actions = [log["action"] for log in logs]
    assert "call_memory" in actions
    assert "call_swarm" in actions
    assert "call_skill" in actions

    # 验证日志结构
    for log in logs:
        assert log["agent_id"] == agent_id
        assert log["status"] == "ok"
        assert log["duration_ms"] >= 0
        assert log["request"] is not None
        assert log["response"] is not None
        assert log["created_at"] is not None

    # 验证 call_count 已更新
    agent_after = await service.get_agent(agent_id)
    assert agent_after["call_count"] == 3
    assert agent_after["last_called"] is not None


# ===== 7. WeComChannel 可实例化 =====


def test_wecom_channel_instantiable():
    """WeComChannel 可实例化"""
    channel = WeComChannel()
    assert channel is not None

    status = channel.get_status()
    assert status["ok"] is True
    assert "configured" in status
    assert "webhook_set" in status
    assert "error" in status


# ===== 8. WeComChannel 无 webhook 时 send_text 返回 mock =====


@pytest.mark.asyncio
async def test_wecom_send_text_mock(monkeypatch):
    """WeComChannel 无 webhook 时 send_text 返回 mock"""
    monkeypatch.delenv("NEBULA_WECOM_WEBHOOK", raising=False)
    channel = WeComChannel()
    # 确保无 webhook
    assert channel._webhook_url is None

    result = await channel.send_text("hello wecom")

    assert result["ok"] is True
    assert result["channel"] == "wecom"
    assert result["error"] is None
    data = result["data"]
    assert data["mock"] is True
    assert data["text"] == "hello wecom"
