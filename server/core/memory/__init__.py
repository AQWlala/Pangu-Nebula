"""Memory core module - public API surface.

Re-exports from services/ for stable import paths.
"""
from server.services.memory_service import MemoryService
from server.services.sponge_engine import SpongeEngine, SpongeResult
from server.services.blackhole_engine import BlackHoleEngine, CompressionResult
from server.services.compact import CompactEngine, CompactResult

__all__ = [
    "MemoryService",
    "SpongeEngine",
    "SpongeResult",
    "BlackHoleEngine",
    "CompressionResult",
    "CompactEngine",
    "CompactResult",
]