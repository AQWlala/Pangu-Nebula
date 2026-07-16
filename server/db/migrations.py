"""轻量运行时 schema 迁移助手

本项目使用 Base.metadata.create_all 建表,但 create_all 不会给已存在的表追加新列。
v2.2.0 给 personas/conversations/messages 三张表新增了列,这里在启动时检测并补齐,
保证旧库无需 Alembic 即可平滑升级。

仅依赖 SQLAlchemy inspector + ALTER TABLE ADD COLUMN,兼容 SQLite/PostgreSQL。
幂等:已存在的列会被跳过。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# (表名, 列名, ADD COLUMN 用的列定义 SQL)
# 列定义须与 orm.py 中的类型/默认值保持一致
_MIGRATIONS: list[tuple[str, str, str]] = [
    # v2.2.0 Persona 能力开关
    ("personas", "tools_enabled", "BOOLEAN DEFAULT 1"),
    ("personas", "rag_enabled", "BOOLEAN DEFAULT 1"),
    ("personas", "sandbox_allow_network", "BOOLEAN DEFAULT 0"),
    ("personas", "terminal_allowed", "BOOLEAN DEFAULT 0"),
    ("personas", "browser_use_enabled", "BOOLEAN DEFAULT 0"),
    # v2.2.1 F7: computer_* 工具独立权限字段 (默认关闭,安全优先)
    ("personas", "computer_use_enabled", "BOOLEAN DEFAULT 0"),
    # v2.2.0 Conversation 状态
    ("conversations", "status", "VARCHAR(20) DEFAULT 'idle'"),
    # v2.2.0 Message 工具调用持久化
    ("messages", "tool_calls", "TEXT"),
    ("messages", "tool_call_id", "VARCHAR(64)"),
    ("messages", "tool_name", "VARCHAR(64)"),
    ("messages", "tool_result", "TEXT"),
]


def run_lightweight_migrations(conn) -> None:
    """在 create_all 之后补齐缺失列。幂等:已存在的列会被跳过。"""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    # 本地缓存已存在列,避免 ALTER 后 inspector 反射缓存过期
    cols_cache: dict[str, set[str]] = {}

    def cols_of(table: str) -> set[str]:
        if table not in cols_cache:
            cols_cache[table] = {c["name"] for c in inspector.get_columns(table)}
        return cols_cache[table]

    for table_name, column_name, column_def in _MIGRATIONS:
        if table_name not in existing_tables:
            # 表尚不存在(全新库由 create_all 建表,无需迁移)
            continue
        if column_name in cols_of(table_name):
            continue
        stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}'
        logger.info("schema 迁移: %s", stmt)
        conn.execute(text(stmt))
        cols_of(table_name).add(column_name)
