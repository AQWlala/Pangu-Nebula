"""Tests for SpongeEngine - automatic memory extraction from conversations."""

import pytest
from unittest.mock import patch, MagicMock
from server.services.sponge_engine import SpongeEngine, SpongeResult


def _make_msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def _mock_generate_json(json_str: str):
    async def gen(messages, model, temperature=0.7, max_tokens=4096):
        yield json_str
    return gen


class TestSpongeEngine:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_no_extraction(self):
        engine = SpongeEngine()
        result = await engine.absorb([], persona_id=1)
        assert result.extracted is False

    @pytest.mark.asyncio
    async def test_extracts_memory_when_valuable(self):
        mock_gen = _mock_generate_json(
            '{"should_extract": true, "layer": "L3", "title": "Python preference", '
            '"html_content": "<p>User prefers Python for backend development.</p>", '
            '"importance": 0.8, "tags": ["python", "preference"]}'
        )
        with patch("server.services.sponge_engine.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.generate = mock_gen
            mock_get.return_value = mock_provider

            engine = SpongeEngine()
            msgs = [
                _make_msg("user", "I prefer Python over Java for backend development."),
                _make_msg("assistant", "Noted, Python is great for backends."),
            ]
            result = await engine.absorb(msgs, persona_id=1)
            assert result.extracted is True
            assert result.memory is not None

    @pytest.mark.asyncio
    async def test_no_extraction_when_not_valuable(self):
        mock_gen = _mock_generate_json(
            '{"should_extract": false, "reason": "Just a greeting"}'
        )
        with patch("server.services.sponge_engine.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.generate = mock_gen
            mock_get.return_value = mock_provider

            engine = SpongeEngine()
            msgs = [_make_msg("user", "Hi!"), _make_msg("assistant", "Hello!")]
            result = await engine.absorb(msgs, persona_id=1)
            assert result.extracted is False

    @pytest.mark.asyncio
    async def test_dedup_with_existing_memories(self):
        mock_gen = _mock_generate_json(
            '{"should_extract": false, "reason": "Similar memory exists"}'
        )
        with patch("server.services.sponge_engine.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.generate = mock_gen
            mock_get.return_value = mock_provider

            engine = SpongeEngine()
            existing = [{"title": "Python preference", "content": "Python over Java"}]
            msgs = [_make_msg("user", "I really like Python.")]
            result = await engine.absorb(msgs, persona_id=1, existing_memories=existing)
            assert result.extracted is False

    @pytest.mark.asyncio
    async def test_batch_absorb(self):
        mock_gen = _mock_generate_json(
            '{"should_extract": false, "reason": "Nothing to extract"}'
        )
        with patch("server.services.sponge_engine.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.generate = mock_gen
            mock_get.return_value = mock_provider

            engine = SpongeEngine()
            messages = [
                _make_msg("user", "msg1"),
                _make_msg("assistant", "reply1"),
            ]
            results = await engine.batch_absorb(messages, persona_id=1)
            assert len(results) >= 1
