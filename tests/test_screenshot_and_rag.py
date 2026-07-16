# tests/test_screenshot_and_rag.py
"""v2.2.1 S8+S9 — 截图压缩与 RAG 健壮性测试

S8: 截图压缩 (已被 F7 覆盖,此处补充测试)
    - test_screenshot_compressed: 大图 → JPEG 1024x768 范围
    - test_screenshot_fallback_without_pil: 无 PIL 时优雅降级

S9: RAG 健壮性
    - test_rag_failure_yields_error_event: RAG 失败时 yield rag_context error 事件
    - test_rag_context_inserted_after_last_system: RAG 上下文插入到最后一个 system 之后
    - test_rag_context_inserted_when_multiple_systems: 多 system 时插入到最后一个之后
    - test_rag_preview_handles_none_text: text=None 时不抛异常
    - test_rag_preview_handles_short_text: 短文本不加 "..."
"""
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# S8: 截图压缩测试
# ============================================================

class TestScreenshotCompression:
    """S8: 截图压缩 — 验证截图被缩放到 1024x768 + JPEG quality=85 (F7 已实现)"""

    @pytest.mark.asyncio
    async def test_screenshot_compressed(self):
        """大图截图被压缩: 1920x1080 → JPEG 宽度 <= 1024"""
        pytest.importorskip("PIL")
        from PIL import Image
        from server.tools.computer_tools import ComputerScreenshotTool

        # 创建 1920x1080 大图 (超过 1024x768 阈值,触发压缩)
        large_img = Image.new("RGB", (1920, 1080), color=(255, 0, 0))

        mock_pg = MagicMock()
        mock_pg.screenshot = MagicMock(return_value=large_img)

        with patch(
            "server.tools.computer_tools._check_dependencies",
            return_value=(True, ""),
        ):
            with patch.dict(sys.modules, {"pyautogui": mock_pg}):
                tool = ComputerScreenshotTool()
                result = await tool.execute()

                assert result.success, f"截图应成功,错误: {result.error}"
                # 输出应包含 JPEG 标识
                assert "JPEG" in result.output
                # 压缩后宽度应 <= 1024 (1920 → 1024)
                assert "1024" in result.output

    @pytest.mark.asyncio
    async def test_screenshot_fallback_without_pil(self):
        """无 PIL 依赖时优雅降级: 返回错误而非崩溃"""
        from server.tools.computer_tools import ComputerScreenshotTool

        with patch(
            "server.tools.computer_tools._check_dependencies",
            return_value=(False, "计算机操作依赖未安装: No module named 'PIL'"),
        ):
            tool = ComputerScreenshotTool()
            result = await tool.execute()

            assert not result.success
            assert "依赖未安装" in result.error


# ============================================================
# S9: RAG 健壮性测试
# ============================================================

def _make_mock_session(conv, persona, history=None):
    """构造 mock async session,返回 conv → persona → history 三次 execute。"""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=history or [])))),
    ])
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    return mock_session


def _mock_history_msg(role, content):
    """构造 mock history message (模拟 ORM Message 的 role/content 属性)。"""
    m = MagicMock()
    m.role = role
    m.content = content
    return m


class TestRagFailureErrorEvent:
    """S9 问题1: RAG 异常不再静默 — yield rag_context error 事件"""

    @pytest.mark.asyncio
    async def test_rag_failure_yields_error_event(self):
        """RAG 检索失败时 yield rag_context 事件带 error 字段"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(side_effect=Exception("vector store offline"))

            svc = ChatService()
            with patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):
                with patch(
                    "server.services.chat_service.async_session"
                ) as mock_sf:
                    persona = Persona(
                        id=1, name="test", system_prompt="你是助手",
                        model_provider=None,
                        rag_enabled=True,
                        tools_enabled=False,
                    )
                    conv = Conversation(id=1, persona_id=1)
                    mock_session = _make_mock_session(conv, persona)
                    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

                    chunks = []
                    async for chunk in svc.stream_reply(1, "hello"):
                        chunks.append(chunk)

                    # 应有 rag_context 事件带 error
                    rag_events = [c for c in chunks if c.get("type") == "rag_context"]
                    assert len(rag_events) == 1
                    assert rag_events[0]["sources"] == []
                    assert "error" in rag_events[0]
                    assert "vector store offline" in rag_events[0]["error"]
                    # 对话不阻断 (仍有 error 事件因 model_provider=None)
                    assert any(c.get("type") == "error" for c in chunks)


class TestRagContextInsertion:
    """S9 问题2: RAG 上下文插入到最后一个 system 消息之后"""

    @pytest.mark.asyncio
    async def test_rag_context_inserted_after_last_system(self):
        """单个 system 消息时,RAG 上下文插入到 system 之后 (index 1)"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation
        from server.providers.protocols.base import StreamChunk

        rag_results = [{"doc_id": "doc1", "score": 0.9, "text": "RAG 参考内容"}]
        captured_messages = []

        async def fake_stream(messages, model, **kwargs):
            captured_messages.extend(messages)
            yield StreamChunk(text="回答", finish_reason="stop")

        mock_provider = MagicMock()
        mock_provider.stream = fake_stream

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=rag_results)
            with patch(
                "server.services.chat_service.get_provider",
                return_value=mock_provider,
            ):
                svc = ChatService()
                with patch.object(
                    svc, "_persist_assistant", AsyncMock(return_value=1)
                ):
                    with patch(
                        "server.services.chat_service.async_session"
                    ) as mock_sf:
                        persona = Persona(
                            id=1, name="test", system_prompt="你是助手",
                            model_provider="mock",
                            model_name="mock-model",
                            rag_enabled=True,
                            tools_enabled=False,
                        )
                        conv = Conversation(id=1, persona_id=1)
                        mock_session = _make_mock_session(
                            conv, persona,
                            history=[_mock_history_msg("user", "hello")],
                        )
                        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

                        chunks = []
                        async for chunk in svc.stream_reply(1, "hello"):
                            chunks.append(chunk)

                        # provider_messages: [system, rag_system, user]
                        assert len(captured_messages) >= 3
                        assert captured_messages[0].role == "system"
                        assert captured_messages[1].role == "system"
                        assert "知识库参考" in captured_messages[1].content
                        assert captured_messages[2].role == "user"

    @pytest.mark.asyncio
    async def test_rag_context_inserted_when_multiple_systems(self):
        """多个 system 消息时,RAG 上下文插入到最后一个 system 之后"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation
        from server.providers.protocols.base import StreamChunk
        from server.services.compact import CompactResult

        rag_results = [{"doc_id": "doc1", "score": 0.9, "text": "RAG 参考内容"}]
        captured_messages = []

        async def fake_stream(messages, model, **kwargs):
            captured_messages.extend(messages)
            yield StreamChunk(text="回答", finish_reason="stop")

        mock_provider = MagicMock()
        mock_provider.stream = fake_stream

        # mock compact 返回多个 system 消息
        async def fake_compact(messages, llm_call=None):
            return CompactResult(
                messages=[
                    {"role": "system", "content": "系统提示1"},
                    {"role": "system", "content": "系统提示2"},
                    {"role": "user", "content": "hello"},
                ],
                compacted=False,
                tokens_before=100,
                tokens_after=100,
                strategy="none",
            )

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=rag_results)
            with patch(
                "server.services.chat_service.get_provider",
                return_value=mock_provider,
            ):
                svc = ChatService()
                with patch.object(
                    svc.compact, "compact_if_needed", side_effect=fake_compact
                ):
                    with patch.object(
                        svc, "_persist_assistant", AsyncMock(return_value=1)
                    ):
                        with patch(
                            "server.services.chat_service.async_session"
                        ) as mock_sf:
                            persona = Persona(
                                id=1, name="test", system_prompt="你是助手",
                                model_provider="mock",
                                model_name="mock-model",
                                rag_enabled=True,
                                tools_enabled=False,
                            )
                            conv = Conversation(id=1, persona_id=1)
                            mock_session = _make_mock_session(conv, persona)
                            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

                            chunks = []
                            async for chunk in svc.stream_reply(1, "hello"):
                                chunks.append(chunk)

                            # provider_messages: [system1, system2, rag_system, user]
                            assert len(captured_messages) >= 4
                            assert captured_messages[0].role == "system"
                            assert captured_messages[0].content == "系统提示1"
                            assert captured_messages[1].role == "system"
                            assert captured_messages[1].content == "系统提示2"
                            # RAG context 在最后一个 system 之后
                            assert captured_messages[2].role == "system"
                            assert "知识库参考" in captured_messages[2].content
                            assert captured_messages[3].role == "user"


class TestRagPreviewText:
    """S9 问题3: preview text=None 时不抛 TypeError"""

    @pytest.mark.asyncio
    async def test_rag_preview_handles_none_text(self):
        """text=None 时 preview 为空字符串,不抛 TypeError"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation

        rag_results = [
            {"doc_id": "doc1", "score": 0.9, "text": None},
        ]

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=rag_results)
            # mock format_rag_context 避免 None.strip() 崩溃 (仅测试 preview 逻辑)
            with patch(
                "server.services.chat_service.format_rag_context",
                return_value="知识库参考:\n[1] (doc_id:doc1)",
            ):
                svc = ChatService()
                with patch.object(
                    svc, "_persist_assistant", AsyncMock(return_value=1)
                ):
                    with patch(
                        "server.services.chat_service.async_session"
                    ) as mock_sf:
                        persona = Persona(
                            id=1, name="test", system_prompt="你是助手",
                            model_provider=None,
                            rag_enabled=True,
                            tools_enabled=False,
                        )
                        conv = Conversation(id=1, persona_id=1)
                        mock_session = _make_mock_session(conv, persona)
                        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

                        chunks = []
                        async for chunk in svc.stream_reply(1, "hello"):
                            chunks.append(chunk)

                        rag_events = [
                            c for c in chunks if c.get("type") == "rag_context"
                        ]
                        assert len(rag_events) == 1
                        assert len(rag_events[0]["sources"]) == 1
                        # text=None → preview 应为 "" (不抛 TypeError)
                        assert rag_events[0]["sources"][0]["preview"] == ""

    @pytest.mark.asyncio
    async def test_rag_preview_handles_short_text(self):
        """短文本 (<200 字符) preview 不加 '...'"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation

        short_text = "这是一段简短的参考内容"
        rag_results = [
            {"doc_id": "doc1", "score": 0.9, "text": short_text},
        ]

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=rag_results)
            svc = ChatService()
            with patch.object(
                svc, "_persist_assistant", AsyncMock(return_value=1)
            ):
                with patch(
                    "server.services.chat_service.async_session"
                ) as mock_sf:
                    persona = Persona(
                        id=1, name="test", system_prompt="你是助手",
                        model_provider=None,
                        rag_enabled=True,
                        tools_enabled=False,
                    )
                    conv = Conversation(id=1, persona_id=1)
                    mock_session = _make_mock_session(conv, persona)
                    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

                    chunks = []
                    async for chunk in svc.stream_reply(1, "hello"):
                        chunks.append(chunk)

                    rag_events = [
                        c for c in chunks if c.get("type") == "rag_context"
                    ]
                    assert len(rag_events) == 1
                    assert len(rag_events[0]["sources"]) == 1
                    # 短文本 preview 应原样返回,不加 "..."
                    preview = rag_events[0]["sources"][0]["preview"]
                    assert preview == short_text
                    assert "..." not in preview
