"""Tests for AutoWorkService - 无人值守任务框架。"""

import pytest

from server.services.autowork_service import AutoWorkService

_service = AutoWorkService()


async def _create(session, **kw):
    defaults = dict(title="Test Task", description="desc", config={})
    defaults.update(kw)
    return await _service.create_session(session, **defaults)


class TestAutoWorkCreate:
    @pytest.mark.asyncio
    async def test_create_session(self, db_session):
        result = await _create(db_session, title="My Task")
        assert result["id"] is not None
        assert result["title"] == "My Task"
        assert result["status"] == "pending"
        assert result["priority"] == 0
        assert result["assigned_to"] is None


class TestAutoWorkList:
    @pytest.mark.asyncio
    async def test_list_sessions(self, db_session):
        await _create(db_session, title="Task A")
        await _create(db_session, title="Task B")
        results = await _service.list_sessions(db_session)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_by_status(self, db_session):
        await _create(db_session, title="Pending Task")
        created = await _create(db_session, title="Running Task")
        await _service.claim_session(db_session, created["id"], "agent")
        pending = await _service.list_sessions(db_session, status="pending")
        assert len(pending) == 1
        assert pending[0]["title"] == "Pending Task"
        running = await _service.list_sessions(db_session, status="running")
        assert len(running) == 1


class TestAutoWorkClaim:
    @pytest.mark.asyncio
    async def test_claim_session(self, db_session):
        created = await _create(db_session, title="Claimable")
        result = await _service.claim_session(db_session, created["id"], "worker-1")
        assert result["status"] == "running"
        assert result["assigned_to"] == "worker-1"


class TestAutoWorkComplete:
    @pytest.mark.asyncio
    async def test_complete_session(self, db_session):
        created = await _create(db_session, title="Completable")
        result = await _service.complete_session(db_session, created["id"], "all done")
        assert result["status"] == "completed"
        assert result["result"] == "all done"
        assert result["completed_at"] is not None


class TestAutoWorkKanban:
    @pytest.mark.asyncio
    async def test_kanban_grouping(self, db_session):
        # pending x2
        await _create(db_session, title="P1")
        await _create(db_session, title="P2")
        # running x1
        running = await _create(db_session, title="R1")
        await _service.claim_session(db_session, running["id"], "agent")
        # completed x1
        completed = await _create(db_session, title="C1")
        await _service.complete_session(db_session, completed["id"], "ok")

        kanban = await _service.get_kanban(db_session)
        assert kanban["total"] == 4
        assert len(kanban["groups"]["pending"]) == 2
        assert len(kanban["groups"]["running"]) == 1
        assert len(kanban["groups"]["completed"]) == 1
        assert kanban["counts"]["pending"] == 2
        assert kanban["counts"]["running"] == 1
        assert kanban["counts"]["completed"] == 1


class TestAutoWorkNotification:
    @pytest.mark.asyncio
    async def test_send_notification_mock(self, db_session):
        result = await _service.send_notification("slack", "hello")
        assert result["ok"] is True
        assert result["mock"] is True
        assert result["channel"] == "slack"
        assert result["message"] == "hello"
