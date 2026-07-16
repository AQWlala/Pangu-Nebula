# tests/test_p2_audit_migration_close.py
"""v2.2.1 P2 修复测试 — 审计日志流式读取 / migrations 标识符校验 / lance_store close 资源释放

覆盖三个 P2 一般问题:
- P2-11: AuditLogger.iter_audit_entries 流式倒序迭代、limit 限制、跳过无效 JSON、空文件
- P2-12: migrations._validate_identifier 标识符校验(防 SQL 注入)
- P2-13: LanceVectorStore.close 释放 _table/_db 且幂等

依赖说明:
- audit_log / migrations 测试无外部依赖
- lance_store.close 测试用 MagicMock 注入 _table/_db,不依赖真实 lancedb
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server.cu.safety.audit_log import AuditLogger
from server.db.migrations import _validate_identifier
from server.kb.retrieval.lance_store import LanceVectorStore


# ============ P2-11: AuditLogger.iter_audit_entries ============

def _write_audit_lines(log_file: Path, entries: list[dict]) -> None:
    """直接写入若干 JSONL 行(每行一个 dict)。"""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_iter_audit_entries_empty(tmp_path):
    """空文件(不存在)返回空迭代器。"""
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    result = list(logger.iter_audit_entries("cutask-empty"))
    assert result == []


def test_iter_audit_entries_limit(tmp_path):
    """limit 限制生效:写入 5 条,limit=2 只返回 2 条最新的。"""
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    log_file = tmp_path / "cu_audit" / "cutask-limit" / "audit.jsonl"
    entries = [{"step_index": i, "action_type": f"act_{i}"} for i in range(5)]
    _write_audit_lines(log_file, entries)

    result = list(logger.iter_audit_entries("cutask-limit", limit=2))

    assert len(result) == 2
    # 倒序:最新两条是 step_index 4 和 3
    assert result[0]["step_index"] == 4
    assert result[1]["step_index"] == 3


def test_iter_audit_entries_skip_invalid(tmp_path):
    """跳过无效 JSON 行,只返回可解析的条目。"""
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    log_file = tmp_path / "cu_audit" / "cutask-invalid" / "audit.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"step_index": 0}) + "\n")
        f.write("this is not valid json\n")
        f.write("{broken\n")
        f.write(json.dumps({"step_index": 1}) + "\n")

    result = list(logger.iter_audit_entries("cutask-invalid", limit=100))

    # 只剩 2 条有效条目,倒序: step 1 然后 step 0
    assert len(result) == 2
    assert result[0]["step_index"] == 1
    assert result[1]["step_index"] == 0


def test_iter_audit_entries_reversed(tmp_path):
    """从末尾开始倒序产出。"""
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    log_file = tmp_path / "cu_audit" / "cutask-rev" / "audit.jsonl"
    entries = [{"step_index": i} for i in range(4)]
    _write_audit_lines(log_file, entries)

    result = list(logger.iter_audit_entries("cutask-rev", limit=100))

    assert [r["step_index"] for r in result] == [3, 2, 1, 0]


# ============ P2-12: migrations._validate_identifier ============

def test_validate_identifier_allows_safe():
    """正常标识符通过。"""
    assert _validate_identifier("personas") == "personas"
    assert _validate_identifier("tools_enabled") == "tools_enabled"
    assert _validate_identifier("_under_score123") == "_under_score123"


def test_validate_identifier_rejects_injection():
    """经典 SQL 注入字符串必须拒绝。"""
    with pytest.raises(ValueError):
        _validate_identifier("evil; DROP TABLE--")


def test_validate_identifier_rejects_empty():
    """空字符串拒绝。"""
    with pytest.raises(ValueError):
        _validate_identifier("")


# ============ P2-13: LanceVectorStore.close ============

def test_close_releases_table(tmp_path):
    """close 后 _table 为 None,且调用了 table.close()。"""
    store = LanceVectorStore(persist_dir=tmp_path / "lance")
    mock_table = MagicMock()
    mock_table.close = MagicMock()
    store._table = mock_table

    store.close()

    assert store._table is None
    mock_table.close.assert_called_once()


def test_close_releases_db(tmp_path):
    """close 后 _db 为 None,且调用了 db.close()。"""
    store = LanceVectorStore(persist_dir=tmp_path / "lance")
    mock_db = MagicMock()
    mock_db.close = MagicMock()
    store._db = mock_db

    store.close()

    assert store._db is None
    mock_db.close.assert_called_once()


def test_close_idempotent(tmp_path):
    """多次 close 不报错。"""
    store = LanceVectorStore(persist_dir=tmp_path / "lance")
    mock_table = MagicMock()
    mock_table.close = MagicMock()
    mock_db = MagicMock()
    mock_db.close = MagicMock()
    store._table = mock_table
    store._db = mock_db

    # 多次调用不应抛异常
    store.close()
    store.close()
    store.close()

    assert store._table is None
    assert store._db is None
    # close 只在第一次被调用(之后对象已置 None)
    mock_table.close.assert_called_once()
    mock_db.close.assert_called_once()
