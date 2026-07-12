"""Pangu Memory SDK — 记忆存储

抽象基类 BaseMemoryStore + 默认 SQLite 实现 MemoryStore
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from .types import Memory, MemoryLayer, MemoryMetadata


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    layer TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT,
    updated_at TEXT,
    source TEXT NOT NULL DEFAULT '',
    backlinks TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
"""


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _row_to_memory(row: sqlite3.Row | tuple) -> Memory:
    if isinstance(row, sqlite3.Row):
        row = tuple(row)
    (
        mid,
        content,
        layer,
        tags_json,
        importance,
        created_at,
        updated_at,
        source,
        backlinks_json,
        metadata_json,
    ) = row
    created = None
    if created_at:
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            created = None
    updated = None
    if updated_at:
        try:
            updated = datetime.fromisoformat(updated_at)
        except ValueError:
            updated = None
    return Memory(
        id=mid,
        content=content,
        metadata=MemoryMetadata(
            layer=MemoryLayer(layer),
            tags=json.loads(tags_json) if tags_json else [],
            importance=importance,
            created_at=created,
            updated_at=updated,
            source=source or "",
            backlinks=json.loads(backlinks_json) if backlinks_json else [],
            metadata=json.loads(metadata_json) if metadata_json else {},
        ),
    )


class BaseMemoryStore(ABC):
    """记忆存储抽象基类 — 可插入不同后端 (SQLite/PostgreSQL/Redis)"""

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def add(
        self,
        content: str,
        layer: MemoryLayer = MemoryLayer.L1_EPISODIC,
        **kwargs: Any,
    ) -> Memory: ...

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Memory]: ...

    @abstractmethod
    async def list(
        self,
        layer: Optional[MemoryLayer] = None,
        limit: int = 100,
    ) -> list[Memory]: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[Memory]: ...

    @abstractmethod
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        **kwargs: Any,
    ) -> Memory: ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool: ...

    @abstractmethod
    async def link(self, source_id: str, target_id: str) -> bool: ...

    @abstractmethod
    async def get_backlinks(self, memory_id: str) -> list[Memory]: ...


class MemoryStore(BaseMemoryStore):
    """默认实现: SQLite 后端 (与 Pangu Nebula 主项目兼容)"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("MemoryStore 未初始化，请先调用 init()")
        return self._db

    async def add(
        self,
        content: str,
        layer: MemoryLayer = MemoryLayer.L1_EPISODIC,
        **kwargs: Any,
    ) -> Memory:
        memory_id = kwargs.pop("id", None) or str(uuid.uuid4())
        tags = kwargs.pop("tags", []) or []
        importance = float(kwargs.pop("importance", 0.5))
        source = kwargs.pop("source", "")
        backlinks = kwargs.pop("backlinks", []) or []
        now = datetime.utcnow()
        created_at = kwargs.pop("created_at", now)
        updated_at = kwargs.pop("updated_at", now)
        metadata_extra = kwargs.pop("metadata", {}) or {}

        if isinstance(layer, str):
            layer = MemoryLayer(layer)

        mem = Memory(
            id=memory_id,
            content=content,
            metadata=MemoryMetadata(
                layer=layer,
                tags=list(tags),
                importance=importance,
                created_at=created_at,
                updated_at=updated_at,
                source=source,
                backlinks=list(backlinks),
                metadata=dict(metadata_extra),
            ),
        )
        await self.db.execute(
            """
            INSERT INTO memories
                (id, content, layer, tags, importance, created_at, updated_at,
                 source, backlinks, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mem.id,
                mem.content,
                mem.metadata.layer.value,
                json.dumps(mem.metadata.tags),
                mem.metadata.importance,
                mem.metadata.created_at.isoformat() if mem.metadata.created_at else None,
                mem.metadata.updated_at.isoformat() if mem.metadata.updated_at else None,
                mem.metadata.source,
                json.dumps(mem.metadata.backlinks),
                json.dumps(mem.metadata.metadata),
            ),
        )
        await self.db.commit()
        return mem

    async def get(self, memory_id: str) -> Optional[Memory]:
        cursor = await self.db.execute(
            "SELECT id, content, layer, tags, importance, created_at, updated_at, "
            "source, backlinks, metadata FROM memories WHERE id = ?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return _row_to_memory(row)

    async def list(
        self,
        layer: Optional[MemoryLayer] = None,
        limit: int = 100,
    ) -> list[Memory]:
        if layer is not None:
            layer_val = layer.value if isinstance(layer, MemoryLayer) else str(layer)
            cursor = await self.db.execute(
                "SELECT id, content, layer, tags, importance, created_at, updated_at, "
                "source, backlinks, metadata FROM memories WHERE layer = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (layer_val, limit),
            )
        else:
            cursor = await self.db.execute(
                "SELECT id, content, layer, tags, importance, created_at, updated_at, "
                "source, backlinks, metadata FROM memories "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_memory(r) for r in rows]

    async def search(self, query: str, limit: int = 10) -> list[Memory]:
        pattern = f"%{query}%"
        cursor = await self.db.execute(
            "SELECT id, content, layer, tags, importance, created_at, updated_at, "
            "source, backlinks, metadata FROM memories WHERE content LIKE ? "
            "ORDER BY importance DESC LIMIT ?",
            (pattern, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_memory(r) for r in rows]

    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        **kwargs: Any,
    ) -> Memory:
        existing = await self.get(memory_id)
        if existing is None:
            raise KeyError(f"Memory {memory_id} not found")

        sets: list[str] = []
        params: list[Any] = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if "layer" in kwargs and kwargs["layer"] is not None:
            layer = kwargs["layer"]
            layer_val = layer.value if isinstance(layer, MemoryLayer) else str(layer)
            sets.append("layer = ?")
            params.append(layer_val)
        if "tags" in kwargs and kwargs["tags"] is not None:
            sets.append("tags = ?")
            params.append(json.dumps(list(kwargs["tags"])))
        if "importance" in kwargs and kwargs["importance"] is not None:
            sets.append("importance = ?")
            params.append(float(kwargs["importance"]))
        if "source" in kwargs and kwargs["source"] is not None:
            sets.append("source = ?")
            params.append(kwargs["source"])
        if "backlinks" in kwargs and kwargs["backlinks"] is not None:
            sets.append("backlinks = ?")
            params.append(json.dumps(list(kwargs["backlinks"])))
        if "metadata" in kwargs and kwargs["metadata"] is not None:
            merged = {**existing.metadata.metadata, **kwargs["metadata"]}
            sets.append("metadata = ?")
            params.append(json.dumps(merged))

        sets.append("updated_at = ?")
        params.append(_now_iso())

        if sets:
            params.append(memory_id)
            await self.db.execute(
                f"UPDATE memories SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            await self.db.commit()
        return await self.get(memory_id)  # type: ignore[return-value]

    async def delete(self, memory_id: str) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        await self.db.commit()
        deleted = cursor.rowcount > 0
        await cursor.close()
        return deleted

    async def link(self, source_id: str, target_id: str) -> bool:
        source = await self.get(source_id)
        if source is None:
            return False
        target = await self.get(target_id)
        if target is None:
            return False

        source_backlinks = list(source.metadata.backlinks)
        if target_id not in source_backlinks:
            source_backlinks.append(target_id)
        await self.update(source_id, backlinks=source_backlinks)

        target_backlinks = list(target.metadata.backlinks)
        if source_id not in target_backlinks:
            target_backlinks.append(source_id)
        await self.update(target_id, backlinks=target_backlinks)
        return True

    async def get_backlinks(self, memory_id: str) -> list[Memory]:
        mem = await self.get(memory_id)
        if mem is None:
            return []
        ids = mem.metadata.backlinks
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        cursor = await self.db.execute(
            "SELECT id, content, layer, tags, importance, created_at, updated_at, "
            f"source, backlinks, metadata FROM memories WHERE id IN ({placeholders})",
            ids,
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_memory(r) for r in rows]
