"""文件夹监控服务(Phase 7B)

使用 watchdog 监控文件夹变化,支持 created/modified/deleted/moved 事件类型,
支持递归监控和 ignore_patterns 文件模式过滤。

依赖(可选,缺失时返回错误而不是崩溃):
- watchdog: 文件系统事件监控
"""

from __future__ import annotations

import fnmatch
import threading
from datetime import datetime
from typing import Any

from ..api.models import FileWatcherConfig

# 可选依赖:watchdog
try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.events import FileSystemEvent  # type: ignore

    _HAS_WATCHDOG = True
except ImportError:
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore
    FileSystemEvent = None  # type: ignore
    _HAS_WATCHDOG = False


class _Handler(FileSystemEventHandler):  # type: ignore[misc]
    """watchdog 事件处理器

    将 watchdog 事件转发到 FileWatcher._on_event 方法。
    当 watchdog 不可用时,基类为 object,该类仍可被实例化(但不会被使用)。
    """

    def __init__(self, watcher: "FileWatcher") -> None:
        # 不调用 super().__init__() 以兼容基类为 object 的情况
        self._watcher = watcher

    def on_created(self, event: Any) -> None:  # noqa: D401
        self._watcher._on_event("created", event)

    def on_modified(self, event: Any) -> None:
        self._watcher._on_event("modified", event)

    def on_deleted(self, event: Any) -> None:
        self._watcher._on_event("deleted", event)

    def on_moved(self, event: Any) -> None:
        self._watcher._on_event("moved", event)


class FileWatcher:
    """文件夹监控器

    使用 watchdog Observer 监控多个文件夹,事件记录到 events 列表。
    Observer 在后台线程运行,通过 _lock 保护 events 列表的线程安全。
    """

    def __init__(self) -> None:
        self.config: FileWatcherConfig = FileWatcherConfig()
        self.observer: Any = None
        self.events: list[dict[str, Any]] = []
        self._running: bool = False
        self._lock = threading.Lock()
        self._watched_paths: list[str] = []

    # ===== 生命周期 =====

    def start(self, config: FileWatcherConfig | None = None) -> bool:
        """启动文件夹监控

        - 保存 config
        - 使用 watchdog Observer 监控 config.paths 中的路径
        - 为每个路径设置 FileSystemEventHandler
        - 返回是否成功启动
        """
        if not _HAS_WATCHDOG:
            return False
        if self._running:
            return True
        if config is not None:
            self.config = config
        if not self.config.enabled:
            return False
        if not self.config.paths:
            return False

        try:
            self.observer = Observer()  # type: ignore[assignment]
        except Exception:
            self.observer = None
            return False

        handler = _Handler(self)
        watched: list[str] = []
        for path in self.config.paths:
            try:
                self.observer.schedule(  # type: ignore[union-attr]
                    handler,
                    path,
                    recursive=bool(self.config.recursive),
                )
                watched.append(path)
            except Exception:
                # 单个路径失败不影响其他路径
                continue

        if not watched:
            self.observer = None
            return False

        try:
            self.observer.start()  # type: ignore[union-attr]
        except Exception:
            self.observer = None
            return False

        self._watched_paths = watched
        self._running = True
        return True

    def stop(self) -> bool:
        """停止文件夹监控

        - 停止 observer
        - 返回是否成功停止
        """
        self._running = False
        if self.observer is not None:
            try:
                self.observer.stop()  # type: ignore[union-attr]
                self.observer.join(timeout=1.0)  # type: ignore[union-attr]
            except Exception:
                pass
            self.observer = None
        self._watched_paths = []
        return True

    # ===== 事件处理 =====

    def _on_event(self, event_type: str, event: Any) -> None:
        """事件处理

        - 按 config.event_types 过滤
        - 按 config.ignore_patterns 过滤
        - 记录到 events 列表(线程安全)
        """
        # 按事件类型过滤
        if event_type not in self.config.event_types:
            return

        # 提取路径(支持 moved 事件的 src_path / dest_path)
        src_path = getattr(event, "src_path", "") or ""
        dest_path = getattr(event, "dest_path", "") or ""
        is_directory = bool(getattr(event, "is_directory", False))

        # 按 ignore_patterns 过滤
        if self._should_ignore(src_path) or (
            dest_path and self._should_ignore(dest_path)
        ):
            return

        record = {
            "event_type": event_type,
            "src_path": src_path,
            "dest_path": dest_path,
            "is_directory": is_directory,
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self.events.append(record)
            # 限制事件历史大小,避免内存膨胀
            if len(self.events) > 1000:
                self.events = self.events[-1000:]

    def _should_ignore(self, path: str) -> bool:
        """检查路径是否应该被忽略(按 ignore_patterns 过滤)"""
        if not self.config.ignore_patterns:
            return False
        import os

        basename = os.path.basename(path) if path else ""
        for pattern in self.config.ignore_patterns:
            # 使用 fnmatch 支持 glob 风格模式
            if fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(path, pattern):
                return True
        return False

    # ===== 查询 =====

    def get_events(
        self,
        limit: int = 100,
        path: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取文件事件

        - limit: 最多返回多少条(从最新开始)
        - path: 按路径前缀过滤
        - event_type: 按事件类型过滤(created/modified/deleted/moved)
        """
        with self._lock:
            items = list(self.events)
        if path:
            items = [
                r for r in items
                if r.get("src_path", "").startswith(path)
                or r.get("dest_path", "").startswith(path)
            ]
        if event_type:
            items = [r for r in items if r.get("event_type") == event_type]
        # 从最新开始
        items = list(reversed(items))
        if limit > 0:
            items = items[:limit]
        return items

    def clear_events(self) -> int:
        """清空事件,返回被清空的条数"""
        with self._lock:
            count = len(self.events)
            self.events = []
        return count

    def get_status(self) -> dict[str, Any]:
        """获取文件监控状态"""
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "paths": self._watched_paths,
            "recursive": self.config.recursive,
            "event_types": self.config.event_types,
            "events_count": len(self.events),
            "watchdog_available": _HAS_WATCHDOG,
            "library_available": _HAS_WATCHDOG,
        }


# 模块级单例
file_watcher = FileWatcher()
