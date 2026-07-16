# server/cu/safety/emergency_stop.py
"""紧急停止（三级响应）"""
from __future__ import annotations
import threading


class EmergencyStopError(RuntimeError):
    """急停触发异常"""


class EmergencyStop:
    """全局急停开关

    使用 threading.Event 而非 asyncio.Event，使其在同步与异步上下文中均可工作。
    """

    def __init__(self):
        self._stop_flag = threading.Event()
        self._reason: str | None = None

    def trigger(self, reason: str = "manual") -> None:
        self._reason = reason
        self._stop_flag.set()

    async def trigger_async(self, reason: str = "manual") -> None:
        """异步触发，委托给同步 trigger。"""
        self.trigger(reason)

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
