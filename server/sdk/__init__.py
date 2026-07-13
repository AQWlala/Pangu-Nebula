"""Pangu Memory SDK (merged into server.sdk) — 可独立使用的记忆系统 SDK

6 层认知记忆 + 海绵/黑洞双引擎 + CRDT 跨设备同步

基本用法:
    from server.sdk import MemoryStore, SpongeStrategy, BlackHoleEngine
    
    store = MemoryStore()
    await store.init()
    await store.add("some memory content", layer="L1")
"""

from .store import MemoryStore
from .sponge import SpongeStrategy
from .blackhole import CompressionStrategy
from .crdt import CRDTSyncManager
from .types import Memory, MemoryLayer, MemoryMetadata

__version__ = "0.1.0"
__all__ = [
    "MemoryStore",
    "SpongeStrategy",
    "CompressionStrategy",
    "CRDTSyncManager",
    "Memory",
    "MemoryLayer",
    "MemoryMetadata",
]
