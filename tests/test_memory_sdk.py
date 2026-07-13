"""Tests for pangu_memory_sdk — independent memory system SDK.

Covers:
1. MemoryStore initialization
2. add + get workflow
3. search (with mock-friendly content)
4. LWWRegister merge correctness
5. ORSet add/remove/merge correctness
6. SpongeStrategy pluggability (DefaultSpongeStrategy instantiable)
7. CompressionStrategy pluggability (SummaryCompression instantiable)
Plus extras: list/filter, update, delete, link/backlinks, CRDTSyncManager export/import.
"""

from datetime import datetime, timedelta

import pytest

from server.sdk import (
    CRDTSyncManager,
    CompressionStrategy,
    Memory,
    MemoryLayer,
    MemoryStore,
    SpongeStrategy,
)
from server.sdk.blackhole import (
    KeywordCompression,
    SemanticCompression,
    SummaryCompression,
)
from server.sdk.crdt import LWWRegister, ORSet
from server.sdk.sponge import (
    AggressiveSpongeStrategy,
    ConservativeSpongeStrategy,
    DefaultSpongeStrategy,
)


@pytest.fixture
async def store():
    s = MemoryStore(db_path=":memory:")
    await s.init()
    yield s
    await s.close()


# ----------------------------------------------------------------------
# 1. MemoryStore 可初始化
# ----------------------------------------------------------------------


class TestMemoryStoreInit:
    @pytest.mark.asyncio
    async def test_init_creates_store(self):
        s = MemoryStore(db_path=":memory:")
        await s.init()
        assert s._db is not None
        await s.close()

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self, store):
        # init again should not raise
        await store.init()
        assert store._db is not None


# ----------------------------------------------------------------------
# 2. add + get 正常工作
# ----------------------------------------------------------------------


class TestMemoryStoreAddGet:
    @pytest.mark.asyncio
    async def test_add_returns_memory(self, store):
        mem = await store.add("hello world", layer=MemoryLayer.L1_EPISODIC)
        assert mem.id != ""
        assert mem.content == "hello world"
        assert mem.metadata.layer == MemoryLayer.L1_EPISODIC

    @pytest.mark.asyncio
    async def test_add_with_string_layer(self, store):
        mem = await store.add("content", layer="L3")
        assert mem.metadata.layer == MemoryLayer.L3_SEMANTIC

    @pytest.mark.asyncio
    async def test_get_existing(self, store):
        created = await store.add("some memory", layer=MemoryLayer.L2_NARRATIVE)
        fetched = await store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.content == "some memory"
        assert fetched.metadata.layer == MemoryLayer.L2_NARRATIVE

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_with_tags_and_importance(self, store):
        mem = await store.add(
            "tagged memory",
            layer=MemoryLayer.L3_SEMANTIC,
            tags=["python", "ai"],
            importance=0.9,
            source="user",
        )
        fetched = await store.get(mem.id)
        assert fetched is not None
        assert fetched.metadata.tags == ["python", "ai"]
        assert fetched.metadata.importance == 0.9
        assert fetched.metadata.source == "user"


# ----------------------------------------------------------------------
# 3. search 正常工作
# ----------------------------------------------------------------------


class TestMemoryStoreSearch:
    @pytest.mark.asyncio
    async def test_search_finds_matching(self, store):
        await store.add("Python is great for backend", layer=MemoryLayer.L3_SEMANTIC)
        await store.add("JavaScript runs in browser", layer=MemoryLayer.L3_SEMANTIC)
        results = await store.search("Python")
        assert len(results) == 1
        assert "Python" in results[0].content

    @pytest.mark.asyncio
    async def test_search_no_results(self, store):
        await store.add("hello world", layer=MemoryLayer.L1_EPISODIC)
        results = await store.search("zzzznonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_orders_by_importance(self, store):
        await store.add(
            "important Python tip", layer=MemoryLayer.L3_SEMANTIC, importance=0.9
        )
        await store.add(
            "minor Python note", layer=MemoryLayer.L3_SEMANTIC, importance=0.2
        )
        results = await store.search("Python")
        assert len(results) == 2
        assert results[0].metadata.importance >= results[1].metadata.importance


# ----------------------------------------------------------------------
# 4. LWWRegister merge 正确
# ----------------------------------------------------------------------


class TestLWWRegister:
    def test_set_updates_value(self):
        reg = LWWRegister(node_id="node_a")
        ok = reg.set("new_value")
        assert ok is True
        assert reg.value == "new_value"

    def test_set_ignores_older_timestamp(self):
        reg = LWWRegister(value="old", node_id="node_a")
        old_ts = reg.timestamp - timedelta(seconds=10)
        ok = reg.set("newer", timestamp=old_ts)
        assert ok is False
        assert reg.value == "old"

    def test_merge_takes_newer_timestamp(self):
        ts1 = datetime(2025, 1, 1, 12, 0, 0)
        ts2 = datetime(2025, 1, 1, 12, 5, 0)
        reg_a = LWWRegister(value="a", timestamp=ts1, node_id="node_a")
        reg_b = LWWRegister(value="b", timestamp=ts2, node_id="node_b")
        changed = reg_a.merge(reg_b)
        assert changed is True
        assert reg_a.value == "b"
        assert reg_a.node_id == "node_b"

    def test_merge_ignores_older(self):
        ts1 = datetime(2025, 1, 1, 12, 5, 0)
        ts2 = datetime(2025, 1, 1, 12, 0, 0)
        reg_a = LWWRegister(value="a", timestamp=ts1, node_id="node_a")
        reg_b = LWWRegister(value="b", timestamp=ts2, node_id="node_b")
        changed = reg_a.merge(reg_b)
        assert changed is False
        assert reg_a.value == "a"

    def test_merge_tiebreak_by_node_id(self):
        ts = datetime(2025, 1, 1, 12, 0, 0)
        reg_a = LWWRegister(value="a", timestamp=ts, node_id="node_a")
        reg_b = LWWRegister(value="b", timestamp=ts, node_id="node_b")
        changed = reg_a.merge(reg_b)
        assert changed is True
        assert reg_a.value == "b"
        assert reg_a.node_id == "node_b"

    def test_round_trip_dict(self):
        reg = LWWRegister(value="test", node_id="node_x")
        data = reg.to_dict()
        restored = LWWRegister.from_dict(data)
        assert restored.value == "test"
        assert restored.node_id == "node_x"


# ----------------------------------------------------------------------
# 5. ORSet add/remove/merge 正确
# ----------------------------------------------------------------------


class TestORSet:
    def test_add_and_contains(self):
        s = ORSet()
        s.add("apple")
        assert s.contains("apple") is True
        assert s.contains("banana") is False

    def test_get_all(self):
        s = ORSet()
        s.add("a")
        s.add("b")
        s.add("c")
        assert s.get_all() == {"a", "b", "c"}

    def test_remove(self):
        s = ORSet()
        s.add("x")
        removed = s.remove("x")
        assert removed is True
        assert s.contains("x") is False

    def test_remove_nonexistent(self):
        s = ORSet()
        removed = s.remove("nope")
        assert removed is False

    def test_merge_unions_tags(self):
        s_a = ORSet()
        s_a.add("shared")
        s_a.add("only_a")

        s_b = ORSet()
        s_b.add("shared")
        s_b.add("only_b")

        changed = s_a.merge(s_b)
        assert changed is True
        assert s_a.get_all() == {"shared", "only_a", "only_b"}

    def test_merge_idempotent(self):
        s_a = ORSet()
        s_a.add("x")
        s_b = ORSet()
        s_b.add("x")
        s_a.merge(s_b)
        changed = s_a.merge(s_b)
        assert changed is False

    def test_concurrent_add_survives_remove(self):
        # 并发场景: A 添加, B 删除 (基于旧观察), merge 后元素应保留
        s_a = ORSet()
        s_b = ORSet()
        # 两端都先有 "item" 的 tag1
        s_a.add("item", tag="tag1")
        s_b._elements = {"item": {"tag1"}}
        # B 先删除 (观察到 tag1)
        s_b.remove("item")
        # A 同时添加新 tag2
        s_a.add("item", tag="tag2")
        # merge: A 的 tag2 应保留
        s_a.merge(s_b)
        assert s_a.contains("item") is True


# ----------------------------------------------------------------------
# 6. SpongeStrategy 可插拔
# ----------------------------------------------------------------------


class TestSpongeStrategy:
    @pytest.mark.asyncio
    async def test_default_strategy_instantiable(self):
        strategy = DefaultSpongeStrategy()
        assert isinstance(strategy, SpongeStrategy)
        mem = await strategy.absorb("Python is a great language", [])
        assert mem.content == "Python is a great language"
        assert mem.metadata.layer == MemoryLayer.L1_EPISODIC
        assert mem.metadata.source == "sponge"
        assert len(mem.metadata.tags) > 0

    @pytest.mark.asyncio
    async def test_aggressive_strategy_instantiable(self):
        strategy = AggressiveSpongeStrategy()
        assert isinstance(strategy, SpongeStrategy)
        mem = await strategy.absorb("Python is a great language", [])
        assert mem.metadata.layer == MemoryLayer.L2_NARRATIVE
        assert mem.metadata.source == "sponge_aggressive"

    @pytest.mark.asyncio
    async def test_conservative_strategy_instantiable(self):
        strategy = ConservativeSpongeStrategy()
        assert isinstance(strategy, SpongeStrategy)
        mem = await strategy.absorb("Python is a great language", [])
        assert mem.metadata.layer == MemoryLayer.L0_WORKING
        assert mem.metadata.tags == []
        assert mem.metadata.importance == 0.3

    @pytest.mark.asyncio
    async def test_strategies_are_pluggable(self):
        """验证策略可通过基类类型注解互换"""
        strategies: list[SpongeStrategy] = [
            DefaultSpongeStrategy(),
            AggressiveSpongeStrategy(),
            ConservativeSpongeStrategy(),
        ]
        for s in strategies:
            mem = await s.absorb("test content", [])
            assert isinstance(mem, Memory)


# ----------------------------------------------------------------------
# 7. CompressionStrategy 可插拔
# ----------------------------------------------------------------------


class TestCompressionStrategy:
    def _make_memories(self) -> list[Memory]:
        return [
            Memory(
                id=f"m{i}",
                content=f"memory content {i} about python",
                metadata=__import__(
                    "pangu_memory_sdk.types", fromlist=["MemoryMetadata"]
                ).MemoryMetadata(
                    layer=MemoryLayer.L1_EPISODIC,
                    tags=[f"tag{i % 2}"],
                    importance=0.5 + i * 0.1,
                ),
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_summary_compression_instantiable(self):
        strategy = SummaryCompression()
        assert isinstance(strategy, CompressionStrategy)
        memories = self._make_memories()
        result = await strategy.compress(memories)
        assert result.metadata.layer == MemoryLayer.L2_NARRATIVE
        assert "memory content" in result.content
        assert len(result.metadata.backlinks) == 3

    @pytest.mark.asyncio
    async def test_keyword_compression_instantiable(self):
        strategy = KeywordCompression()
        assert isinstance(strategy, CompressionStrategy)
        memories = self._make_memories()
        result = await strategy.compress(memories)
        assert "[Keyword Index]" in result.content
        assert len(result.metadata.tags) > 0

    @pytest.mark.asyncio
    async def test_semantic_compression_instantiable(self):
        strategy = SemanticCompression()
        assert isinstance(strategy, CompressionStrategy)
        memories = self._make_memories()
        result = await strategy.compress(memories)
        assert result.metadata.layer == MemoryLayer.L2_NARRATIVE
        assert "tag0" in result.content or "tag1" in result.content

    @pytest.mark.asyncio
    async def test_compression_empty_raises(self):
        strategy = SummaryCompression()
        with pytest.raises(ValueError):
            await strategy.compress([])

    @pytest.mark.asyncio
    async def test_strategies_are_pluggable(self):
        strategies: list[CompressionStrategy] = [
            SummaryCompression(),
            KeywordCompression(),
            SemanticCompression(),
        ]
        memories = self._make_memories()
        for s in strategies:
            result = await s.compress(memories)
            assert isinstance(result, Memory)


# ----------------------------------------------------------------------
# 额外: list / update / delete / link / CRDTSyncManager
# ----------------------------------------------------------------------


class TestMemoryStoreListUpdateDelete:
    @pytest.mark.asyncio
    async def test_list_all(self, store):
        await store.add("first", layer=MemoryLayer.L1_EPISODIC)
        await store.add("second", layer=MemoryLayer.L2_NARRATIVE)
        results = await store.list()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_by_layer(self, store):
        await store.add("a", layer=MemoryLayer.L1_EPISODIC)
        await store.add("b", layer=MemoryLayer.L3_SEMANTIC)
        results = await store.list(layer=MemoryLayer.L1_EPISODIC)
        assert len(results) == 1
        assert results[0].metadata.layer == MemoryLayer.L1_EPISODIC

    @pytest.mark.asyncio
    async def test_update_content(self, store):
        mem = await store.add("original", layer=MemoryLayer.L1_EPISODIC)
        updated = await store.update(mem.id, content="updated content")
        assert updated.content == "updated content"
        assert updated.id == mem.id

    @pytest.mark.asyncio
    async def test_update_importance(self, store):
        mem = await store.add("content", layer=MemoryLayer.L1_EPISODIC, importance=0.3)
        updated = await store.update(mem.id, importance=0.9)
        assert updated.metadata.importance == 0.9

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self, store):
        with pytest.raises(KeyError):
            await store.update("nonexistent", content="x")

    @pytest.mark.asyncio
    async def test_delete_existing(self, store):
        mem = await store.add("to delete", layer=MemoryLayer.L1_EPISODIC)
        deleted = await store.delete(mem.id)
        assert deleted is True
        assert await store.get(mem.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        deleted = await store.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_link_creates_backlinks(self, store):
        a = await store.add("memory A", layer=MemoryLayer.L1_EPISODIC)
        b = await store.add("memory B", layer=MemoryLayer.L1_EPISODIC)
        ok = await store.link(a.id, b.id)
        assert ok is True
        backlinks_a = await store.get_backlinks(a.id)
        backlinks_b = await store.get_backlinks(b.id)
        assert any(m.id == b.id for m in backlinks_a)
        assert any(m.id == a.id for m in backlinks_b)


class TestCRDTSyncManager:
    def test_get_register_creates_lazily(self):
        mgr = CRDTSyncManager(node_id="node1")
        reg = mgr.get_register("key1")
        assert reg.node_id == "node1"
        assert "key1" in mgr._registers

    def test_get_set_creates_lazily(self):
        mgr = CRDTSyncManager()
        s = mgr.get_set("tags")
        assert "tags" in mgr._sets

    def test_export_import_state(self):
        # 使用显式时间戳确保 mgr_a 的写入更新,演示 LWW 正确性
        newer_ts = datetime.utcnow() + timedelta(seconds=10)

        mgr_b = CRDTSyncManager(node_id="node_b")
        mgr_b.set_register("title", "World")  # 较旧的本地写入
        mgr_b.add_to_set("tags", "rust")

        mgr_a = CRDTSyncManager(node_id="node_a")
        mgr_a.get_register("title").set("Hello", timestamp=newer_ts)  # 更新的写入
        mgr_a.add_to_set("tags", "python")
        mgr_a.add_to_set("tags", "ai")

        state = mgr_a.export_state()
        assert "registers" in state
        assert "sets" in state
        assert state["node_id"] == "node_a"

        changed = mgr_b.import_state(state)
        assert changed is True
        # LWW: mgr_a 的 timestamp 更新, 应覆盖 mgr_b 的旧值
        assert mgr_b.get_register("title").value == "Hello"
        # OR-Set merge: tags 应包含全部
        assert mgr_b.get_set("tags").get_all() == {"python", "ai", "rust"}

    def test_import_idempotent(self):
        mgr_a = CRDTSyncManager(node_id="node_a")
        mgr_a.set_register("k", "v")
        state = mgr_a.export_state()

        mgr_b = CRDTSyncManager(node_id="node_b")
        mgr_b.import_state(state)
        changed = mgr_b.import_state(state)
        assert changed is False
