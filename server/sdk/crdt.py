"""Pangu Memory SDK — CRDT 同步管理器

实现两种 CRDT 用于跨设备冲突无关同步:
- LWWRegister: Last-Writer-Wins Register, 用于单值字段
- ORSet: Observed-Remove Set, 用于集合数据 (标签等)

CRDTSyncManager 统一管理多个 Register 和 Set,支持状态导出/导入。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4


class LWWRegister:
    """Last-Writer-Wins Register — 用于单值的冲突无关同步"""

    def __init__(
        self,
        value: Any = None,
        timestamp: Optional[datetime] = None,
        node_id: str = "default",
    ):
        self.value = value
        self.timestamp: datetime = timestamp or datetime.utcnow()
        self.node_id = node_id

    def set(
        self,
        value: Any,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """设置新值,仅当 timestamp 更新时才写入

        返回是否成功更新。
        同节点写入 (timestamp=None) 时保证单调递增,避免时钟精度导致的同时间戳问题。
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
            # 同节点写入: 保证严格递增 (Windows 时钟精度较低)
            if timestamp <= self.timestamp:
                timestamp = self.timestamp + timedelta(microseconds=1)
        if timestamp > self.timestamp:
            self.value = value
            self.timestamp = timestamp
            return True
        return False

    def merge(self, other: LWWRegister) -> bool:
        """合并另一个副本,取 timestamp 更大的值

        timestamp 相同时按 node_id 字典序打破平局 (确定性)
        返回是否发生了变更
        """
        if other.timestamp > self.timestamp:
            self.value = other.value
            self.timestamp = other.timestamp
            self.node_id = other.node_id
            return True
        if other.timestamp == self.timestamp and other.node_id > self.node_id:
            self.value = other.value
            self.node_id = other.node_id
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "node_id": self.node_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LWWRegister:
        ts = data.get("timestamp")
        timestamp = None
        if ts:
            try:
                timestamp = datetime.fromisoformat(ts)
            except ValueError:
                timestamp = None
        return cls(
            value=data.get("value"),
            timestamp=timestamp,
            node_id=data.get("node_id", "default"),
        )


class ORSet:
    """Observed-Remove Set — 用于集合的冲突无关同步

    每个元素关联一组 tag:
    - add: 生成唯一 tag 加入
    - remove: 移除该元素所有已观察到的 tag
    - merge: 对每个元素取 tag 并集

    并发 add/remove 不会丢失: add 后于 remove 的 tag 会在 merge 后保留。
    """

    def __init__(self) -> None:
        self._elements: dict[str, set[str]] = {}  # element -> set of tags

    def add(self, element: str, tag: Optional[str] = None) -> str:
        """添加元素,生成唯一 tag,返回该 tag"""
        if tag is None:
            tag = str(uuid4())
        if element not in self._elements:
            self._elements[element] = set()
        self._elements[element].add(tag)
        return tag

    def remove(self, element: str) -> bool:
        """删除元素 (移除所有已观察到的 tag)

        返回是否确实删除了某些 tag
        """
        if element in self._elements and self._elements[element]:
            self._elements[element].clear()
            return True
        return False

    def contains(self, element: str) -> bool:
        return element in self._elements and len(self._elements[element]) > 0

    def get_all(self) -> set[str]:
        """返回所有元素 (有 tag 的)"""
        return {e for e, tags in self._elements.items() if tags}

    def merge(self, other: ORSet) -> bool:
        """合并:每个元素的 tags 取并集

        返回是否发生了变更
        """
        changed = False
        for elem, tags in other._elements.items():
            if elem not in self._elements:
                self._elements[elem] = set()
            if not tags.issubset(self._elements[elem]):
                self._elements[elem] |= tags
                changed = True
        return changed

    def to_dict(self) -> dict:
        return {e: list(tags) for e, tags in self._elements.items()}

    @classmethod
    def from_dict(cls, data: dict) -> ORSet:
        obj = cls()
        for elem, tags in (data or {}).items():
            obj._elements[elem] = set(tags)
        return obj


class CRDTSyncManager:
    """CRDT 同步管理器 — 管理多个 LWW Register 和 OR-Set"""

    def __init__(self, node_id: str = "default"):
        self.node_id = node_id
        self._registers: dict[str, LWWRegister] = {}
        self._sets: dict[str, ORSet] = {}

    def get_register(self, key: str) -> LWWRegister:
        if key not in self._registers:
            self._registers[key] = LWWRegister(node_id=self.node_id)
        return self._registers[key]

    def get_set(self, key: str) -> ORSet:
        if key not in self._sets:
            self._sets[key] = ORSet()
        return self._sets[key]

    def set_register(self, key: str, value: Any) -> bool:
        """便捷方法: 设置 register 的值"""
        return self.get_register(key).set(value)

    def add_to_set(self, key: str, element: str) -> str:
        """便捷方法: 向 set 添加元素"""
        return self.get_set(key).add(element)

    def remove_from_set(self, key: str, element: str) -> bool:
        """便捷方法: 从 set 删除元素"""
        return self.get_set(key).remove(element)

    def export_state(self) -> dict:
        """导出同步状态 (可序列化为 JSON)"""
        return {
            "node_id": self.node_id,
            "registers": {
                k: r.to_dict() for k, r in self._registers.items()
            },
            "sets": {
                k: s.to_dict() for k, s in self._sets.items()
            },
        }

    def import_state(self, state: dict) -> bool:
        """导入同步状态并 merge

        返回是否发生了任何变更
        """
        changed = False
        # 合并 registers
        for key, reg_data in (state.get("registers") or {}).items():
            other = LWWRegister.from_dict(reg_data)
            local = self.get_register(key)
            if local.merge(other):
                changed = True
        # 合并 sets
        for key, set_data in (state.get("sets") or {}).items():
            other = ORSet.from_dict(set_data)
            local = self.get_set(key)
            if local.merge(other):
                changed = True
        return changed
