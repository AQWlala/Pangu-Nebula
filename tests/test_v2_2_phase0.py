"""v2.2.0 Phase 0 基础架构测试

覆盖:
1. orm.py 新字段 (Persona +5 / Message +4 / Conversation +1)
2. 轻量运行时迁移助手 (旧库补列 / 幂等)
3. list_tools_schema() OpenAI tools 格式
4. openai_protocol _build_payload tools/tool_choice + tool_calls/tool 角色序列化
5. openai_protocol _parse_sse_chunk 解析 delta.tool_calls
6. StreamChunk tool_calls 字段
7. chat_service.stream_reply 工具调用循环 (含最大轮次防护 / 纯文本回退)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from server.db.migrations import run_lightweight_migrations
from server.db.orm import Base, Conversation, Message as OrmMessage, Persona
from server.providers.base import Message as ProviderMessage, ProviderCapability
from server.providers.protocols.base import StreamChunk
from server.providers.protocols.openai_protocol import OpenAIProtocol
from server.services.chat_service import MAX_TOOL_ROUNDS, ChatService
from server.tools.registry import list_tools_schema


# ===== 1. orm 新字段 =====


def _columns(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


def test_orm_persona_has_v2_2_capability_fields():
    assert {
        "tools_enabled",
        "rag_enabled",
        "sandbox_allow_network",
        "terminal_allowed",
        "browser_use_enabled",
    } <= _columns(Persona)


def test_orm_message_has_v2_2_tool_fields():
    assert {"tool_calls", "tool_call_id", "tool_name", "tool_result"} <= _columns(OrmMessage)


def test_orm_conversation_has_status_field():
    assert "status" in _columns(Conversation)


# ===== 2. 轻量运行时迁移 =====


async def test_lightweight_migration_adds_v2_2_columns_to_legacy_db():
    """旧库(仅 v2.1 列)经迁移后应补齐 v2.2.0 新列"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # 模拟旧库:仅 v2.1 列
        await conn.execute(text(
            "CREATE TABLE personas (id INTEGER PRIMARY KEY, name TEXT, "
            "system_prompt TEXT, model_name TEXT)"
        ))
        await conn.execute(text(
            "CREATE TABLE conversations (id INTEGER PRIMARY KEY, title TEXT)"
        ))
        await conn.execute(text(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT)"
        ))
        await conn.run_sync(run_lightweight_migrations)

        pcols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(personas)"))).fetchall()}
        ccols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(conversations)"))).fetchall()}
        mcols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(messages)"))).fetchall()}

    assert {
        "tools_enabled", "rag_enabled", "sandbox_allow_network",
        "terminal_allowed", "browser_use_enabled",
    } <= pcols
    assert "status" in ccols
    assert {"tool_calls", "tool_call_id", "tool_name", "tool_result"} <= mcols
    await engine.dispose()


async def test_lightweight_migration_is_idempotent_on_fresh_db():
    """全新库(create_all 已含新列)再跑迁移应无副作用"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_lightweight_migrations)  # 不应报错
        pcols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(personas)"))).fetchall()}
    assert "tools_enabled" in pcols
    await engine.dispose()


# ===== 3. list_tools_schema =====


def test_list_tools_schema_returns_openai_function_format():
    schema = list_tools_schema()
    assert isinstance(schema, list) and len(schema) >= 3
    for s in schema:
        assert s["type"] == "function"
        assert {"name", "description", "parameters"} <= set(s["function"])
    names = {s["function"]["name"] for s in schema}
    assert {"web_search", "file_read", "file_write"} <= names


# ===== 4/5/6. openai_protocol + StreamChunk =====


def _make_openai_provider(name: str = "t", env_key: str = "T_K") -> OpenAIProtocol:
    class _P(OpenAIProtocol):
        pass
    _P.name = name
    _P.env_key = env_key
    _P.default_chat_model = "m"
    return _P()


def test_openai_build_payload_includes_tools_and_default_tool_choice():
    provider = _make_openai_provider()
    msgs = [ProviderMessage(role="user", content="hi")]
    tools = [{"type": "function", "function": {"name": "x", "description": "d", "parameters": {}}}]
    payload = provider._build_payload(msgs, "m", {"tools": tools})
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


def test_openai_build_payload_respects_explicit_tool_choice():
    provider = _make_openai_provider()
    msgs = [ProviderMessage(role="user", content="hi")]
    tools = [{"type": "function", "function": {"name": "x", "description": "d", "parameters": {}}}]
    payload = provider._build_payload(msgs, "m", {"tools": tools, "tool_choice": "none"})
    assert payload["tool_choice"] == "none"


def test_openai_build_payload_serializes_assistant_tool_calls_and_tool_role():
    provider = _make_openai_provider()
    msgs = [
        ProviderMessage(
            role="assistant",
            content="",
            tool_calls=[{"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
        ),
        ProviderMessage(role="tool", content="result", tool_call_id="c1"),
    ]
    payload = provider._build_payload(msgs, "m", {})
    m0, m1 = payload["messages"]
    assert m0["role"] == "assistant"
    assert m0["tool_calls"] == [{"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]
    # 空 content 应转为 null,兼容严格 provider
    assert m0["content"] is None
    assert m1["role"] == "tool"
    assert m1["tool_call_id"] == "c1"
    assert m1["content"] == "result"


def test_openai_parse_sse_chunk_extracts_tool_calls():
    obj = {
        "choices": [{
            "delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "file_read", "arguments": json.dumps({"path": "x"})}}]},
            "finish_reason": "tool_calls",
        }]
    }
    chunk = OpenAIProtocol._parse_sse_chunk("data: " + json.dumps(obj))
    assert chunk is not None
    assert chunk.tool_calls is not None
    assert chunk.tool_calls[0]["id"] == "call_1"
    assert chunk.finish_reason == "tool_calls"
    assert chunk.text == ""


def test_stream_chunk_has_tool_calls_field():
    assert StreamChunk(text="", tool_calls=[{"index": 0}]).tool_calls == [{"index": 0}]
    assert StreamChunk(text="x").tool_calls is None


# ===== 7. chat_service.stream_reply 工具调用循环 =====


async def _seed_db():
    """建库 + 插入一个 tools_enabled=True 的 persona 和对话,返回 (Session, conv_id)"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_lightweight_migrations)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        p = Persona(
            name="t", system_prompt="sp",
            model_provider="mock", model_name="m", tools_enabled=True,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        conv = Conversation(persona_id=p.id, title="c")
        s.add(conv)
        await s.commit()
        await s.refresh(conv)
        conv_id = conv.id
    return Session, conv_id, engine


class _ToolCallThenTextProvider:
    """第一轮返回 tool_calls,第二轮返回文本"""
    name = "fake"
    protocol = "openai"
    capabilities = ProviderCapability(text=True)

    def __init__(self):
        self.calls = 0
        self.captured_kwargs: list[dict] = []

    async def stream(self, messages, model, **kwargs):
        self.captured_kwargs.append(kwargs)
        if self.calls == 0:
            self.calls += 1
            yield StreamChunk(
                tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "file_read", "arguments": json.dumps({"path": "/tmp/x"})}}],
                finish_reason="tool_calls",
            )
        else:
            yield StreamChunk(text="已读取文件", finish_reason="stop")


async def test_stream_reply_tool_call_loop_executes_and_persists():
    Session, conv_id, engine = await _seed_db()
    provider = _ToolCallThenTextProvider()
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={
        "success": True, "output": "content:/tmp/x", "error": "", "duration_ms": 0
    })
    with patch("server.services.chat_service.async_session", Session), \
         patch("server.services.chat_service.get_provider", return_value=provider), \
         patch("server.services.chat_service.tool_executor", mock_executor):
        svc = ChatService()
        events = [e async for e in svc.stream_reply(conv_id, "读文件")]

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "token" in types
    assert types[-1] == "done"

    tc = next(e for e in events if e["type"] == "tool_call")
    assert tc["name"] == "file_read"
    assert tc["arguments"] == {"path": "/tmp/x"}
    tr = next(e for e in events if e["type"] == "tool_result")
    assert tr["success"] is True
    assert "content:/tmp/x" in tr["result"]
    # tools schema 应注入请求
    assert provider.captured_kwargs[0].get("tools")
    # tool_executor.execute 应被调用一次 (file_read)
    mock_executor.execute.assert_called_once()
    called_args = mock_executor.execute.call_args
    assert called_args.args[0] == "file_read"
    assert called_args.args[1] == {"path": "/tmp/x"}

    # 持久化校验
    async with Session() as s:
        result = await s.execute(
            select(OrmMessage).where(OrmMessage.conversation_id == conv_id).order_by(OrmMessage.created_at)
        )
        msgs = list(result.scalars().all())
    asst = next(m for m in msgs if m.role == "assistant")
    assert asst.content == "已读取文件"
    assert asst.tool_calls is not None
    assert "file_read" in asst.tool_calls
    await engine.dispose()


class _LoopProvider:
    """始终返回 tool_calls,用于触发最大轮次防护"""
    name = "loop"
    protocol = "openai"
    capabilities = ProviderCapability(text=True)

    async def stream(self, messages, model, **kwargs):
        yield StreamChunk(
            tool_calls=[{"index": 0, "id": "c", "function": {"name": "file_read", "arguments": "{}"}}],
            finish_reason="tool_calls",
        )


async def test_stream_reply_max_rounds_guard():
    Session, conv_id, engine = await _seed_db()
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={
        "success": True, "output": "loop", "error": "", "duration_ms": 0
    })
    with patch("server.services.chat_service.async_session", Session), \
         patch("server.services.chat_service.get_provider", return_value=_LoopProvider()), \
         patch("server.services.chat_service.tool_executor", mock_executor):
        svc = ChatService()
        events = [e async for e in svc.stream_reply(conv_id, "loop")]

    types = [e["type"] for e in events]
    errs = [e for e in events if e["type"] == "error"]
    assert errs and "最大轮次" in errs[0]["error"]
    assert types.count("tool_call") == MAX_TOOL_ROUNDS
    await engine.dispose()


async def test_stream_reply_text_only_without_tools_enabled():
    """tools_enabled=False 时不注入 tools,单轮文本完成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_lightweight_migrations)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        p = Persona(name="t", system_prompt="sp", model_provider="mock", model_name="m", tools_enabled=False)
        s.add(p)
        await s.commit()
        await s.refresh(p)
        conv = Conversation(persona_id=p.id, title="c")
        s.add(conv)
        await s.commit()
        await s.refresh(conv)
        conv_id = conv.id

    class _TextProvider:
        name = "txt"
        protocol = "openai"
        capabilities = ProviderCapability(text=True)
        def __init__(self):
            self.captured_kwargs = []
        async def stream(self, messages, model, **kwargs):
            self.captured_kwargs.append(kwargs)
            yield StreamChunk(text="纯文本回答", finish_reason="stop")

    provider = _TextProvider()
    with patch("server.services.chat_service.async_session", Session), \
         patch("server.services.chat_service.get_provider", return_value=provider):
        svc = ChatService()
        events = [e async for e in svc.stream_reply(conv_id, "hi")]

    types = [e["type"] for e in events]
    assert "tool_call" not in types
    assert types[-1] == "done"
    # tools 不应注入
    assert not provider.captured_kwargs[0].get("tools")
    await engine.dispose()
