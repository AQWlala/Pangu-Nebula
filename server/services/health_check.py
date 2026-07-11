"""Provider 健康检查服务(Phase 10B)

定时检查所有已注册 Provider 的连通性,维护状态与历史记录,
并根据连续失败次数进行降级(down/degraded)标记。

降级规则:
- 连续 3 次失败: degraded(降级)
- 连续 5 次失败: down(下线)
- 通知: 暂时只记录到状态中,不实际发送通知

状态与历史均保存在内存中(模块级单例),进程重启后清空。
"""

import asyncio
import time
from datetime import datetime

from ..providers.registry import get_provider, is_registered, list_providers


# 降级阈值
_DEGRADED_THRESHOLD = 3  # 连续失败 3 次标记为 degraded
_DOWN_THRESHOLD = 5  # 连续失败 5 次标记为 down
_HISTORY_MAX = 100  # 每个 Provider 最多保留 100 条历史记录


class HealthCheckService:
    """Provider 健康检查服务(模块级单例)"""

    def __init__(self) -> None:
        # name -> {name, healthy, latency_ms, last_check, error, consecutive_failures, status}
        self._status: dict[str, dict] = {}
        # name -> list[{timestamp, healthy, latency_ms, error}]
        self._history: dict[str, list[dict]] = {}
        # 后台监控任务
        self._monitor_task: asyncio.Task | None = None
        self._monitor_interval: int = 300
        self._monitor_running: bool = False
        self._monitor_last_check: str | None = None

    # ===== 核心检查方法 =====

    async def check_provider(self, name: str) -> dict:
        """检查单个 Provider 的连通性

        调用 provider.test_connection(),测量延迟,更新状态与历史。
        返回该 Provider 的最新状态。
        """
        if not is_registered(name):
            raise ValueError(f"Provider '{name}' not registered")

        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            provider = get_provider(name)
            healthy = await provider.test_connection()
            if not healthy:
                error = "test_connection returned False"
        except Exception as exc:  # noqa: BLE001 - 健康检查需捕获所有异常
            healthy = False
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = int((time.monotonic() - start) * 1000)

        return self._record(name, healthy, latency_ms, error)

    async def check_all(self) -> list[dict]:
        """检查所有已注册 Provider,返回状态列表"""
        providers = list_providers()
        results: list[dict] = []
        for info in providers:
            name = info.get("name")
            if not name:
                continue
            try:
                status = await self.check_provider(name)
            except Exception as exc:  # noqa: BLE001
                # 单个 Provider 检查异常不应中断整体流程
                status = self._record(
                    name, False, 0, f"check_all error: {type(exc).__name__}: {exc}"
                )
            results.append(status)
        self._monitor_last_check = datetime.utcnow().isoformat()
        return results

    # ===== 状态查询 =====

    def get_status(self, name: str) -> dict | None:
        """获取某 Provider 最近状态;不存在返回 None"""
        return self._status.get(name)

    def list_status(self) -> list[dict]:
        """列出所有 Provider 状态"""
        return list(self._status.values())

    def get_history(self, name: str, limit: int = 20) -> list[dict]:
        """获取 Provider 历史记录(按时间倒序,最多 limit 条)"""
        history = self._history.get(name, [])
        limit = max(limit, 1)
        # 历史已按追加顺序保存,最新在末尾,返回倒序
        return list(reversed(history[-limit:]))

    # ===== 后台监控 =====

    def start_monitor(self, interval_seconds: int = 300) -> dict:
        """启动后台监控任务

        - 若已有任务在运行,先停止再重启
        - interval_seconds 最小 10 秒
        """
        if interval_seconds < 10:
            interval_seconds = 10

        if self._monitor_task is not None and not self._monitor_task.done():
            self.stop_monitor()

        self._monitor_interval = interval_seconds
        self._monitor_running = True
        self._monitor_task = asyncio.ensure_future(self._monitor_loop())
        return {
            "running": True,
            "interval": self._monitor_interval,
            "last_check": self._monitor_last_check,
        }

    def stop_monitor(self) -> dict:
        """停止后台监控任务"""
        self._monitor_running = False
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
        self._monitor_task = None
        return {
            "running": False,
            "interval": self._monitor_interval,
            "last_check": self._monitor_last_check,
        }

    def get_monitor_status(self) -> dict:
        """获取监控状态"""
        running = self._monitor_running and (
            self._monitor_task is not None and not self._monitor_task.done()
        )
        return {
            "running": running,
            "interval": self._monitor_interval,
            "last_check": self._monitor_last_check,
        }

    # ===== 内部方法 =====

    async def _monitor_loop(self) -> None:
        """后台监控循环:按间隔周期性执行 check_all"""
        try:
            while self._monitor_running:
                try:
                    await self.check_all()
                except Exception:  # noqa: BLE001
                    # 监控循环不应因单次异常退出
                    pass
                await asyncio.sleep(self._monitor_interval)
        except asyncio.CancelledError:
            # 正常取消,忽略
            pass

    def _record(
        self, name: str, healthy: bool, latency_ms: int, error: str | None
    ) -> dict:
        """记录一次检查结果,更新状态与历史,返回最新状态"""
        prev = self._status.get(name, {})
        prev_failures = prev.get("consecutive_failures", 0)

        if healthy:
            consecutive_failures = 0
        else:
            consecutive_failures = prev_failures + 1

        # 计算状态: down > degraded > healthy/unhealthy
        if consecutive_failures >= _DOWN_THRESHOLD:
            status = "down"
        elif consecutive_failures >= _DEGRADED_THRESHOLD:
            status = "degraded"
        elif healthy:
            status = "healthy"
        else:
            status = "unhealthy"

        now_iso = datetime.utcnow().isoformat()
        status_entry = {
            "name": name,
            "healthy": healthy,
            "status": status,
            "latency_ms": latency_ms,
            "last_check": now_iso,
            "error": error,
            "consecutive_failures": consecutive_failures,
        }
        self._status[name] = status_entry

        history_entry = {
            "timestamp": now_iso,
            "healthy": healthy,
            "latency_ms": latency_ms,
            "error": error,
        }
        hist = self._history.setdefault(name, [])
        hist.append(history_entry)
        # 限制历史长度
        if len(hist) > _HISTORY_MAX:
            self._history[name] = hist[-_HISTORY_MAX:]

        return status_entry


# 模块级单例
health_check_service = HealthCheckService()
