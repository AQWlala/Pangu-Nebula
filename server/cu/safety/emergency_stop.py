# server/cu/safety/emergency_stop.py
"""紧急停止（三级响应）"""
from __future__ import annotations
import asyncio


class EmergencyStopError(RuntimeError):
    """急停触发异常"""


class EmergencyStop:
    """全局急停开关"""

    def __init__(self):
        self._stop_flag = asyncio.Event()
        self._reason: str | None = None

    async def trigger(self, reason: str = "manual") -> None:
        self._reason = reason
        self._stop_flag.set()

    def check(self) -> None:
        if self._stop_flag.is_set():
            raise EmergencyStopError(f"任务已急停: {self._reason}")

    def reset(self) -> None:
        self._stop_flag.clear()
        self._reason = None

    def is_triggered(self) -> bool:
        return self._stop_flag.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason
