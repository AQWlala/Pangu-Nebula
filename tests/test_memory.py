"""Tests for MemoryService - 6-layer memory CRUD and graph operations."""

import pytest
from server.services.memory_service import MemoryService

_service = MemoryService()


async def _create(session, **kw):
    defaults = dict(
        persona_id=None, layer="L3", title="Test Memory",
        html_content="<p>Content</p>", importance=0.7,
    )
    defaults.update(kw)
    return await _service.create_memory(session, **defaults)


class TestCreateMemory:
    @pytest.mark.asyncio
    async def test_basic_create(self, db_session):
        result = await _create(db_session)
        assert result["id"] is not None
        assert result["layer"] == "L3"
        assert result["title"] == "Test Memory"
        assert result["importance"] == 0.7

    @pytest.mark.asyncio
    async def test_extracts_links_from_html(self, db_session):
        result = await _create(
            db_session,
            title="Linked",
            html_content='<p>See [[Python]] and [[FastAPI]]</p>',
        )
        assert "Python" in result["links"]
        assert "FastAPI" in result["links"]

    @pytest.mark.asyncio
    async def test_extracts_plain_text(self, db_session):
        result = await _create(
            db_session,
            html_content="<h1>Title</h1><p>Hello <b>World</b></p>",
        )
        assert "Title" in result["plain_text"]
        assert "Hello World" in result["plain_text"]

    @pytest.mark.asyncio
    async def test_with_tags(self, db_session):
        result = await _create(db_session, tags=["python", "ai"])
        assert result["tags"] == ["python", "ai"]

    @pytest.mark.asyncio
    async def test_persona_scoped(self, db_session):
        result = await _create(db_session, persona_id=42)
        assert result["persona_id"] == 42


class TestGetMemory:
    @pytest.mark.asyncio
    async def test_get_existing(self, db_session):
        created = await _create(db_session)
        result = await _service.get_memory(db_session, created["id"])
        assert result is not None
        assert result["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db_session):
        result = await _service.get_memory(db_session, 99999)
        assert result is None


class TestListMemories:
    @pytest.mark.asyncio
    async def test_list_empty(self, db_session):
        results = await _service.list_memories(db_session)
        assert results == []

    @pytest.mark.asyncio
    async def test_list_with_data(self, db_session):
        await _create(db_session, title="First")
        await _create(db_session, title="Second")
        results = await _service.list_memories(db_session)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_with_layer_filter(self, db_session):
        await _create(db_session, layer="L1", title="L1 Memory")
        await _create(db_session, layer="L3", title="L3 Memory")
        results = await _service.list_memories(db_session, layer="L1")
        assert len(results) == 1
        assert results[0]["layer"] == "L1"


class TestUpdateMemory:
    @pytest.mark.asyncio
    async def test_update_title(self, db_session):
        created = await _create(db_session)
        result = await _service.update_memory(db_session, created["id"], title="Updated")
        assert result["title"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_updates_links(self, db_session):
        created = await _create(db_session, html_content="<p>Old</p>")
        result = await _service.update_memory(
            db_session, created["id"], html_content="<p>[[NewLink]]</p>"
        )
        assert "NewLink" in result["links"]

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, db_session):
        result = await _service.update_memory(db_session, 99999, title="X")
        assert result is None


class TestDeleteMemory:
    @pytest.mark.asyncio
    async def test_delete_existing(self, db_session):
        created = await _create(db_session)
        deleted = await _service.delete_memory(db_session, created["id"])
        assert deleted is True
        assert await _service.get_memory(db_session, created["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db_session):
        deleted = await _service.delete_memory(db_session, 99999)
        assert deleted is False


class TestSearchMemories:
    @pytest.mark.asyncio
    async def test_search_by_title(self, db_session):
        await _create(db_session, title="Python Async")
        await _create(db_session, title="JavaScript Basics")
        results = await _service.search_memories(db_session, "python")
        assert len(results) == 1
        assert results[0]["title"] == "Python Async"

    @pytest.mark.asyncio
    async def test_search_by_content(self, db_session):
        await _create(db_session, html_content="<p>Machine Learning</p>")
        results = await _service.search_memories(db_session, "learning")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session):
        results = await _service.search_memories(db_session, "zzzzz")
        assert results == []


class TestBacklinks:
    @pytest.mark.asyncio
    async def test_backlinks_created_on_link(self, db_session):
        a = await _create(db_session, title="Target A")
        await _create(db_session, title="Source B", html_content="<p>See [[" + a["title"] + "]]</p>")
        updated_a = await _service.get_memory(db_session, a["id"])
        assert len(updated_a["backlinks"]) >= 1

    @pytest.mark.asyncio
    async def test_get_backlinks_api(self, db_session):
        a = await _create(db_session, title="Target")
        await _create(db_session, html_content="<p>Ref [[Target]]</p>")
        backlinks = await _service.get_backlinks(db_session, a["id"])
        assert len(backlinks) >= 1


class TestLinkedGraph:
    @pytest.mark.asyncio
    async def test_graph_with_links(self, db_session):
        await _create(db_session, title="Node A", html_content="<p>See [[Node B]]</p>")
        await _create(db_session, title="Node B")
        graph = await _service.get_linked_graph(db_session)
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) >= 2
