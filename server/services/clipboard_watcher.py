"""剪贴板监控服务(Phase 7B)

通过轮询方式监控剪贴板内容变化,记录历史。
支持文本和图片两种内容类型,支持正则忽略模式。

依赖(均为可选,缺失时返回错误而不是崩溃):
- pyperclip: 跨平台剪贴板读取
- win32clipboard: Windows 原生备选方案
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from ..api.models import ClipboardWatcherConfig

# 可选依赖:pyperclip
try:
    import pyperclip  # type: ignore

    _HAS_PYPERCLIP = True
except ImportError:
    pyperclip = None  # type: ignore
    _HAS_PYPERCLIP = False

# 可选依赖:win32clipboard(Windows 备选方案)
try:
    import win32clipboard  # type: ignore

    _HAS_WIN32 = True
except ImportError:
    win32clipboard = None  # type: ignore
    _HAS_WIN32 = False


def _read_clipboard_text() -> str | None:
    """读取剪贴板文本内容

    优先使用 pyperclip,失败时尝试 win32clipboard。
    任何异常都返回 None。
    """
    if _HAS_PYPERCLIP:
        try:
            return pyperclip.paste()  # type: ignore[union-attr]
        except Exception:
            pass
    if _HAS_WIN32:
        try:
            win32clipboard.OpenClipboard()  # type: ignore[union-attr]
            try:
                if win32clipboard.IsClipboardFormatAvailable(  # type: ignore[union-attr]
                    win32clipboard.CF_UNICODETEXT  # type: ignore[union-attr]
                ):
                    return win32clipboard.GetClipboardData(  # type: ignore[union-attr]
                        win32clipboard.CF_UNICODETEXT  # type: ignore[union-attr]
                    )
            finally:
                win32clipboard.CloseClipboard()  # type: ignore[union-attr]
        except Exception:
            return None
    return None


def _is_image_on_clipboard() -> bool:
    """检测剪贴板中是否有图片(仅 win32clipboard 可用)"""
    if not _HAS_WIN32:
        return False
    try:
        win32clipboard.OpenClipboard()  # type: ignore[union-attr]
        try:
            # CF_DIB = 8, CF_DIBV5 = 17
            return win32clipboard.IsClipboardFormatAvailable(8) or (  # type: ignore[union-attr]
                win32clipboard.IsClipboardFormatAvailable(17)  # type: ignore[union-attr]
            )
        finally:
            win32clipboard.CloseClipboard()  # type: ignore[union-attr]
    except Exception:
        return False


class ClipboardWatcher:
    """剪贴板监控器

    通过 asyncio.Task 轮询剪贴板,内容变化时记录到 history 列表。
    """

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.config: ClipboardWatcherConfig = ClipboardWatcherConfig()
        self.last_content: Any = None
        self._task: asyncio.Task | None = None
        self._running: bool = False

    # ===== 生命周期 =====

    def start(self, config: ClipboardWatcherConfig | None = None) -> bool:
        """启动剪贴板监控

        - 保存 config
        - 创建 asyncio.Task 执行 _watch_loop
        - 返回是否成功启动
        """
        if not _HAS_PYPERCLIP and not _HAS_WIN32:
            return False
        if self._running:
            return True
        if config is not None:
            self.config = config
        if not self.config.enabled:
            return False
        self._running = True
        try:
            self._task = asyncio.ensure_future(self._watch_loop())
        except RuntimeError:
            # 无事件循环时退化为同步标记
            self._running = False
            return False
        return True

    def stop(self) -> bool:
        """停止剪贴板监控

        - 取消 asyncio.Task
        - 返回是否成功停止
        """
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                # 不等待,避免阻塞
                pass
            except Exception:
                pass
        self._task = None
        return True

    # ===== 监控循环 =====

    async def _watch_loop(self) -> None:
        """监控循环:按 interval_seconds 轮询剪贴板"""
        interval = max(0.1, float(self.config.interval_seconds))
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                # 任何异常都不应中断监控循环
                pass
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _poll_once(self) -> None:
        """执行一次轮询:读取剪贴板并与上次内容比较"""
        # 文本检测
        text = _read_clipboard_text()
        if text is not None and text != "":
            if text != self.last_content:
                if self._should_record(text):
                    self._record("text", text)
                self.last_content = text
                return
        # 图片检测(仅当 filter_image 启用时)
        if self.config.filter_image and _is_image_on_clipboard():
            # 仅标记检测到图片,不存储二进制(隐私)
            marker = "[image on clipboard]"
            if marker != self.last_content:
                if self._should_record(marker):
                    self._record("image", marker)
                self.last_content = marker
                return

    def _should_record(self, content: str) -> bool:
        """检查内容是否应该被记录(按 ignore_patterns 过滤)"""
        if not self.config.ignore_patterns:
            return True
        for pattern in self.config.ignore_patterns:
            try:
                if re.search(pattern, content):
                    return False
            except re.error:
                # 模式无效时忽略该模式
                continue
        return True

    def _record(self, content_type: str, content: Any) -> None:
        """记录一条历史,并按 max_history 截断"""
        record = {
            "content_type": content_type,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self.history.append(record)
        # 截断到 max_history
        max_history = max(1, int(self.config.max_history))
        if len(self.history) > max_history:
            # 保留最新的 N 条
            self.history = self.history[-max_history:]

    # ===== 查询 =====

    def get_history(
        self, limit: int = 100, content_type: str | None = None
    ) -> list[dict[str, Any]]:
        """获取剪贴板历史

        - limit: 最多返回多少条(从最新开始)
        - content_type: 按 text/image 过滤,为 None 时返回全部
        """
        items = self.history
        if content_type:
            items = [r for r in items if r.get("content_type") == content_type]
        # 从最新开始
        items = list(reversed(items))
        if limit > 0:
            items = items[:limit]
        return items

    def clear_history(self) -> int:
        """清空历史,返回被清空的条数"""
        count = len(self.history)
        self.history = []
        return count

    def get_status(self) -> dict[str, Any]:
        """获取剪贴板监控状态"""
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "interval_seconds": self.config.interval_seconds,
            "max_history": self.config.max_history,
            "history_count": len(self.history),
            "pyperclip_available": _HAS_PYPERCLIP,
            "win32clipboard_available": _HAS_WIN32,
            "library_available": _HAS_PYPERCLIP or _HAS_WIN32,
        }


# 模块级单例
clipboard_watcher = ClipboardWatcher()
