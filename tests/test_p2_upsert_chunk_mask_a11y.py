# tests/test_p2_upsert_chunk_mask_a11y.py
"""P2 修复测试 — v2.2.1

测试目标:
1. P2-7: LanceVectorStore.upsert 失败重试 + 日志 (lance_store.py)
2. P2-8: _chunk_text 近似 token 计数切片 (knowledge_service.py)
3. P2-9: browser_type _mask_sensitive 日志脱敏 (browser_tools.py)
4. P2-10: _walk_a11y 迭代式遍历,防深层 UI 树栈溢出 (computer_tools.py)
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# P2-8: _chunk_text (已存在, 测试新 token 计数行为)
from server.services.knowledge_service import _chunk_text

# P2-9: _mask_sensitive (v2.2.1 P2 新增)
from server.tools.browser_tools import _mask_sensitive

# P2-10: _walk_a11y (已存在, 测试新迭代行为)
from server.tools.computer_tools import ComputerGetA11yTreeTool


# ============ P2-7: upsert 失败重试 ============
# LanceVectorStore 的 lancedb/pyarrow 为运行时惰性 import,
# 通过 sys.modules 注入 mock, 使测试无需安装 lancedb 即可运行

@pytest.fixture(scope="module")
def mock_lance_env():
    """注入 mock lancedb + pyarrow 到 sys.modules, 使 LanceVectorStore 可实例化

    LanceVectorStore.__init__ 不 import lancedb; _ensure_db/upsert 运行时才 import。
    测试中 _table/_db 已设为 mock, _ensure_db 提前返回, 不会触发真实 lancedb 调用。
    """
    import sys

    mock_pa = MagicMock()
    mock_ldb = MagicMock()
    saved = {k: sys.modules.get(k) for k in ("pyarrow", "lancedb")}
    sys.modules["pyarrow"] = mock_pa
    sys.modules["lancedb"] = mock_ldb
    try:
        yield mock_pa
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _make_store_with_mock_table():
    """构造 LanceVectorStore 实例, _table/_db 用 mock, 跳过真实 lancedb 连接"""
    import tempfile

    from server.kb.retrieval.lance_store import LanceVectorStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = LanceVectorStore(Path(tmpdir))
    mock_table = MagicMock()
    mock_table.delete = MagicMock()
    mock_table.add = MagicMock()
    store._table = mock_table
    store._db = MagicMock()  # _ensure_db 检查 _db is not None 即提前返回
    # mock embedding: 返回带 to_list() 的 fake vector
    fake_vec = MagicMock()
    fake_vec.tolist.return_value = [0.1, 0.2]
    store._embedding_function = MagicMock(return_value=[fake_vec])
    return store, mock_table


class TestUpsertRetry:
    """P2-7: upsert add 失败时记录日志 + 重试 1 次"""

    def test_upsert_failure_logged(self, mock_lance_env, caplog):
        """upsert add 失败时 logger.warning 被调用 (重试也失败, 异常抛出)"""
        store, mock_table = _make_store_with_mock_table()
        # add 每次都失败
        mock_table.add.side_effect = RuntimeError("db locked")
        chunks = [{
            "id": "c1", "text": "hello", "doc_id": "doc-001", "scope": "private",
        }]
        with pytest.raises(RuntimeError):
            store.upsert(chunks)
        # 关键断言: warning 日志被记录
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1, "upsert add 失败应记录 warning"
        assert "upsert" in warnings[0].message.lower()

    def test_upsert_retry_success(self, mock_lance_env):
        """第一次 add 失败, 重试成功, 无异常抛出"""
        store, mock_table = _make_store_with_mock_table()
        # 第一次失败, 第二次成功
        mock_table.add.side_effect = [RuntimeError("transient"), None]
        chunks = [{
            "id": "c1", "text": "hello", "doc_id": "doc-001", "scope": "private",
        }]
        store.upsert(chunks)  # 不应抛异常
        # 关键断言: add 被调用 2 次 (1 次失败 + 1 次重试成功)
        assert mock_table.add.call_count == 2


# ============ P2-8: _chunk_text 近似 token 计数 ============

class TestChunkText:
    """P2-8: 近似 token 计数切片 (CJK 字符=1 token, 英文单词=1 token)"""

    def test_chunk_text_cjk(self):
        """CJK 文本按 token (字符) 切片, 600 字 / 512 = 2 chunks"""
        text = "字" * 600  # 600 CJK 字符 = 600 tokens
        chunks = _chunk_text(text, chunk_size=512, overlap=50)
        assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
        # 所有 chunk 非空
        assert all(c for c in chunks)
        # 验证切片内容来自原文
        assert chunks[0].startswith("字")
        assert chunks[-1].endswith("字")

    def test_chunk_text_english(self):
        """英文文本按 token (单词) 切片, 而非字符

        600 个 'hello' 单词 ≈ 3600 字符:
        - token 计数: 600 tokens / 512 = 2 chunks
        - 字符计数(旧行为): 3600 / 512 ≈ 7 chunks
        """
        text = " ".join(["hello"] * 600)
        chunks = _chunk_text(text, chunk_size=512, overlap=50)
        # 关键断言: token 计数应得 2 chunks, 字符计数会得 ~7
        assert len(chunks) == 2, (
            f"expected 2 chunks (token-based), got {len(chunks)} "
            f"(char-based would give ~7)"
        )
        assert all(c for c in chunks)

    def test_chunk_text_empty(self):
        """空文本返回空列表"""
        assert _chunk_text("") == []
        assert _chunk_text(None) == []  # type: ignore[arg-type]


# ============ P2-9: _mask_sensitive 脱敏 ============

class TestMaskSensitive:
    """P2-9: browser_type 日志脱敏, 防止密码/token 泄漏"""

    def test_mask_sensitive_short(self):
        """短文本 (<=visible) 全脱敏为星号"""
        # visible 默认 4, 文本 <= 4 字符全脱敏
        assert _mask_sensitive("abc") == "***"
        assert _mask_sensitive("abcd") == "****"
        assert _mask_sensitive("a") == "*"

    def test_mask_sensitive_long(self):
        """长文本保留前 4 字符 + 星号 (最多 20 个星号)"""
        result = _mask_sensitive("password123456")
        # 保留前 4 字符
        assert result.startswith("pass")
        # 包含星号
        assert "*" in result
        # 脱敏后比原文短 (前 4 + 最多 20 星号 = 24 < 14? 不一定)
        # 关键: 不暴露完整原文
        assert "123456" not in result

    def test_mask_sensitive_empty(self):
        """空字符串/None 返回空字符串"""
        assert _mask_sensitive("") == ""
        assert _mask_sensitive(None) == ""  # type: ignore[arg-type]


# ============ P2-10: _walk_a11y 迭代式遍历 ============

class _MockControl:
    """模拟 uiautomation.Control, 用于测试 _walk_a11y

    提供与真实 uiautomation.Control 相同的接口:
    Name / ControlTypeName / ClassName / GetChildren()
    """

    def __init__(self, name: str, children: list | None = None):
        self.Name = name
        self.ControlTypeName = "Button"
        self.ClassName = "TestClass"
        self._children = children or []

    def GetChildren(self):
        return self._children


def _make_deep_chain(depth: int) -> _MockControl:
    """构造深度为 depth 的链状 UI 树 (每节点 1 个子节点)

    迭代构造, 避免构造过程本身栈溢出。
    """
    node = _MockControl("leaf")
    for i in range(depth):
        node = _MockControl(f"node-{i}", [node])
    return node


class TestWalkA11yIterative:
    """P2-10: _walk_a11y 改迭代, 防止深层 UI 树栈溢出"""

    def test_walk_a11y_iterative_deep_tree(self):
        """深层 UI 树 (depth=1500) 不栈溢出

        递归实现会触发 RecursionError (默认限制 1000),
        迭代实现用栈 (list) 不会。
        """
        root = _make_deep_chain(1500)
        # 应正常返回, 不抛 RecursionError
        tree = ComputerGetA11yTreeTool._walk_a11y(root, depth=0, max_depth=2000)
        assert tree is not None
        assert tree["depth"] == 0
        # 根节点应有 children (depth 0 < max_depth 2000)
        assert "children" in tree

    def test_walk_a11y_iterative_max_depth(self):
        """max_depth 限制遍历深度

        树深度 5, max_depth=2: 只遍历到 depth 2 (0, 1, 2 三层)
        """
        root = _make_deep_chain(5)
        tree = ComputerGetA11yTreeTool._walk_a11y(root, depth=0, max_depth=2)
        # 沿着唯一子链遍历, 记录所有 depth
        node = tree
        depths_seen = [node["depth"]]
        while "children" in node:
            node = node["children"][0]
            depths_seen.append(node["depth"])
        # 应只到 depth=2 (depth < max_depth 才有 children)
        assert max(depths_seen) == 2, (
            f"expected max depth 2, got {max(depths_seen)}"
        )
