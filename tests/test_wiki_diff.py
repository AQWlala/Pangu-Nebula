"""Tests for Wiki Diff 结构化输出 (T2.6)。"""

import pytest

from server.services.wiki_review_service import WikiReviewService

_service = WikiReviewService()


async def _submit(session, **kw):
    defaults = dict(
        wiki_id=1,
        title="Diff Test",
        proposed_content="line A\nline B\nline C",
        current_content="line A\nline B\nline C",
        scope="default",
    )
    defaults.update(kw)
    return await _service.submit_for_review(session, **defaults)


class TestWikiDiffStructured:
    """T2.6: 结构化 diff 输出"""

    @pytest.mark.asyncio
    async def test_diff_no_changes(self, db_session):
        """无变化时 structured 应为空(全 context)"""
        item = await _submit(db_session)
        result = await _service.get_diff(db_session, item["id"])
        assert result["has_changes"] is False
        # structured 仍存在但只有 context 行
        assert "structured" in result
        assert all(s["type"] == "context" for s in result["structured"])
        assert result["stats"]["added"] == 0
        assert result["stats"]["removed"] == 0

    @pytest.mark.asyncio
    async def test_diff_with_added_lines(self, db_session):
        """新增行高亮"""
        item = await _submit(
            db_session,
            current_content="line A\nline B",
            proposed_content="line A\nline B\nline C\nline D",
        )
        result = await _service.get_diff(db_session, item["id"])
        assert result["has_changes"] is True
        added = [s for s in result["structured"] if s["type"] == "added"]
        assert len(added) == 2
        # 新增行的 new_line_no 不为 None,old_line_no 为 None
        for a in added:
            assert a["new_line_no"] is not None
            assert a["old_line_no"] is None
        assert result["stats"]["added"] == 2
        assert result["stats"]["removed"] == 0

    @pytest.mark.asyncio
    async def test_diff_with_removed_lines(self, db_session):
        """删除行高亮"""
        item = await _submit(
            db_session,
            current_content="line A\nline B\nline C\nline D",
            proposed_content="line A\nline B",
        )
        result = await _service.get_diff(db_session, item["id"])
        assert result["has_changes"] is True
        removed = [s for s in result["structured"] if s["type"] == "removed"]
        assert len(removed) == 2
        # 删除行的 old_line_no 不为 None,new_line_no 为 None
        for r in removed:
            assert r["old_line_no"] is not None
            assert r["new_line_no"] is None
        assert result["stats"]["removed"] == 2
        assert result["stats"]["added"] == 0

    @pytest.mark.asyncio
    async def test_diff_with_modified_lines(self, db_session):
        """修改行(替换)高亮 - 应同时产生 added 和 removed"""
        item = await _submit(
            db_session,
            current_content="line A\nline B\nline C",
            proposed_content="line A\nline X\nline C",
        )
        result = await _service.get_diff(db_session, item["id"])
        assert result["has_changes"] is True
        added = [s for s in result["structured"] if s["type"] == "added"]
        removed = [s for s in result["structured"] if s["type"] == "removed"]
        assert len(added) == 1
        assert len(removed) == 1
        assert added[0]["content"] == "line X"
        assert removed[0]["content"] == "line B"

    @pytest.mark.asyncio
    async def test_diff_structured_preserves_context(self, db_session):
        """未变化行应标记为 context 并保留双侧行号"""
        item = await _submit(
            db_session,
            current_content="line A\nline B\nline C",
            proposed_content="line A\nline X\nline C",
        )
        result = await _service.get_diff(db_session, item["id"])
        context_lines = [s for s in result["structured"] if s["type"] == "context"]
        assert len(context_lines) == 2
        # context 行的双侧行号都应有值
        for c in context_lines:
            assert c["old_line_no"] is not None
            assert c["new_line_no"] is not None
        # 验证内容
        contents = [c["content"] for c in context_lines]
        assert "line A" in contents
        assert "line C" in contents

    @pytest.mark.asyncio
    async def test_diff_returns_unified_text_too(self, db_session):
        """同时返回 unified diff 文本(向后兼容)"""
        item = await _submit(
            db_session,
            current_content="line A\nline B",
            proposed_content="line A\nline C",
        )
        result = await _service.get_diff(db_session, item["id"])
        # unified diff 文本应包含 - 和 + 标记
        assert "-line B" in result["diff"]
        assert "+line C" in result["diff"]
        # 同时存在 structured 字段
        assert "structured" in result
        assert isinstance(result["structured"], list)
