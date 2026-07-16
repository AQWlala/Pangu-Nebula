"""v2.2.1 S3+S4 安全重构测试

S3: browser_service 锁粒度优化 — navigate/execute_action/get_page_info/list_tabs
    仅在读取 session 状态(page/context 引用)时持锁,Playwright 操作本身不持锁,
    避免 30s 导航超时期间长期持锁阻塞其他状态读取;
    start_session/close_session 保持全程持锁(它们修改 session 状态)。

S4: chat_service.stream_reply finish_reason 兼容判断 — 部分 provider 返回
    tool_calls 时 finish_reason 可能为 None,旧逻辑 `finish_reason != "tool_calls"`
    会误 break 导致工具不执行;新逻辑仅在 tool_calls 为空或 finish_reason 明确
    不是 "tool_calls" 时才 break。
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from server.providers.protocols.base import StreamChunk


# ============================================================
# S3: browser_service 锁粒度
# ============================================================


class TestBrowserLockGranularity:
    """S3: 验证 navigate 操作期间不持锁,start_session 全程持锁。"""

    async def test_navigate_does_not_hold_lock_during_operation(self):
        """navigate 在 page.goto 执行期间不应持有锁 (S3 核心修复点)。

        mock page.goto 延时 50ms,在其内部检查 self._lock.locked() 应为 False。
        """
        from server.services.browser_service import BrowserService

        svc = BrowserService()
        lock_held_during_goto = []

        async def fake_goto(*args, **kwargs):
            # 在 page.goto 执行期间检查锁是否被持有
            lock_held_during_goto.append(svc._lock.locked())
            await asyncio.sleep(0.05)  # 模拟慢导航
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(side_effect=fake_goto)
        mock_page.title = AsyncMock(return_value="Test Title")
        mock_page.url = "https://example.com"
        svc.page = mock_page

        with patch("server.services.browser_service._HAS_PLAYWRIGHT", True):
            result = await svc.navigate("https://example.com")

        assert result["ok"] is True
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["title"] == "Test Title"
        assert result["data"]["status"] == 200
        assert len(lock_held_during_goto) == 1
        assert lock_held_during_goto[0] is False, (
            "navigate 在 page.goto 期间不应持有锁 (S3)"
        )

    async def test_navigate_still_returns_error_when_no_session(self):
        """无 session (page=None) 时 navigate 应返回错误。"""
        from server.services.browser_service import BrowserService

        svc = BrowserService()
        assert svc.page is None

        with patch("server.services.browser_service._HAS_PLAYWRIGHT", True):
            result = await svc.navigate("https://example.com")

        assert result["ok"] is False
        assert result["data"] is None
        assert "未启动" in result["error"]

    async def test_start_session_still_holds_lock(self):
        """start_session 应全程持锁 (修改 session 状态,不可与其他操作交错)。"""
        from server.services.browser_service import BrowserService

        svc = BrowserService()
        lock_checks = []

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        async def launch_side(*args, **kwargs):
            lock_checks.append(svc._lock.locked())
            return mock_browser

        async def new_context_side(*args, **kwargs):
            lock_checks.append(svc._lock.locked())
            return mock_context

        async def new_page_side(*args, **kwargs):
            lock_checks.append(svc._lock.locked())
            return mock_page

        mock_playwright.chromium.launch = AsyncMock(side_effect=launch_side)
        mock_browser.new_context = AsyncMock(side_effect=new_context_side)
        mock_context.new_page = AsyncMock(side_effect=new_page_side)

        with patch("server.services.browser_service._HAS_PLAYWRIGHT", True), \
             patch("server.services.browser_service.async_playwright") as mock_ap:
            mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

            result = await svc.start_session()

        assert result["ok"] is True
        assert result["data"]["session_id"]
        # launch / new_context / new_page 期间锁均应被持有
        assert len(lock_checks) == 3
        assert all(lock_checks), (
            f"start_session 应全程持锁,实际: {lock_checks}"
        )


# ============================================================
# S4: finish_reason 兼容判断
# ============================================================


def _make_persona(**overrides):
    """构造 transient Persona 对象。"""
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
        "rag_enabled": True,
        "sandbox_allow_network": False,
        "terminal_allowed": True,
        "browser_use_enabled": True,
    }
    defaults.update(overrides)
    return Persona(**defaults)


def _setup_stream_reply_mocks(persona, mock_session_factory=None):
    """统一设置 stream_reply 所需的 mock (DB session 三次 execute)。"""
    from server.db.orm import Conversation

    conv = Conversation(id=1, persona_id=persona.id)

    mock_session = AsyncMock()
    if mock_session_factory is None:
        mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_session.execute = AsyncMock(side_effect=[
        # 1. 查询 conversation (persona 未加载 → 触发 fallback)
        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
        # 2. fallback 查询 persona
        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
        # 3. 查询 history
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    return mock_session_factory


class _ScriptedProvider:
    """按脚本依次返回预设的 StreamChunk 序列,记录 stream 调用次数。"""

    def __init__(self, scripts):
        self.scripts = scripts
        self.call_count = 0

    async def stream(self, messages, model_name, **kwargs):
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.scripts):
            # 防御性兜底:返回空文本 stop,避免无界循环
            yield StreamChunk(text="", finish_reason="stop")
            return
        for chunk in self.scripts[idx]:
            yield chunk


def _tool_call_chunk(name="web_search", args=None, index=0, call_id="call_test_0"):
    """构造一个带 tool_calls 的 StreamChunk (finish_reason 默认 None)。"""
    return StreamChunk(
        tool_calls=[{
            "index": index,
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args or {}, ensure_ascii=False),
            },
        }],
    )


class TestFinishReasonCompat:
    """S4: finish_reason 兼容判断测试。"""

    async def _run_stream_reply(self, provider, persona=None):
        """运行 stream_reply 并返回 (events, provider)。"""
        from server.services.chat_service import ChatService

        persona = persona or _make_persona()
        svc = ChatService()
        with patch("server.services.chat_service.get_provider", return_value=provider), \
             patch("server.services.chat_service.async_session") as mock_sf, \
             patch("server.services.chat_service.knowledge_service") as mock_kb, \
             patch("server.services.chat_service.tool_executor") as mock_te, \
             patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):
            _setup_stream_reply_mocks(persona, mock_sf)
            mock_kb.search = AsyncMock(return_value=[])
            mock_te.execute = AsyncMock(return_value={
                "success": True, "output": "ok", "error": "", "duration_ms": 10,
            })
            events = [e async for e in svc.stream_reply(1, "hi")]
        return events, provider

    async def test_finish_reason_none_with_tool_calls_continues(self):
        """finish_reason=None + tool_calls 非空 → 应继续执行工具 (S4 核心修复点)。

        旧逻辑 `finish_reason != "tool_calls"` → None != "tool_calls" 为 True → 误 break。
        新逻辑: finish_reason is None 时不进入第二层 break,继续执行工具。
        """
        provider = _ScriptedProvider(scripts=[
            [_tool_call_chunk()],  # tool_calls + finish_reason=None
            [StreamChunk(text="完成", finish_reason="stop")],
        ])
        events, prov = await self._run_stream_reply(provider)

        types = [e["type"] for e in events]
        assert "tool_call" in types, "finish_reason=None + tool_calls 应继续执行工具"
        assert "tool_result" in types
        assert "done" in types
        assert prov.call_count == 2, "应执行两轮 (工具调用 + 文本收尾)"

    async def test_finish_reason_tool_calls_continues(self):
        """finish_reason='tool_calls' + tool_calls 非空 → 应继续执行工具。"""
        provider = _ScriptedProvider(scripts=[
            [_tool_call_chunk(), StreamChunk(finish_reason="tool_calls")],
            [StreamChunk(text="完成", finish_reason="stop")],
        ])
        events, prov = await self._run_stream_reply(provider)

        types = [e["type"] for e in events]
        assert "tool_call" in types
        assert "tool_result" in types
        assert "done" in types
        assert prov.call_count == 2

    async def test_finish_reason_stop_breaks(self):
        """finish_reason='stop' + tool_calls=[] → 应 break,不执行工具。"""
        provider = _ScriptedProvider(scripts=[
            [StreamChunk(text="纯文本回答", finish_reason="stop")],
        ])
        events, prov = await self._run_stream_reply(provider)

        types = [e["type"] for e in events]
        assert "tool_call" not in types, "finish_reason=stop 且无 tool_calls 不应执行工具"
        assert "token" in types
        assert "done" in types
        assert prov.call_count == 1, "应只执行一轮即 break"

    async def test_no_tool_calls_breaks(self):
        """tool_calls 为空 → 应 break (无论 finish_reason 取值)。"""
        provider = _ScriptedProvider(scripts=[
            [StreamChunk(text="回答", finish_reason=None)],
        ])
        events, prov = await self._run_stream_reply(provider)

        types = [e["type"] for e in events]
        assert "tool_call" not in types
        assert "done" in types
        assert prov.call_count == 1
