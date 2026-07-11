"""CRDT 数据结构 + 同步服务(Phase 9A)

实现三种 CRDT(Conflict-free Replicated Data Type)用于多设备同步冲突解决:
- LWWRegister[T]: Last-Write-Wins Register,后写覆盖,适合单值字段
- ORSet: Observed-Remove Set,观察删除集合,适合标签/集合数据
- RGA: Replicated Growable Array,有序列表,适合有序消息/列表

CRDTService 模块级单例负责:
- 将 CRDT 状态持久化到 SyncOperation 表
- 提供合并接口处理远程副本
- 追踪操作同步状态(list_pending_ops / mark_synced)

融合来源:
- Shapiro 等人的 CRDT 综述论文(A comprehensive study of CRDTs)
- Yjs / Automerge 的有序集合设计
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import uuid4

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import SyncOperation

T = TypeVar("T")


# ----------------------------------------------------------------------
# LWWRegister: Last-Write-Wins Register
# ----------------------------------------------------------------------


class LWWRegister(Generic[T]):
    """Last-Write-Wins Register(后写覆盖寄存器)

    每个副本保存 (value, timestamp, node_id):
    - merge(other): 取 timestamp 更大的值;timestamp 相同时按 node_id 字典序打破平局
    - get(): 返回当前值
    - set(value, node_id, timestamp?): 更新值与时间戳
    """

    def __init__(
        self,
        value: T | None = None,
        timestamp: str | None = None,
        node_id: str | None = None,
    ):
        self._value: T | None = value
        self._timestamp: str | None = timestamp
        self._node_id: str | None = node_id

    @staticmethod
    def _now_iso() -> str:
        """当前 UTC 时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat()

    def get(self) -> T | None:
        """获取当前值"""
        return self._value

    def set(self, value: T, node_id: str, timestamp: str | None = None) -> None:
        """设置新值

        - timestamp 为 None 时使用当前时间
        - 仅当新 timestamp >= 当前 timestamp 时才更新
        """
        ts = timestamp or self._now_iso()
        # 如果已有值,且新时间戳更旧,则忽略(保证单调)
        if self._timestamp is not None and ts < self._timestamp:
            return
        self._value = value
        self._timestamp = ts
        self._node_id = node_id

    def merge(self, other: "LWWRegister[T]") -> "LWWRegister[T]":
        """合并另一个副本

        规则:取 timestamp 更大的;timestamp 相同时按 node_id 字典序较大者(确定性)
        返回 self(便于链式调用)
        """
        if other._timestamp is None:
            return self
        if self._timestamp is None:
            self._value = other._value
            self._timestamp = other._timestamp
            self._node_id = other._node_id
            return self

        if other._timestamp > self._timestamp:
            self._value = other._value
            self._timestamp = other._timestamp
            self._node_id = other._node_id
        elif other._timestamp == self._timestamp:
            # 平局:按 node_id 字典序打破(保证两端的合并结果一致)
            if (other._node_id or "") > (self._node_id or ""):
                self._value = other._value
                self._node_id = other._node_id
        return self

    def to_dict(self) -> dict:
        """序列化为 dict(用于持久化/传输)"""
        return {
            "value": self._value,
            "timestamp": self._timestamp,
            "node_id": self._node_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LWWRegister[T]":
        """从 dict 反序列化"""
        return cls(
            value=data.get("value"),
            timestamp=data.get("timestamp"),
            node_id=data.get("node_id"),
        )


# ----------------------------------------------------------------------
# ORSet: Observed-Remove Set
# ----------------------------------------------------------------------


class ORSet:
    """Observed-Remove Set(观察删除集合)

    每个元素关联一组 tag(UUID):
    - add(value): 生成唯一 tag 加入 elements[value]
    - remove(value): 删除该 value 的所有 tag(观察到的 tag 全部移除)
    - contains(value): 是否存在
    - merge(other): 对每个 value 取 tag 并集
    - values(): 返回所有有 tag 的元素

    并发 add/remove 不会丢失:add 后于 remove 的 tag 会在 merge 后保留。
    """

    def __init__(self, elements: dict[str, set[str]] | None = None):
        # value -> set of tags
        self._elements: dict[str, set[str]] = {}
        if elements:
            for value, tags in elements.items():
                self._elements[value] = set(tags)

    def add(self, value: str) -> str:
        """添加元素,生成唯一 tag,返回该 tag"""
        tag = str(uuid4())
        self._elements.setdefault(value, set()).add(tag)
        return tag

    def remove(self, value: str) -> bool:
        """删除元素(移除所有已观察到的 tag)

        返回是否确实删除了某些 tag
        """
        if value in self._elements:
            self._elements[value].clear()
            return True
        return False

    def contains(self, value: str) -> bool:
        """是否包含某元素(有至少一个 tag)"""
        tags = self._elements.get(value)
        return bool(tags)

    def merge(self, other: "ORSet") -> "ORSet":
        """合并:每个 value 的 tags 取并集"""
        for value, tags in other._elements.items():
            self._elements.setdefault(value, set()).update(tags)
        return self

    def values(self) -> list[str]:
        """返回所有元素(有 tag 的 value)"""
        return [v for v, tags in self._elements.items() if tags]

    def to_dict(self) -> dict:
        """序列化为 dict(tags 转为 list 以便 JSON 序列化)"""
        return {v: list(tags) for v, tags in self._elements.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "ORSet":
        """从 dict 反序列化(list -> set)"""
        elements = {v: set(tags) for v, tags in data.items()} if data else {}
        return cls(elements=elements)


# ----------------------------------------------------------------------
# RGA: Replicated Growable Array
# ----------------------------------------------------------------------


@dataclass
class RGAItem:
    """RGA 单个元素

    - id: 元素唯一标识(UUID)
    - value: 元素值
    - timestamp: 创建时间(用于排序打破平局)
    - tombstone: 是否已删除(逻辑删除)
    """

    id: str
    value: str
    timestamp: str
    tombstone: bool = False


class RGA:
    """Replicated Growable Array(有序列表)

    维护一个有序的 RGAItem 列表:
    - insert_after(ref_id, value): 在 ref_id 之后插入新元素(ref_id 为 None 表示头部)
    - remove(id): 标记 tombstone(逻辑删除,保留以支持并发 merge)
    - merge(other): 按 id 去重合并,timestamp 排序
    - to_list(): 返回非 tombstone 的值列表
    """

    def __init__(self, elements: list[RGAItem] | None = None):
        self._elements: list[RGAItem] = elements or []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def insert_after(self, ref_id: str | None, value: str) -> RGAItem:
        """在 ref_id 元素之后插入新元素

        - ref_id 为 None 时插入到列表头部
        - 返回新创建的 RGAItem
        """
        new_item = RGAItem(
            id=str(uuid4()),
            value=value,
            timestamp=self._now_iso(),
            tombstone=False,
        )
        if ref_id is None:
            self._elements.insert(0, new_item)
        else:
            idx = self._find_index(ref_id)
            if idx is None:
                # ref_id 不存在,追加到末尾
                self._elements.append(new_item)
            else:
                self._elements.insert(idx + 1, new_item)
        return new_item

    def remove(self, item_id: str) -> bool:
        """标记元素为 tombstone(逻辑删除)

        返回是否成功标记(元素存在且未被标记)
        """
        for item in self._elements:
            if item.id == item_id and not item.tombstone:
                item.tombstone = True
                return True
        return False

    def _find_index(self, item_id: str) -> int | None:
        """根据 id 查找元素索引,未找到返回 None"""
        for i, item in enumerate(self._elements):
            if item.id == item_id:
                return i
        return None

    def merge(self, other: "RGA") -> "RGA":
        """合并另一个 RGA

        - 按 id 去重:对相同 id 的 item,tombstone 取或(任一删除即删除)
        - 合并后按 timestamp 排序,保证两端一致
        """
        merged_map: dict[str, RGAItem] = {item.id: item for item in self._elements}
        for other_item in other._elements:
            if other_item.id in merged_map:
                # 已存在:合并 tombstone(任一为 True 即 True)
                existing = merged_map[other_item.id]
                merged_map[other_item.id] = RGAItem(
                    id=existing.id,
                    value=existing.value,
                    timestamp=existing.timestamp,
                    tombstone=existing.tombstone or other_item.tombstone,
                )
            else:
                merged_map[other_item.id] = other_item
        # 按 timestamp 排序,保证两端顺序一致
        self._elements = sorted(merged_map.values(), key=lambda x: x.timestamp)
        return self

    def to_list(self) -> list[str]:
        """返回非 tombstone 的值列表"""
        return [item.value for item in self._elements if not item.tombstone]

    def to_dict(self) -> dict:
        """序列化为 dict"""
        return {
            "elements": [
                {
                    "id": item.id,
                    "value": item.value,
                    "timestamp": item.timestamp,
                    "tombstone": item.tombstone,
                }
                for item in self._elements
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RGA":
        """从 dict 反序列化"""
        elements = []
        for item_data in data.get("elements", []):
            elements.append(
                RGAItem(
                    id=item_data["id"],
                    value=item_data["value"],
                    timestamp=item_data["timestamp"],
                    tombstone=item_data.get("tombstone", False),
                )
            )
        return cls(elements=elements)


# ----------------------------------------------------------------------
# CRDTService: 模块级单例,负责 CRDT 持久化与同步追踪
# ----------------------------------------------------------------------


def _op_to_dict(op: SyncOperation) -> dict:
    """SyncOperation ORM 转 dict"""
    return {
        "id": op.id,
        "device_id": op.device_id,
        "op_type": op.op_type,
        "key": op.key,
        "payload": op.payload,
        "synced_devices": op.synced_devices or [],
        "created_at": op.created_at.isoformat() if op.created_at else None,
    }


class CRDTService:
    """CRDT 同步服务

    职责:
    - 将 LWW/ORSet 状态作为 SyncOperation 记录持久化
    - 合并远程副本
    - 追踪每个操作已同步到哪些设备,支持增量同步
    """

    # ===== LWW Register =====

    async def create_lww(self, key: str, value: str, node_id: str) -> dict:
        """创建/更新 LWW Register

        - 若 key 已存在:加载现有 register,调用 set 后 merge 保存
        - 若 key 不存在:新建 register 并保存为 SyncOperation
        """
        register = LWWRegister[str]()
        existing = await self._load_latest_op("lww", key)
        if existing is not None:
            payload = existing.payload or {}
            register = LWWRegister[str].from_dict(payload)

        register.set(value, node_id)
        op = await self._save_op("lww", key, register.to_dict(), node_id)
        return {
            "key": key,
            "register": register.to_dict(),
            "operation": _op_to_dict(op),
        }

    async def get_lww(self, key: str) -> dict | None:
        """获取 LWW Register 值"""
        existing = await self._load_latest_op("lww", key)
        if existing is None:
            return None
        register = LWWRegister[str].from_dict(existing.payload or {})
        return {
            "key": key,
            "register": register.to_dict(),
            "operation": _op_to_dict(existing),
        }

    async def merge_lww(self, key: str, other_register: dict) -> dict:
        """合并远程 LWW Register

        - other_register: {value, timestamp, node_id}
        - 加载本地 register,merge 远程副本后保存
        """
        local = await self._load_latest_op("lww", key)
        if local is None:
            # 本地不存在:直接保存远程副本
            register = LWWRegister[str].from_dict(other_register)
            node_id = other_register.get("node_id")
        else:
            register = LWWRegister[str].from_dict(local.payload or {})
            remote = LWWRegister[str].from_dict(other_register)
            register.merge(remote)
            node_id = (local.device_id or other_register.get("node_id") or "")

        op = await self._save_op("lww", key, register.to_dict(), node_id)
        return {
            "key": key,
            "register": register.to_dict(),
            "operation": _op_to_dict(op),
        }

    # ===== OR-Set =====

    async def create_orset(self, key: str) -> dict:
        """创建空 OR-Set"""
        orset = ORSet()
        op = await self._save_op("orset", key, orset.to_dict(), None)
        return {
            "key": key,
            "orset": orset.to_dict(),
            "operation": _op_to_dict(op),
        }

    async def add_to_orset(self, key: str, value: str) -> dict:
        """向 OR-Set 添加元素"""
        existing = await self._load_latest_op("orset", key)
        if existing is None:
            orset = ORSet()
        else:
            orset = ORSet.from_dict(existing.payload or {})

        tag = orset.add(value)
        op = await self._save_op("orset", key, orset.to_dict(), existing.device_id if existing else None)
        return {
            "key": key,
            "value": value,
            "tag": tag,
            "orset": orset.to_dict(),
            "operation": _op_to_dict(op),
        }

    async def remove_from_orset(self, key: str, value: str) -> dict:
        """从 OR-Set 删除元素"""
        existing = await self._load_latest_op("orset", key)
        if existing is None:
            orset = ORSet()
        else:
            orset = ORSet.from_dict(existing.payload or {})

        removed = orset.remove(value)
        op = await self._save_op("orset", key, orset.to_dict(), existing.device_id if existing else None)
        return {
            "key": key,
            "value": value,
            "removed": removed,
            "orset": orset.to_dict(),
            "operation": _op_to_dict(op),
        }

    async def get_orset_values(self, key: str) -> dict | None:
        """获取 OR-Set 的所有值"""
        existing = await self._load_latest_op("orset", key)
        if existing is None:
            return None
        orset = ORSet.from_dict(existing.payload or {})
        return {
            "key": key,
            "values": orset.values(),
            "orset": orset.to_dict(),
            "operation": _op_to_dict(existing),
        }

    async def merge_orset(self, key: str, other_elements: dict) -> dict:
        """合并远程 OR-Set

        - other_elements: {value: [tags]}
        """
        existing = await self._load_latest_op("orset", key)
        if existing is None:
            orset = ORSet.from_dict(other_elements)
            node_id = None
        else:
            orset = ORSet.from_dict(existing.payload or {})
            remote = ORSet.from_dict(other_elements)
            orset.merge(remote)
            node_id = existing.device_id

        op = await self._save_op("orset", key, orset.to_dict(), node_id)
        return {
            "key": key,
            "orset": orset.to_dict(),
            "operation": _op_to_dict(op),
        }

    # ===== 同步追踪 =====

    async def list_pending_ops(self, device_id: str) -> list[dict]:
        """列出尚未同步到指定设备的操作

        - 筛选 synced_devices 不包含 device_id 的操作
        """
        async with async_session() as session:
            stmt = select(SyncOperation).order_by(SyncOperation.created_at.desc())
            result = await session.execute(stmt)
            pending = []
            for op in result.scalars().all():
                synced = op.synced_devices or []
                if device_id not in synced:
                    pending.append(_op_to_dict(op))
            return pending

    async def mark_synced(self, op_id: int, device_id: str) -> dict | None:
        """标记操作已同步到某设备"""
        async with async_session() as session:
            op = await session.get(SyncOperation, op_id)
            if op is None:
                return None
            synced = op.synced_devices or []
            if device_id not in synced:
                synced.append(device_id)
                op.synced_devices = synced
                await session.commit()
                await session.refresh(op)
            return _op_to_dict(op)

    async def list_keys(self) -> dict:
        """列出所有 CRDT 键(去重,标注 op_type)"""
        async with async_session() as session:
            stmt = select(SyncOperation).order_by(SyncOperation.created_at.desc())
            result = await session.execute(stmt)
            seen: dict[str, str] = {}
            for op in result.scalars().all():
                if op.key not in seen:
                    seen[op.key] = op.op_type
            keys = [{"key": k, "op_type": v} for k, v in seen.items()]
            return {"keys": keys, "count": len(keys)}

    # ===== 内部辅助 =====

    async def _load_latest_op(self, op_type: str, key: str) -> SyncOperation | None:
        """加载指定 (op_type, key) 的最新一条 SyncOperation"""
        async with async_session() as session:
            stmt = (
                select(SyncOperation)
                .where(SyncOperation.op_type == op_type)
                .where(SyncOperation.key == key)
                .order_by(SyncOperation.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def _save_op(
        self,
        op_type: str,
        key: str,
        payload: dict,
        device_id: str | None,
    ) -> SyncOperation:
        """保存一条新的 SyncOperation 记录"""
        async with async_session() as session:
            op = SyncOperation(
                device_id=device_id,
                op_type=op_type,
                key=key,
                payload=payload,
                synced_devices=[device_id] if device_id else [],
            )
            session.add(op)
            await session.commit()
            await session.refresh(op)
            return op


# 模块级单例
crdt_service = CRDTService()
