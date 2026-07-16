"""F4 安全修复测试 — LanceDB SQL 注入防护

测试目标:
1. _validate_doc_id / _validate_scope / _escape_sql_literal 单元测试
2. LanceVectorStore.delete_by_doc_id 拒绝注入字符串(集成测试, mock table)
3. LanceVectorStore.query 拒绝恶意 scope
4. LanceVectorStore.upsert 跳过恶意 doc_id

依赖说明:
- 测试不依赖真实 lancedb,通过 mock 表对象验证 SQL 过滤字符串构造正确
- LanceDB 未安装时,纯辅助函数测试仍可执行(无需 importorskip)
- 仅当涉及真实 LanceVectorStore 实例化时,若 lancedb 缺失则跳过
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

# 直接导入辅助函数,不需要 lancedb
from server.kb.retrieval.lance_store import (
    _escape_sql_literal,
    _validate_doc_id,
    _validate_scope,
    _build_doc_id_filter,
    _build_scope_filter,
)


# ============ _validate_doc_id 测试 ============

class TestValidateDocId:
    def test_allows_safe_simple(self):
        """正常 doc_id 通过"""
        assert _validate_doc_id("abc123") == "abc123"

    def test_allows_safe_with_underscore(self):
        assert _validate_doc_id("doc_001") == "doc_001"

    def test_allows_safe_with_hyphen(self):
        assert _validate_doc_id("doc-001-xyz") == "doc-001-xyz"

    def test_allows_safe_uuid_like(self):
        """UUID 风格 doc_id 通过"""
        assert _validate_doc_id("550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"

    def test_rejects_injection_or_1_1(self):
        """经典注入 ' OR 1=1 -- 必须拒绝"""
        with pytest.raises(ValueError):
            _validate_doc_id("' OR 1=1 --")

    def test_rejects_injection_drop_table(self):
        with pytest.raises(ValueError):
            _validate_doc_id("abc'; DROP TABLE kb_chunks; --")

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError):
            _validate_doc_id("abc;")

    def test_rejects_quote(self):
        with pytest.raises(ValueError):
            _validate_doc_id("abc'")

    def test_rejects_space(self):
        """空格不允许(doc_id 不应包含空白)"""
        with pytest.raises(ValueError):
            _validate_doc_id("abc def")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            _validate_doc_id("")

    def test_rejects_non_string(self):
        with pytest.raises(TypeError):
            _validate_doc_id(123)  # type: ignore[arg-type]

    def test_rejects_none(self):
        with pytest.raises(TypeError):
            _validate_doc_id(None)  # type: ignore[arg-type]


# ============ _validate_scope 测试 ============

class TestValidateScope:
    def test_allows_private(self):
        assert _validate_scope("private") == "private"

    def test_allows_shared(self):
        assert _validate_scope("shared") == "shared"

    def test_allows_public(self):
        assert _validate_scope("public") == "public"

    def test_rejects_evil_or_1_1(self):
        """注入 scope 必须拒绝"""
        with pytest.raises(ValueError):
            _validate_scope("evil' OR '1'='1")

    def test_rejects_unknown_scope(self):
        with pytest.raises(ValueError):
            _validate_scope("admin")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            _validate_scope("")

    def test_rejects_non_string(self):
        with pytest.raises(TypeError):
            _validate_scope(123)  # type: ignore[arg-type]


# ============ _escape_sql_literal 测试 ============

class TestEscapeSqlLiteral:
    def test_no_quote_unchanged(self):
        assert _escape_sql_literal("abc123") == "abc123"

    def test_single_quote_doubled(self):
        """单引号被转义为两个单引号(SQL 标准)"""
        assert _escape_sql_literal("abc'def") == "abc''def"

    def test_multiple_quotes_all_doubled(self):
        assert _escape_sql_literal("a'b'c") == "a''b''c"

    def test_only_quote(self):
        assert _escape_sql_literal("'") == "''"

    def test_injection_payload_neutralized(self):
        """注入 payload 经转义后无法逃逸字面量"""
        # 原始: '; DROP TABLE x; --
        # 转义: ''; DROP TABLE x; --
        # 这在 SQL 中变成单个字符串字面量的一部分,无法执行 DROP
        payload = "'; DROP TABLE kb_chunks; --"
        escaped = _escape_sql_literal(payload)
        assert "''" in escaped
        # 关键: 转义后没有未配对的单引号能逃逸
        # 用 '...' 包裹模拟 SQL 字面量上下文
        sql_literal = f"'{escaped}'"
        # 验证: 引号数量应为偶数(SQL 字面量中引号成对出现)
        assert sql_literal.count("'") % 2 == 0

    def test_non_string_raises(self):
        with pytest.raises(TypeError):
            _escape_sql_literal(123)  # type: ignore[arg-type]


# ============ _build_doc_id_filter / _build_scope_filter 测试 ============

class TestBuildFilters:
    def test_build_doc_id_filter_safe(self):
        f = _build_doc_id_filter("doc-001")
        assert f == "doc_id = 'doc-001'"

    def test_build_doc_id_filter_rejects_injection(self):
        with pytest.raises(ValueError):
            _build_doc_id_filter("' OR 1=1 --")

    def test_build_scope_filter_safe(self):
        f = _build_scope_filter("private")
        assert f == "scope = 'private'"

    def test_build_scope_filter_rejects_injection(self):
        with pytest.raises(ValueError):
            _build_scope_filter("evil' OR '1'='1")


# ============ 集成测试: LanceVectorStore (mock table, 不依赖真实 lancedb) ============
#
# 集成测试通过 mock 表对象验证 SQL 过滤字符串构造正确,
# 但仍需 lancedb 可 import (因为 LanceVectorStore.__init__ 不 import, 但 _ensure_db 会 import)。
# 为避免 lancedb 缺失时跳过整个文件,我们用 pytest.importorskip 的「方法级」跳过:
# 把 importorskip 放在 fixture 里,缺失时只跳过需要它的集成测试类。


@pytest.fixture(scope="module")
def lancedb_available():
    """检查 lancedb 是否可 import。
    返回 True 或 None(并跳过使用此 fixture 的测试)。
    不在模块顶部 importorskip,以避免整个文件被跳过。
    """
    pytest.importorskip("lancedb", reason="lancedb 未安装, 跳过 LanceVectorStore 集成测试")
    pytest.importorskip("pyarrow", reason="pyarrow 未安装")
    return True


# 延迟 import LanceVectorStore,避免 lancedb 缺失时收集失败
def _get_lance_vector_store_class():
    from server.kb.retrieval.lance_store import LanceVectorStore
    return LanceVectorStore


class TestDeleteByDocIdInjection:
    """集成测试: 验证 delete_by_doc_id 在恶意 doc_id 时不调用 table.delete"""

    def _make_store(self, lancedb_available):
        """构造 LanceVectorStore 实例,_table 用 mock"""
        from pathlib import Path
        import tempfile
        LanceVectorStore = _get_lance_vector_store_class()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))
        # 注入 mock table, 跳过 _ensure_db 真实初始化
        mock_table = MagicMock()
        mock_table.delete = MagicMock()
        store._table = mock_table
        store._db = MagicMock()  # 防止后续 _ensure_db 触发真实连接
        return store, mock_table

    def test_safe_doc_id_calls_delete(self, lancedb_available):
        """正常 doc_id 应调用 table.delete 一次,过滤字符串中无注入"""
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id("doc-001")
        assert mock_table.delete.call_count == 1
        # 验证传入的过滤字符串是安全的
        passed_filter = mock_table.delete.call_args[0][0]
        assert passed_filter == "doc_id = 'doc-001'"

    def test_injection_doc_id_rejected_no_delete(self, lancedb_available):
        """注入 doc_id 必须被拒绝,且绝不调用 table.delete"""
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id("' OR 1=1 --")
        # 关键断言: 没有调用 delete, 防止恶意 SQL 进入 LanceDB
        assert mock_table.delete.call_count == 0

    def test_drop_table_injection_rejected(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id("abc'; DROP TABLE kb_chunks; --")
        assert mock_table.delete.call_count == 0

    def test_semicolon_rejected(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id("abc;")
        assert mock_table.delete.call_count == 0

    def test_empty_doc_id_rejected(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id("")
        assert mock_table.delete.call_count == 0

    def test_non_string_doc_id_rejected(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        store.delete_by_doc_id(123)  # type: ignore[arg-type]
        assert mock_table.delete.call_count == 0


class TestQueryScopeInjection:
    """集成测试: 验证 query 在恶意 scope 时不调用 table.search"""

    def _make_store(self, lancedb_available):
        from pathlib import Path
        import tempfile
        LanceVectorStore = _get_lance_vector_store_class()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))
        mock_table = MagicMock()
        mock_search_chain = MagicMock()
        mock_search_chain.where.return_value.limit.return_value.to_list.return_value = []
        mock_table.search = MagicMock(return_value=mock_search_chain)
        store._table = mock_table
        store._db = MagicMock()
        store._embedding_function = MagicMock()
        store._embedding_function.return_value = [MagicMock()]
        store._embedding_function.return_value[0].tolist = MagicMock(return_value=[0.1])
        return store, mock_table

    def test_safe_scope_calls_search(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        store.query("hello", "private")
        assert mock_table.search.call_count == 1

    def test_injection_scope_rejected_no_search(self, lancedb_available):
        """恶意 scope 必须拒绝,绝不调用 search"""
        store, mock_table = self._make_store(lancedb_available)
        results = store.query("hello", "evil' OR '1'='1")
        # 关键断言: 没有调用 search
        assert mock_table.search.call_count == 0
        # 返回空列表
        assert results == []

    def test_unknown_scope_rejected(self, lancedb_available):
        store, mock_table = self._make_store(lancedb_available)
        results = store.query("hello", "admin")
        assert mock_table.search.call_count == 0
        assert results == []


class TestUpsertInjection:
    """集成测试: 验证 upsert 在恶意 doc_id 时跳过 delete 但不抛异常"""

    def _make_store_with_mock_table(self, lancedb_available):
        from pathlib import Path
        import tempfile
        LanceVectorStore = _get_lance_vector_store_class()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceVectorStore(Path(tmpdir))
        mock_table = MagicMock()
        mock_table.delete = MagicMock()
        # add 调用需要 pyarrow Table,这里 mock 掉
        mock_table.add = MagicMock()
        store._table = mock_table
        store._db = MagicMock()
        # mock embedding
        import numpy as np
        store._embedding_function = MagicMock(return_value=np.array([[0.1, 0.2]]))
        return store, mock_table

    def test_safe_upsert_calls_delete_then_add(self, lancedb_available):
        store, mock_table = self._make_store_with_mock_table(lancedb_available)
        chunks = [{
            "id": "chunk-1",
            "text": "hello",
            "doc_id": "doc-001",
            "scope": "private",
        }]
        # 需要 mock pyarrow.Table.from_pylist
        with patch("pyarrow.Table.from_pylist"):
            store.upsert(chunks)
        # 正常 doc_id 触发 delete
        assert mock_table.delete.call_count == 1
        assert mock_table.add.call_count == 1

    def test_injection_doc_id_in_upsert_skips_delete(self, lancedb_available):
        """upsert 中遇到恶意 doc_id 时跳过 delete,但不抛异常"""
        store, mock_table = self._make_store_with_mock_table(lancedb_available)
        chunks = [{
            "id": "chunk-1",
            "text": "hello",
            "doc_id": "' OR 1=1 --",
            "scope": "private",
        }]
        with patch("pyarrow.Table.from_pylist"):
            # 不应抛异常
            store.upsert(chunks)
        # 关键: 恶意 doc_id 不会触发 delete
        assert mock_table.delete.call_count == 0
