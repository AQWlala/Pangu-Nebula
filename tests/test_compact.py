"""Tests for CompactEngine - context compression strategy selection."""

import pytest
from server.services.compact import CompactEngine, CompactResult


def _make_msg(role: str, text: str) -> dict:
    return {"role": role, "content": text}


class TestEstimateTokens:
    def test_empty_messages(self):
        engine = CompactEngine()
        assert engine.estimate_tokens([]) == 0

    def test_english_text(self):
        engine = CompactEngine()
        msgs = [_make_msg("user", "hello world")]
        tokens = engine.estimate_tokens(msgs)
        assert 6 <= tokens <= 8

    def test_chinese_text(self):
        engine = CompactEngine()
        msgs = [_make_msg("user", "你好世界")]
        tokens = engine.estimate_tokens(msgs)
        assert tokens == 6

    def test_mixed_text(self):
        engine = CompactEngine()
        msgs = [_make_msg("user", "hello 你好")]
        tokens = engine.estimate_tokens(msgs)
        assert tokens == 6


class TestShouldCompact:
    def test_below_threshold_returns_none(self):
        engine = CompactEngine(max_tokens=1000)
        msgs = [_make_msg("user", "short")]
        assert engine.should_compact(msgs) == "none"

    def test_above_compact_threshold_returns_auto(self):
        engine = CompactEngine(max_tokens=100, compact_threshold=0.8)
        msgs = [_make_msg("user", "x" * 340)]
        assert engine.should_compact(msgs) == "auto"

    def test_above_emergency_threshold_returns_emergency(self):
        engine = CompactEngine(max_tokens=100, emergency_threshold=0.95)
        msgs = [_make_msg("user", "x" * 380)]
        assert engine.should_compact(msgs) == "emergency"


class TestEmergencyCompact:
    @pytest.mark.asyncio
    async def test_short_messages_unchanged(self):
        engine = CompactEngine()
        msgs = [_make_msg("system", "s"), _make_msg("user", "u")]
        result = await engine.emergency_compact(msgs)
        assert result == msgs

    @pytest.mark.asyncio
    async def test_long_messages_compacted(self):
        engine = CompactEngine()
        msgs = [
            _make_msg("system", "you are helpful"),
            _make_msg("user", "msg1"),
            _make_msg("assistant", "msg2"),
            _make_msg("user", "msg3"),
            _make_msg("assistant", "msg4"),
            _make_msg("user", "msg5"),
        ]
        result = await engine.emergency_compact(msgs)
        assert len(result) <= 5
        assert result[0]["role"] == "system"
        assert any("compacted" in m.get("content", "") for m in result)


class TestAutoCompact:
    @pytest.mark.asyncio
    async def test_few_messages_unchanged(self):
        engine = CompactEngine()
        msgs = [
            _make_msg("system", "s"),
            _make_msg("user", "u"),
            _make_msg("assistant", "a"),
        ]
        async def fake_llm(m):
            return "summary"
        result = await engine.auto_compact(msgs, fake_llm)
        assert result == msgs

    @pytest.mark.asyncio
    async def test_many_messages_compacted(self):
        engine = CompactEngine()
        msgs = [_make_msg("system", "sys")]
        for i in range(10):
            msgs.append(_make_msg("user", "msg" + str(i)))
            msgs.append(_make_msg("assistant", "reply" + str(i)))

        async def fake_llm(m):
            return "summarized content"

        result = await engine.auto_compact(msgs, fake_llm)
        assert len(result) < len(msgs)
        assert result[0] == msgs[0]
        assert any("Summary" in m.get("content", "") for m in result)


class TestCompactIfNeeded:
    @pytest.mark.asyncio
    async def test_no_compact_when_below_threshold(self):
        engine = CompactEngine(max_tokens=10000)
        msgs = [_make_msg("user", "hello")]
        result = await engine.compact_if_needed(msgs)
        assert result.compacted is False
        assert result.strategy == "none"
        assert result.tokens_before == result.tokens_after

    @pytest.mark.asyncio
    async def test_emergency_compact_when_over_limit(self):
        engine = CompactEngine(max_tokens=100, emergency_threshold=0.5)
        msgs = [_make_msg("user", "x" * 400)]
        result = await engine.compact_if_needed(msgs)
        assert result.compacted is True
        assert result.strategy == "emergency"
        assert result.tokens_after <= result.tokens_before

    @pytest.mark.asyncio
    async def test_auto_compact_with_llm(self):
        engine = CompactEngine(max_tokens=500, compact_threshold=0.2, emergency_threshold=0.9)
        msgs = []
        for i in range(15):
            msgs.append(_make_msg("user", "msg" + str(i)))
            msgs.append(_make_msg("assistant", "reply" + str(i)))

        async def fake_llm(m):
            return "summary of conversation"

        result = await engine.compact_if_needed(msgs, fake_llm)
        assert result.compacted is True
        assert result.strategy == "auto"
        assert result.tokens_after < result.tokens_before
