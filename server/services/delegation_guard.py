from __future__ import annotations
import logging
from ..core.event_bus import get_event_bus

logger = logging.getLogger(__name__)

# 最大委派深度 (借鉴 OpenAkita, 防止递归死循环)
MAX_DELEGATION_DEPTH = 3

class DelegationGuard:
    """委派守卫 — 跟踪委派链深度, 超过阈值拒绝"""

    def __init__(self) -> None:
        # persona_id -> current delegation depth
        self._depths: dict[int, int] = {}

    def can_delegate(self, persona_id: int) -> bool:
        depth = self._depths.get(persona_id, 0)
        return depth < MAX_DELEGATION_DEPTH

    def enter_delegation(self, persona_id: int) -> bool:
        """进入委派, 返回是否允许"""
        depth = self._depths.get(persona_id, 0)
        if depth >= MAX_DELEGATION_DEPTH:
            logger.warning("委派深度超限 persona_id=%s depth=%s", persona_id, depth)
            return False
        self._depths[persona_id] = depth + 1
        # publish 事件
        try:
            import asyncio
            bus = get_event_bus()
            asyncio.create_task(bus.publish(
                "persona.delegated",
                {"persona_id": persona_id, "depth": depth + 1, "max_depth": MAX_DELEGATION_DEPTH},
                source="delegation_guard",
            ))
        except Exception:
            pass
        return True

    def exit_delegation(self, persona_id: int) -> None:
        depth = self._depths.get(persona_id, 0)
        if depth > 0:
            self._depths[persona_id] = depth - 1

    def get_depth(self, persona_id: int) -> int:
        return self._depths.get(persona_id, 0)

_guard = DelegationGuard()
def get_delegation_guard() -> DelegationGuard:
    return _guard
