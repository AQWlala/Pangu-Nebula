"""Tests for WikiReviewService - 知识库安全写回。"""

import pytest

from server.services.wiki_review_service import WikiReviewService

_service = WikiReviewService()


async def _submit(session, **kw):
    defaults = dict(
        wiki_id=1,
        title="Update Page",
        proposed_content="new content line1\nnew content line2",
        current_content="old content line1\nold content line2",
        scope="default",
    )
    defaults.update(kw)
    return await _service.submit_for_review(session, **defaults)


class TestWikiReviewSubmit:
    @pytest.mark.asyncio
    async def test_submit_for_review(self, db_session):
        result = await _submit(db_session, title="My Update")
        assert result["id"] is not None
        assert result["title"] == "My Update"
        assert result["status"] == "pending"
        assert result["proposed_by"] == "agent"
        assert result["scope"] == "default"


class TestWikiReviewList:
    @pytest.mark.asyncio
    async def test_list_pending(self, db_session):
        await _submit(db_session, title="A")
        await _submit(db_session, title="B")
        result = await _service.list_pending(db_session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_pending_excludes_merged(self, db_session):
        item = await _submit(db_session, title="To Merge")
        await _service.merge(db_session, item["id"])
        result = await _service.list_pending(db_session)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_pending_by_scope(self, db_session):
        await _submit(db_session, title="Default", scope="default")
        await _submit(db_session, title="Custom", scope="custom-scope")
        default_items = await _service.list_pending(db_session, scope="default")
        assert len(default_items) == 1
        assert default_items[0]["title"] == "Default"


class TestWikiReviewDiff:
    @pytest.mark.asyncio
    async def test_get_diff(self, db_session):
        item = await _submit(
            db_session,
            current_content="line A\nline B",
            proposed_content="line A\nline C",
        )
        result = await _service.get_diff(db_session, item["id"])
        assert result["has_changes"] is True
        assert "line B" in result["diff"]
        assert "line C" in result["diff"]
        # unified diff 标记
        assert "-line B" in result["diff"]
        assert "+line C" in result["diff"]


class TestWikiReviewMerge:
    @pytest.mark.asyncio
    async def test_merge(self, db_session):
        item = await _submit(db_session, title="Merge Me")
        result = await _service.merge(db_session, item["id"], review_note="LGTM")
        assert result["status"] == "merged"
        assert result["review_note"] == "LGTM"
        assert result["reviewed_at"] is not None


class TestWikiReviewDiscard:
    @pytest.mark.asyncio
    async def test_discard(self, db_session):
        item = await _submit(db_session, title="Discard Me")
        result = await _service.discard(db_session, item["id"], review_note="nope")
        assert result["status"] == "discarded"
        assert result["review_note"] == "nope"


class TestURLSnapshotSSRF:
    @pytest.mark.asyncio
    async def test_ssrf_blocked_localhost(self, db_session):
        result = await _service.snapshot_url(db_session, "http://127.0.0.1:8080/secret")
        assert result["blocked"] is True
        assert result["status"] == "ssrf_blocked"
        assert result["blocked"] is True

    @pytest.mark.asyncio
    async def test_ssrf_blocked_localhost_name(self, db_session):
        result = await _service.snapshot_url(db_session, "http://localhost/admin")
        assert result["blocked"] is True
        assert result["status"] == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_ssrf_blocked_private_10(self, db_session):
        result = await _service.snapshot_url(db_session, "http://10.0.0.1/internal")
        assert result["blocked"] is True

    @pytest.mark.asyncio
    async def test_ssrf_allowed_public(self, db_session):
        result = await _service.snapshot_url(db_session, "https://example.com/page")
        assert result["blocked"] is False
        assert result["status"] == "ok"
        assert result["snapshot_content"] is not None


class TestScopeCheck:
    @pytest.mark.asyncio
    async def test_check_scope_default_allow(self, db_session):
        # 未配置白名单时默认允许
        assert await _service.check_scope("agent-1", "default") is True
        assert await _service.check_scope("agent-1", "any-scope") is True
