"""系统托盘 + 全局快捷键服务(Phase 7B)

提供系统托盘图标(显示窗口/快速对话/退出菜单)和全局快捷键功能。
pystray 在后台线程运行,keyboard 库注册全局快捷键回调。

依赖(均为可选,缺失时返回错误而不是崩溃):
- pystray: 系统托盘图标
- PIL(Pillow): pystray 图标所需的图像处理
- keyboard: 全局快捷键注册
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from ..api.models import ShortcutConfig, TrayConfig

# 可选依赖:pystray
try:
    import pystray  # type: ignore

    _HAS_PYSTRAY = True
except ImportError:
    pystray = None  # type: ignore
    _HAS_PYSTRAY = False

# 可选依赖:Pillow(pystray 需要用来生成图标)
try:
    from PIL import Image, ImageDraw  # type: ignore

    _HAS_PIL = True
except ImportError:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    _HAS_PIL = False

# 可选依赖:keyboard
try:
    import keyboard  # type: ignore

    _HAS_KEYBOARD = True
except ImportError:
    keyboard = None  # type: ignore
    _HAS_KEYBOARD = False


def _create_default_icon() -> Any:
    """创建默认托盘图标(一个简单的彩色方块)

    需要 PIL 可用,否则返回 None。
    """
    if not _HAS_PIL:
        return None
    try:
        img = Image.new("RGB", (64, 64), color=(30, 30, 60))  # type: ignore[union-attr]
        draw = ImageDraw.Draw(img)  # type: ignore[union-attr]
        # 绘制一个简单的字母 N(Nebula)
        draw.text((20, 18), "N", fill=(120, 180, 255))
        return img
    except Exception:
        return None


class TrayService:
    """系统托盘 + 全局快捷键服务

    - pystray Icon 在后台线程运行,提供菜单项
    - keyboard 库注册全局快捷键,触发回调
    - 通过 callbacks 字典传递回调函数(如 toggle_window/quick_chat/screenshot)
    """

    def __init__(self) -> None:
        self.config: TrayConfig = TrayConfig()
        self.shortcut_config: ShortcutConfig = ShortcutConfig()
        self.icon: Any = None
        self.keyboard_hooks: list[Any] = []
        self.callbacks: dict[str, Callable[..., Any]] = {}
        self._tray_running: bool = False
        self._shortcuts_running: bool = False
        self._lock = threading.Lock()

    # ===== 设置回调 =====

    def set_callbacks(self, callbacks: dict[str, Callable[..., Any]]) -> None:
        """设置快捷键回调函数字典

        键为动作名(如 toggle_window/quick_chat/screenshot),
        值为对应的可调用对象。
        """
        with self._lock:
            self.callbacks = dict(callbacks)

    def _invoke_callback(self, action: str, *args: Any, **kwargs: Any) -> Any:
        """安全调用回调函数,异常不会传播"""
        with self._lock:
            callback = self.callbacks.get(action)
        if callback is None:
            return None
        try:
            return callback(*args, **kwargs)
        except Exception:
            return None

    # ===== 系统托盘 =====

    def start_tray(self, config: TrayConfig | None = None) -> bool:
        """启动系统托盘

        - 使用 pystray 创建系统托盘图标
        - 设置菜单项(显示窗口/快速对话/退出)
        - 在后台线程运行
        - 返回是否成功启动
        """
        if not _HAS_PYSTRAY or not _HAS_PIL:
            return False
        if self._tray_running:
            return True
        if config is not None:
            self.config = config
        if not self.config.enabled:
            return False

        # 准备图标图像
        if self.config.icon_path:
            try:
                image = Image.open(self.config.icon_path)  # type: ignore[union-attr]
            except Exception:
                image = _create_default_icon()
                if image is None:
                    return False
        else:
            image = _create_default_icon()
            if image is None:
                return False

        # 构建菜单项
        try:
            menu = pystray.Menu(  # type: ignore[union-attr]
                pystray.MenuItem(  # type: ignore[union-attr]
                    "显示窗口",
                    lambda: self._invoke_callback("toggle_window"),
                ),
                pystray.MenuItem(  # type: ignore[union-attr]
                    "快速对话",
                    lambda: self._invoke_callback("quick_chat"),
                ),
                pystray.MenuItem(  # type: ignore[union-attr]
                    "截图",
                    lambda: self._invoke_callback("screenshot"),
                ),
                pystray.Menu.SEPARATOR,  # type: ignore[union-attr]
                pystray.MenuItem(  # type: ignore[union-attr]
                    "退出",
                    self._on_exit,
                ),
            )
        except Exception:
            return False

        try:
            self.icon = pystray.Icon(  # type: ignore[union-attr]
                "pangu_nebula",
                image,
                self.config.title,
                menu,
            )
        except Exception:
            self.icon = None
            return False

        # pystray Icon.run 会阻塞,需在后台线程运行
        try:
            self._tray_thread = threading.Thread(
                target=self._run_icon, daemon=True
            )
            self._tray_thread.start()
        except Exception:
            self.icon = None
            return False

        self._tray_running = True
        return True

    def _run_icon(self) -> None:
        """在后台线程中运行 pystray Icon"""
        if self.icon is None:
            return
        try:
            self.icon.run()
        except Exception:
            pass

    def _on_exit(self, icon: Any = None, item: Any = None) -> None:
        """退出菜单项回调"""
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
        self._tray_running = False

    def stop_tray(self) -> bool:
        """停止系统托盘

        - 停止 pystray icon
        - 返回是否成功停止
        """
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
        self._tray_running = False
        return True

    # ===== 全局快捷键 =====

    def start_shortcuts(self, config: ShortcutConfig | None = None) -> bool:
        """启动全局快捷键

        - 使用 keyboard 库注册快捷键
        - 为每个 shortcut 注册回调
        - 返回是否成功启动
        """
        if not _HAS_KEYBOARD:
            return False
        if self._shortcuts_running:
            return True
        if config is not None:
            self.shortcut_config = config
        if not self.shortcut_config.enabled:
            return False

        # 清理旧 hooks
        self._clear_hooks()

        try:
            for hotkey, action in self.shortcut_config.shortcuts.items():
                hook = keyboard.add_hotkey(  # type: ignore[union-attr]
                    hotkey, self._make_shortcut_callback(action)
                )
                self.keyboard_hooks.append(hook)
        except Exception:
            # 注册失败时清理已注册的 hooks
            self._clear_hooks()
            return False

        self._shortcuts_running = True
        return True

    def _make_shortcut_callback(self, action: str) -> Callable[[], None]:
        """为指定动作创建快捷键回调(避免闭包变量问题)"""

        def _callback() -> None:
            self._invoke_callback(action)

        return _callback

    def _clear_hooks(self) -> None:
        """清理所有已注册的 keyboard hook"""
        for hook in self.keyboard_hooks:
            try:
                keyboard.remove_hotkey(hook)  # type: ignore[union-attr]
            except Exception:
                pass
        self.keyboard_hooks = []

    def stop_shortcuts(self) -> bool:
        """停止全局快捷键

        - 取消所有 keyboard hook
        - 返回是否成功停止
        """
        self._clear_hooks()
        self._shortcuts_running = False
        return True

    # ===== 状态 =====

    def get_status(self) -> dict[str, Any]:
        """获取托盘 + 快捷键状态"""
        return {
            "tray_running": self._tray_running,
            "tray_enabled": self.config.enabled,
            "tray_title": self.config.title,
            "shortcuts_running": self._shortcuts_running,
            "shortcuts_enabled": self.shortcut_config.enabled,
            "shortcuts": self.shortcut_config.shortcuts,
            "pystray_available": _HAS_PYSTRAY,
            "pil_available": _HAS_PIL,
            "keyboard_available": _HAS_KEYBOARD,
            "tray_available": _HAS_PYSTRAY and _HAS_PIL,
            "shortcuts_available": _HAS_KEYBOARD,
        }


# 模块级单例
tray_service = TrayService()
