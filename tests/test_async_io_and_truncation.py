# tests/test_async_io_and_truncation.py
"""v2.2.1 安全重构 S1+S2 测试

S1: 异步 IO 包装 — knowledge_service.ingest/search/delete_doc 通过 asyncio.to_thread
    调用同步 store 操作,避免阻塞事件循环。
S2: 工具结果截断 — chat_service.stream_reply 工具循环内,长工具结果回喂 LLM 前截断,
    保留首尾各 1000 字符,防止 provider_messages 累积导致 token 爆炸。
    注意: 仅截断回喂 LLM 的 content,前端 yield 的 tool_result 事件保留原始内容。

测试用例:
1. test_ingest_uses_to_thread       — ingest 通过 asyncio.to_thread 调用 store.upsert
2. test_search_uses_to_thread       — search 通过 asyncio.to_thread 调用 store.query
3. test_delete_doc_uses_to_thread   — delete_doc 通过 asyncio.to_thread 调用 store.delete_by_doc_id
4. test_truncate_short_content      — 短内容(<=max_chars)不截断
5. test_truncate_long_content       — 长内容截断,保留首尾
6. test_truncate_preserves_boundaries — 验证截断后首尾内容正确
7. test_truncate_none_content       — None / 非字符串 不抛异常
8. test_tool_result_truncated_in_stream_reply — 集成测试,长工具结果回喂前截断
"""
import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from server.services.knowledge_service import KnowledgeService
from server.config_kb_cu import KBConfig
from server.services.chat_service import (
    ChatService,
    _truncate_tool_result,
    _MAX_TOOL_RESULT_CHARS,
)
from server.providers.protocols.base import StreamChunk


# ============================================================
# S1: 异步 IO 包装 — knowledge_service
# ============================================================

class TestS1AsyncIOWrapper:
    """验证 ingest/search/delete_doc 通过 asyncio.to_thread 调用同步 store 操作。"""

    def _make_svc(self, tmp: str) -> KnowledgeService:
        config = KBConfig(kb_root=Path(tmp))
        config.ensure_dirs()
        svc = KnowledgeService(config=config)
        mock_store = MagicMock()
        svc._store = mock_store
        svc._store_type = "mock"
        return svc, mock_store

    @pytest.mark.asyncio
    async def test_ingest_uses_to_thread(self):
        """ingest 中 store.upsert 通过 asyncio.to_thread 调用,不阻塞事件循环。"""
        with TemporaryDirectory() as tmp:
            svc, mock_store = self._make_svc(tmp)
            mock_store.upsert = MagicMock(return_value=None)

            with patch(
                "server.services.knowledge_service.asyncio.to_thread",
                new=AsyncMock(return_value=None),
            ) as mock_to_thread:
                result = await svc.ingest(
                    "doc-1", "Python 异步编程内容", scope="private"
                )

                # to_thread 必须被调用一次
                mock_to_thread.assert_called_once()
                called = mock_to_thread.call_args
                # 第一个位置参数必须是 store.upsert (绑定方法)
                assert called.args[0] == mock_store.upsert
                # 第二个位置参数是 chunks 列表
                chunks_arg = called.args[1]
                assert isinstance(chunks_arg, list)
                assert len(chunks_arg) >= 1
                assert chunks_arg[0]["doc_id"] == "doc-1"
                # 不应有额外关键字参数
                assert called.kwargs == {}

            # ingest 返回结构正确
            assert result["doc_id"] == "doc-1"
            assert result["chunks"] >= 1
            assert result["store_type"] == "mock"
            svc.close()

    @pytest.mark.asyncio
    async def test_search_uses_to_thread(self):
        """search 中 store.query 通过 asyncio.to_thread 调用,透传 scope/top_k 关键字参数。"""
        with TemporaryDirectory() as tmp:
            svc, mock_store = self._make_svc(tmp)
            expected_results = [
                {"id": "c0", "doc_id": "d1", "text": "结果", "score": 0.9}
            ]
            mock_store.query = MagicMock(return_value=expected_results)

            with patch(
                "server.services.knowledge_service.asyncio.to_thread",
                new=AsyncMock(return_value=expected_results),
            ) as mock_to_thread:
                results = await svc.search("query text", top_k=5, scope="private")

                # to_thread 被调用,参数: (store.query, "query text", scope=..., top_k=...)
                mock_to_thread.assert_called_once_with(
                    mock_store.query, "query text", scope="private", top_k=5
                )
                assert results == expected_results
            svc.close()

    @pytest.mark.asyncio
    async def test_delete_doc_uses_to_thread(self):
        """delete_doc 中 store.delete_by_doc_id 通过 asyncio.to_thread 调用。"""
        with TemporaryDirectory() as tmp:
            svc, mock_store = self._make_svc(tmp)
            mock_store.delete_by_doc_id = MagicMock(return_value=None)

            with patch(
                "server.services.knowledge_service.asyncio.to_thread",
                new=AsyncMock(return_value=None),
            ) as mock_to_thread:
                ok = await svc.delete_doc("del-doc")

                mock_to_thread.assert_called_once_with(
                    mock_store.delete_by_doc_id, "del-doc"
                )
                assert ok is True
            svc.close()

    @pytest.mark.asyncio
    async def test_delete_doc_failure_returns_false(self):
        """delete_doc 中 to_thread 抛异常时返回 False,不向上传播。"""
        with TemporaryDirectory() as tmp:
            svc, mock_store = self._make_svc(tmp)

            with patch(
                "server.services.knowledge_service.asyncio.to_thread",
                new=AsyncMock(side_effect=RuntimeError("store down")),
            ):
                ok = await svc.delete_doc("del-doc")
                assert ok is False
            svc.close()

    @pytest.mark.asyncio
    async def test_search_does_not_block_event_loop(self):
        """search 实际通过 to_thread 在工作线程执行,主事件循环不被阻塞。

        用真实 to_thread (非 mock),验证 store.query 在非主线程被调用。
        """
        with TemporaryDirectory() as tmp:
            svc, mock_store = self._make_svc(tmp)
            import threading

            calling_thread = []

            def _query(*args, **kwargs):
                calling_thread.append(threading.current_thread().ident)
                return [{"doc_id": "d1"}]

            mock_store.query = MagicMock(side_effect=_query)

            main_thread = threading.current_thread().ident
            results = await svc.search("hello", top_k=3, scope="private")

            assert results == [{"doc_id": "d1"}]
            assert len(calling_thread) == 1
            # store.query 必须在工作线程执行,而非主线程
            assert calling_thread[0] != main_thread
            svc.close()


# ============================================================
# S2: 工具结果截断 — _truncate_tool_result 单元测试
# ============================================================

class TestS2TruncateToolResult:
    """验证 _truncate_tool_result 截断逻辑。"""

    def test_truncate_short_content(self):
        """短内容(<=max_chars)不截断,原样返回。"""
        # 空字符串
        assert _truncate_tool_result("") == ""
        # 短字符串
        assert _truncate_tool_result("short content") == "short content"
        # 恰好等于 max_chars 边界: 不截断 (<=)
        boundary = "x" * _MAX_TOOL_RESULT_CHARS
        assert _truncate_tool_result(boundary) == boundary
        assert _truncate_tool_result(boundary) is boundary  # 同一对象

    def test_truncate_long_content(self):
        """长内容(>max_chars)被截断,包含 truncated 标记,保留首尾。"""
        long_content = "A" * (_MAX_TOOL_RESULT_CHARS + 3000)
        result = _truncate_tool_result(long_content)

        # 包含截断标记
        assert "truncated" in result
        # 结果比原内容短
        assert len(result) < len(long_content)
        # 保留首部 1000 字符 (max_chars // 2)
        keep = _MAX_TOOL_RESULT_CHARS // 2
        assert result.startswith("A" * keep)
        # 保留尾部 1000 字符
        assert result.endswith("A" * keep)

    def test_truncate_preserves_boundaries(self):
        """验证截断后首尾内容正确,中间内容被丢弃。"""
        keep = _MAX_TOOL_RESULT_CHARS // 2  # 1000
        head = "H" * keep                    # 首部 1000 个 H
        middle = "M" * 3000                  # 中间 3000 个 M (应被丢弃)
        tail = "T" * keep                    # 尾部 1000 个 T
        content = head + middle + tail       # 总长 5000

        result = _truncate_tool_result(content)

        # 首部 1000 个 H 完整保留
        assert result.startswith(head)
        # 尾部 1000 个 T 完整保留
        assert result.endswith(tail)
        # 中间的 3000 个 M 不应完整出现
        assert middle not in result
        # 截断标记存在,且标注被截断的字符数 (3000)
        assert "truncated 3000 chars" in result

    def test_truncate_none_content(self):
        """None / 非字符串 不抛异常,原样返回。"""
        assert _truncate_tool_result(None) is None
        # 数字
        assert _truncate_tool_result(12345) == 12345
        # 列表
        lst = [1, 2, 3]
        assert _truncate_tool_result(lst) is lst
        # 字节串
        b = b"bytes"
        assert _truncate_tool_result(b) is b

    def test_truncate_custom_max_chars(self):
        """max_chars 可配置: 自定义较小值。"""
        content = "ABCDEFGH" * 100  # 800 字符
        # 自定义 max_chars=100, 保留首尾各 50
        result = _truncate_tool_result(content, max_chars=100)
        assert "truncated" in result
        assert result.startswith(content[:50])
        assert result.endswith(content[-50:])

    def test_truncate_custom_max_chars_odd(self):
        """max_chars 为奇数时,keep = max_chars // 2 (整除),不抛异常。"""
        content = "Z" * 500
        result = _truncate_tool_result(content, max_chars=101)
        # 101 // 2 = 50
        assert result.startswith("Z" * 50)
        assert result.endswith("Z" * 50)
        assert "truncated" in result


# ============================================================
# S2 集成测试: stream_reply 工具结果截断
# ============================================================

def _make_persona(**overrides):
    """构造 transient Persona 对象 (与 test_v2_2_integration 一致)。"""
    from server.db.orm import Persona
    defaults = {
        "id": 1,
        "name": "test",
        "system_prompt": "你是助手",
        "model_provider": "deepseek",
        "model_name": "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 4096,
        "tools_enabled": True,
        "rag_enabled": False,
        "sandbox_allow_network": False,
        "terminal_allowed": False,
        "browser_use_enabled": False,
    }
    defaults.update(overrides)
    return Persona(**defaults)


def _setup_stream_reply_mocks(persona, mock_session_factory):
    """统一设置 stream_reply 所需的 session/persona/history mock。"""
    from server.db.orm import Conversation

    conv = Conversation(id=1, persona_id=persona.id)
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=[
        # 1) 查询 conversation
        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
        # 2) 查询 persona fallback
        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
        # 3) 查询 history
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    return mock_session


class TestS2StreamReplyTruncation:
    """集成测试: stream_reply 中长工具结果回喂 LLM 前被截断。"""

    @pytest.mark.asyncio
    async def test_tool_result_truncated_in_stream_reply(self):
        """长工具结果: 前端 yield 原始内容,回喂 LLM 的 messages 中 tool 消息被截断。"""
        # 5000 字符的工具输出,远超 2000 限制
        long_output = "X" * 5000

        # 捕获每轮 stream() 收到的 messages
        captured_messages_per_round: list[list] = []
        call_count = [0]

        class _MockProvider:
            async def stream(self, messages, model_name, **kwargs):
                call_count[0] += 1
                # 捕获本轮 stream 收到的 messages (拷贝 list,引用 ProviderMessage 对象)
                captured_messages_per_round.append(list(messages))
                if call_count[0] == 1:
                    # 第一轮: 返回 tool_calls
                    yield StreamChunk(
                        text="",
                        tool_calls=[{
                            "index": 0,
                            "id": "call_trunc_1",
                            "type": "function",
                            "function": {
                                "name": "file_read",
                                "arguments": json.dumps({"path": "/tmp/x"}),
                            },
                        }],
                        finish_reason="tool_calls",
                    )
                else:
                    # 第二轮: 返回文本,结束循环
                    yield StreamChunk(text="已读取", tool_calls=None, finish_reason="stop")

        provider = _MockProvider()
        persona = _make_persona()

        svc = ChatService()
        with patch("server.services.chat_service.get_provider", return_value=provider), \
             patch("server.services.chat_service.async_session") as mock_sf, \
             patch("server.services.chat_service.knowledge_service") as mock_kb, \
             patch("server.services.chat_service.tool_executor") as mock_te, \
             patch.object(svc, "_persist_assistant", AsyncMock(return_value=42)):

            _setup_stream_reply_mocks(persona, mock_sf)
            mock_kb.search = AsyncMock(return_value=[])
            mock_te.execute = AsyncMock(return_value={
                "success": True,
                "output": long_output,
                "error": "",
                "duration_ms": 5,
            })

            chunks = []
            async for chunk in svc.stream_reply(1, "读取文件"):
                chunks.append(chunk)

            # ---- 断言 1: 前端 yield 的 tool_result 事件保留原始长内容 ----
            tool_result_events = [c for c in chunks if c.get("type") == "tool_result"]
            assert len(tool_result_events) == 1
            assert tool_result_events[0]["result"] == long_output  # 未截断
            assert len(tool_result_events[0]["result"]) == 5000

            # ---- 断言 2: 第二轮 stream 收到的 messages 中,tool 消息 content 被截断 ----
            assert len(captured_messages_per_round) >= 2, \
                "应至少调用 stream 两次(第一轮 tool_calls + 第二轮文本)"
            second_round_msgs = captured_messages_per_round[1]
            tool_msgs = [m for m in second_round_msgs if m.role == "tool"]
            assert len(tool_msgs) == 1, "第二轮 messages 应包含 1 条 tool 消息"

            truncated_content = tool_msgs[0].content
            # 是字符串且被截断
            assert isinstance(truncated_content, str)
            assert "truncated" in truncated_content
            # 比原始短
            assert len(truncated_content) < len(long_output)
            # 保留首尾各 1000 字符
            keep = _MAX_TOOL_RESULT_CHARS // 2
            assert truncated_content.startswith("X" * keep)
            assert truncated_content.endswith("X" * keep)
            # tool_call_id 正确回填
            assert tool_msgs[0].tool_call_id == "call_trunc_1"

            # ---- 断言 3: 流正常完成 ----
            assert any(c.get("type") == "done" for c in chunks)
            assert call_count[0] == 2  # 两轮 stream 调用

    @pytest.mark.asyncio
    async def test_short_tool_result_not_truncated_in_stream_reply(self):
        """短工具结果(<=2000)回喂 LLM 时不截断。"""
        short_output = "短结果" * 10  # 30 字符

        captured: list[list] = []
        call_count = [0]

        class _MockProvider:
            async def stream(self, messages, model_name, **kwargs):
                call_count[0] += 1
                captured.append(list(messages))
                if call_count[0] == 1:
                    yield StreamChunk(
                        text="",
                        tool_calls=[{
                            "index": 0,
                            "id": "call_short_1",
                            "type": "function",
                            "function": {
                                "name": "calc",
                                "arguments": json.dumps({"expr": "1+1"}),
                            },
                        }],
                        finish_reason="tool_calls",
                    )
                else:
                    yield StreamChunk(text="答案是2", tool_calls=None, finish_reason="stop")

        provider = _MockProvider()
        persona = _make_persona()
        svc = ChatService()

        with patch("server.services.chat_service.get_provider", return_value=provider), \
             patch("server.services.chat_service.async_session") as mock_sf, \
             patch("server.services.chat_service.knowledge_service") as mock_kb, \
             patch("server.services.chat_service.tool_executor") as mock_te, \
             patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):

            _setup_stream_reply_mocks(persona, mock_sf)
            mock_kb.search = AsyncMock(return_value=[])
            mock_te.execute = AsyncMock(return_value={
                "success": True,
                "output": short_output,
                "error": "",
                "duration_ms": 1,
            })

            chunks = []
            async for chunk in svc.stream_reply(1, "计算"):
                chunks.append(chunk)

            # 第二轮 tool 消息 content 未截断
            second_round_msgs = captured[1]
            tool_msgs = [m for m in second_round_msgs if m.role == "tool"]
            assert tool_msgs[0].content == short_output
            assert "truncated" not in tool_msgs[0].content
