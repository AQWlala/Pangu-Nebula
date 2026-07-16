# tests/test_p2_blackhole_and_tags.py
"""v2.2.1 P2 修复测试 — 黑洞引擎 N+1/并发 与 tags JSON 序列化

覆盖:
- P2-4: check_and_compact 合并 5 次 layer 查询为 1 次 (消除 N+1)
- P2-5: compact_layer 并发执行 _compact_group (asyncio.gather)
- P2-5: 单个分组失败不影响其他分组 (return_exceptions=True 隔离)
- P2-6: tags JSON 序列化/反序列化 (含逗号/中文/空/旧格式兼容)
"""
from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.blackhole_engine import BlackHoleEngine, CompressionResult


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_mock_memory(
    id: int,
    content: str,
    tags: list | None = None,
    importance: float = 0.5,
    layer: str = "L0",
    html_content: str | None = None,
):
    """构造 mock Memory ORM 对象,只暴露 compact_layer 读取的属性。"""
    m = MagicMock()
    m.id = id
    m.content = content
    m.html_content = html_content
    m.importance = importance
    m.tags = tags
    m.layer = layer
    return m


def _make_session_cm(mock_session: MagicMock):
    """构造 async context manager, __aenter__ 返回 mock_session。

    async_session() 返回此 CM,支持多次调用 (check_and_compact/compact_layer
    可能多次进入 session 上下文)。
    """
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    return mock_cm


def _make_query_result(rows: list):
    """构造 session.execute() 的返回值,支持 .all() / .scalars().all() 两种用法。"""
    result = MagicMock()
    # check_and_compact 使用 .all()
    result.all.return_value = rows
    # compact_layer 使用 .scalars().all()
    result.scalars.return_value.all.return_value = rows
    return result


# ---------------------------------------------------------------------------
# P2-4: check_and_compact 合并 N+1 查询
# ---------------------------------------------------------------------------

class TestCheckAndCompactGroupBy:
    """验证 check_and_compact 用单次查询替代 5 次 layer 查询。"""

    async def test_check_and_compact_uses_group_by(self):
        """session.execute 应只调用 1 次 (而非 5 次), 且只对超阈值的 layer 触发 compact。"""
        engine = BlackHoleEngine()

        # 构造 (layer, tags) 行:
        # L0: 25 行未压缩 (超阈值 20) + 5 行已压缩 (不计入)
        # L1: 10 行未压缩 (未超阈值 15)
        # L2/L3/L4: 0 行
        rows = []
        rows.extend([("L0", ["work"])] * 25)
        rows.extend([("L0", ["compressed"])] * 5)
        rows.extend([("L1", ["note"])] * 10)

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=_make_query_result(rows))

        # 保存 mock 引用, with 退出后仍可检查 call_count
        mock_compact = AsyncMock(
            return_value=CompressionResult(
                success=True, source_layer="L0", target_layer="L1",
                source_count=25, new_memory={"title": "ok"},
            )
        )

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "compact_layer", new=mock_compact):
            results = await engine.check_and_compact(persona_id=1)

        # 核心断言: 只调用 1 次 execute (合并 N+1)
        assert mock_session.execute.call_count == 1, (
            f"check_and_compact 应只用 1 次 execute 查询 (GROUP BY 合并), "
            f"实际 {mock_session.execute.call_count} 次"
        )
        # L0 超阈值 (25 > 20) 触发 compact; L1 未超 (10 <= 15) 不触发
        assert len(results) == 1
        assert results[0].source_layer == "L0"
        # compact_layer 只被调用 1 次 (L0)
        assert mock_compact.call_count == 1

    async def test_check_and_compact_no_compaction_when_below_threshold(self):
        """所有 layer 都未超阈值时, compact_layer 不被调用, execute 仍只 1 次。"""
        engine = BlackHoleEngine()

        rows = [("L0", ["a"])] * 5 + [("L1", ["b"])] * 5  # 都低于阈值

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=_make_query_result(rows))

        mock_compact = AsyncMock()

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "compact_layer", new=mock_compact):
            results = await engine.check_and_compact(persona_id=1)

        assert mock_session.execute.call_count == 1
        assert results == []
        assert mock_compact.call_count == 0

    async def test_check_and_compact_filters_compressed_tags(self):
        """带 'compressed' tag 的记忆不计入 count (保留原过滤语义)。"""
        engine = BlackHoleEngine()

        # L0 阈值 20: 19 未压缩 + 100 已压缩 = 19, 不触发
        rows = [("L0", ["work"])] * 19 + [("L0", ["compressed"])] * 100

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=_make_query_result(rows))

        mock_compact = AsyncMock()

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "compact_layer", new=mock_compact):
            results = await engine.check_and_compact(persona_id=1)

        assert results == []
        assert mock_compact.call_count == 0


# ---------------------------------------------------------------------------
# P2-5: compact_layer 并发执行 + 故障隔离
# ---------------------------------------------------------------------------

class TestCompactLayerConcurrent:
    """验证 compact_layer 用 asyncio.gather 并发执行 _compact_group。"""

    def _build_mock_memories(self, n_groups: int = 3, per_group: int = 2):
        """构造 n_groups 个分组,每组 per_group 条记忆 (不同首 tag 形成不同分组)。"""
        mems = []
        for g in range(n_groups):
            for i in range(per_group):
                mems.append(_make_mock_memory(
                    id=g * per_group + i + 1,
                    content=f"memory group-{g} item-{i}",
                    tags=[f"group{g}"],
                    importance=0.5 + i * 0.1,
                ))
        return mems

    def _make_compact_layer_session(self, memories: list):
        """构造 compact_layer 使用的 mock session。

        compact_layer 会调用 session.execute 两次:
        1. 首次: 查询 source_layer 的记忆 → 返回 memories
        2. 第二次: 查询 compressed_ids 对应的原记忆 → 返回 [] (不更新)
        """
        mock_session = MagicMock()
        memories_result = MagicMock()
        memories_result.scalars.return_value.all.return_value = memories
        originals_result = MagicMock()
        originals_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(
            side_effect=[memories_result, originals_result]
        )
        mock_session.add = MagicMock()  # sync method
        mock_session.commit = AsyncMock()
        return mock_session

    async def test_compact_layer_concurrent(self):
        """多个分组的 _compact_group 应并发执行 (max_concurrent >= 2)。"""
        engine = BlackHoleEngine()
        mock_memories = self._build_mock_memories(n_groups=3, per_group=2)

        # 追踪并发度
        state = {"in_flight": 0, "max_concurrent": 0}

        async def spy_compact_group(memories, source_layer, target_layer, persona_id):
            state["in_flight"] += 1
            state["max_concurrent"] = max(state["max_concurrent"], state["in_flight"])
            # 让出事件循环,允许其他 gather 任务启动
            await asyncio.sleep(0.05)
            state["in_flight"] -= 1
            return {
                "title": f"compressed-{memories[0]['tags'][0]}",
                "html_content": "<p>summary</p>",
                "importance": 0.8,
                "tags": memories[0]["tags"],
            }

        mock_session = self._make_compact_layer_session(mock_memories)

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "_compact_group", new=spy_compact_group):
            result = await engine.compact_layer(persona_id=1, source_layer="L0")

        # 3 个分组都成功压缩
        assert result.success is True
        assert result.source_count == 6  # 3 组 * 2 条
        # 并发度断言: 串行执行 max_concurrent 永远 == 1, 并发执行 >= 2
        assert state["max_concurrent"] >= 2, (
            f"asyncio.gather 应让多分组并发, max_concurrent={state['max_concurrent']}"
        )

    async def test_compact_group_failure_isolated(self):
        """某个分组抛异常时, 其他分组仍应成功完成。"""
        engine = BlackHoleEngine()
        mock_memories = self._build_mock_memories(n_groups=3, per_group=2)

        call_log = []

        async def flaky_compact_group(memories, source_layer, target_layer, persona_id):
            tag = memories[0]["tags"][0]
            call_log.append(tag)
            if tag == "group1":
                raise RuntimeError("LLM provider down for group1")
            # 让出事件循环,确保 group1 异常不阻塞其他组
            await asyncio.sleep(0.02)
            return {
                "title": f"compressed-{tag}",
                "html_content": "<p>ok</p>",
                "importance": 0.8,
                "tags": [tag],
            }

        mock_session = self._make_compact_layer_session(mock_memories)

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "_compact_group", new=flaky_compact_group):
            result = await engine.compact_layer(persona_id=1, source_layer="L0")

        # 所有 3 个分组都被调用 (失败的不影响其他)
        assert len(call_log) == 3
        # group1 失败, group0 和 group2 成功 → 4 条记忆被压缩
        assert result.success is True
        assert result.source_count == 4  # 2 组 * 2 条

    async def test_compact_group_failure_isolated_all_fail(self):
        """所有分组都失败时, compact_layer 返回失败但不抛异常。"""
        engine = BlackHoleEngine()
        mock_memories = self._build_mock_memories(n_groups=2, per_group=2)

        async def always_fail(memories, source_layer, target_layer, persona_id):
            raise RuntimeError("all LLM down")

        mock_session = self._make_compact_layer_session(mock_memories)

        with patch(
            "server.services.blackhole_engine.async_session",
            return_value=_make_session_cm(mock_session),
        ), patch.object(engine, "_compact_group", new=always_fail):
            result = await engine.compact_layer(persona_id=1, source_layer="L0")

        # 全部失败 → success=False, 不抛异常
        assert result.success is False
        assert "All groups failed" in result.error


# ---------------------------------------------------------------------------
# P2-6: tags JSON 序列化/反序列化
# ---------------------------------------------------------------------------

# 两个模块各自定义了 _serialize_tags / _deserialize_tags, 参数化同时测试
_TAG_MODULE_PATHS = [
    "server.kb.retrieval.lance_store",
    "server.kb.retrieval.vectorstore",
]


def _get_tag_helpers(module_path: str):
    mod = importlib.import_module(module_path)
    return mod._serialize_tags, mod._deserialize_tags


@pytest.mark.parametrize("module_path", _TAG_MODULE_PATHS)
class TestTagsJsonSerialization:
    """验证 tags JSON 序列化在两种存储后端行为一致。"""

    def test_tags_json_roundtrip(self, module_path):
        """含逗号的 tag 经过 serialize→deserialize 应完整还原。"""
        serialize, deserialize = _get_tag_helpers(module_path)
        original = ["a,b", "c", "d,e,f"]
        serialized = serialize(original)
        # 新格式必须是 JSON 数组字符串
        assert serialized.startswith("[")
        assert serialized.endswith("]")
        # 反序列化应还原原始列表 (含逗号的 tag 不被切分)
        assert deserialize(serialized) == original

    def test_tags_empty(self, module_path):
        """空 tags 列表和 None 都应正确处理。"""
        serialize, deserialize = _get_tag_helpers(module_path)
        # 空列表
        assert serialize([]) == "[]"
        assert deserialize("[]") == []
        # None
        assert serialize(None) == "[]"
        assert deserialize(None) == []
        # 空字符串
        assert deserialize("") == []
        assert deserialize("   ") == []

    def test_tags_backward_compat(self, module_path):
        """旧格式 (逗号分隔字符串) 应能降级读取, 不抛异常。"""
        serialize, deserialize = _get_tag_helpers(module_path)
        # 旧格式: 逗号分隔 (不以 [ 开头, 走 split 分支)
        old_data = "work,note,important"
        result = deserialize(old_data)
        assert result == ["work", "note", "important"]
        # 旧格式单 tag
        assert deserialize("solo") == ["solo"]
        # 旧格式空字符串 (split 后过滤空)
        assert deserialize(",") == []

    def test_tags_unicode(self, module_path):
        """中文 / Unicode tags 应正确序列化和反序列化。"""
        serialize, deserialize = _get_tag_helpers(module_path)
        original = ["工作", "学习,笔记", "🌟 emoji"]
        serialized = serialize(original)
        # 反序列化应完整还原
        assert deserialize(serialized) == original
        # 中文旧格式也应能降级读取
        assert deserialize("工作,学习") == ["工作", "学习"]

    def test_tags_serialize_not_a_list(self, module_path):
        """上游误传字符串时, serialize 不应抛异常。"""
        serialize, deserialize = _get_tag_helpers(module_path)
        # 字符串被包成单元素列表
        result = serialize("oops")
        assert deserialize(result) == ["oops"]

    def test_tags_deserialize_list_input(self, module_path):
        """如果存储返回 list 而非 str (如 Arrow object 类型), 应直接返回 list。"""
        _, deserialize = _get_tag_helpers(module_path)
        assert deserialize(["a", "b"]) == ["a", "b"]
        assert deserialize(("x", "y")) == ["x", "y"]


# ---------------------------------------------------------------------------
# P2-6 集成: 验证 LanceVectorStore.upsert/query 使用 JSON tags
# ---------------------------------------------------------------------------

class TestLanceStoreTagsIntegration:
    """集成测试: LanceVectorStore.upsert 写入 JSON tags, query 读取还原。"""

    def test_upsert_serializes_tags_as_json(self):
        """upsert 写入时, tags 字段应是 JSON 字符串 (不是逗号分隔)。"""
        pytest.importorskip("lancedb", reason="lancedb 未安装")
        pytest.importorskip("pyarrow", reason="pyarrow 未安装")

        from pathlib import Path
        import tempfile
        from server.kb.retrieval.lance_store import LanceVectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))

        # mock table 和 embedding
        mock_table = MagicMock()
        mock_table.delete = MagicMock()
        mock_table.add = MagicMock()
        store._table = mock_table
        store._db = MagicMock()

        import numpy as np
        store._embedding_function = MagicMock(return_value=np.array([[0.1, 0.2]]))

        chunks = [{
            "id": "chunk-1",
            "text": "hello",
            "doc_id": "doc-001",
            "scope": "private",
            "tags": ["a,b", "c"],  # 含逗号的 tag
        }]

        with patch("pyarrow.Table.from_pylist") as mock_from_pylist:
            store.upsert(chunks)

        # 验证传给 pa.Table.from_pylist 的 rows 中 tags 是 JSON 字符串
        call_args = mock_from_pylist.call_args[0][0]
        row = call_args[0]
        assert row["tags"] == '["a,b", "c"]', (
            f"tags 应序列化为 JSON, 实际: {row['tags']!r}"
        )

    def test_query_deserializes_tags_from_json(self):
        """query 读取时, JSON 字符串应反序列化为 list。"""
        pytest.importorskip("lancedb", reason="lancedb 未安装")
        pytest.importorskip("pyarrow", reason="pyarrow 未安装")

        from pathlib import Path
        import tempfile
        from server.kb.retrieval.lance_store import LanceVectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))

        # mock table 返回 JSON 格式 tags
        mock_table = MagicMock()
        mock_search_chain = MagicMock()
        mock_search_chain.where.return_value.limit.return_value.to_list.return_value = [
            {"id": "1", "doc_id": "d1", "text": "t1", "scope": "private",
             "tags": '["a,b", "c"]', "_distance": 0.5},
        ]
        mock_table.search = MagicMock(return_value=mock_search_chain)
        store._table = mock_table
        store._db = MagicMock()
        store._embedding_function = MagicMock()
        store._embedding_function.return_value = [MagicMock()]
        store._embedding_function.return_value[0].tolist = MagicMock(return_value=[0.1])

        results = store.query("hello", "private")

        assert len(results) == 1
        # 关键: JSON 反序列化后, 含逗号的 tag 是完整的单个元素
        assert results[0]["tags"] == ["a,b", "c"], (
            f"tags 应反序列化为 list, 实际: {results[0]['tags']!r}"
        )

    def test_query_backward_compat_old_comma_format(self):
        """query 读取旧格式 (逗号分隔) tags 时, 降级到 split 不报错。"""
        pytest.importorskip("lancedb", reason="lancedb 未安装")
        pytest.importorskip("pyarrow", reason="pyarrow 未安装")

        from pathlib import Path
        import tempfile
        from server.kb.retrieval.lance_store import LanceVectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))

        mock_table = MagicMock()
        mock_search_chain = MagicMock()
        mock_search_chain.where.return_value.limit.return_value.to_list.return_value = [
            {"id": "1", "doc_id": "d1", "text": "t1", "scope": "private",
             "tags": "work,note,important", "_distance": 0.5},  # 旧格式
        ]
        mock_table.search = MagicMock(return_value=mock_search_chain)
        store._table = mock_table
        store._db = MagicMock()
        store._embedding_function = MagicMock()
        store._embedding_function.return_value = [MagicMock()]
        store._embedding_function.return_value[0].tolist = MagicMock(return_value=[0.1])

        results = store.query("hello", "private")

        assert results[0]["tags"] == ["work", "note", "important"]
