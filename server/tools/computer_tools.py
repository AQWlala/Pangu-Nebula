# server/tools/computer_tools.py
"""v2.2.0 Phase 5 — Computer Use 工具集

将桌面操作能力暴露为 LLM 可调用的工具:
- computer_screenshot: 全屏截图 (base64)
- computer_click: 鼠标点击 (x, y 坐标)
- computer_type_text: 键盘输入文本
- computer_get_a11y_tree: 无障碍树 (Windows UI Automation)

依赖(可选,缺失时返回错误而非崩溃):
- Pillow (PIL): 截图 (跨平台)
- pyautogui: 鼠标/键盘控制 (跨平台)
- uiautomation: 无障碍树 (Windows 专用)

v2.2.1 F7: 权限模型更新
    所有工具需 persona.computer_use_enabled=True (由 ToolExecutor 权限矩阵拦截)。
    此字段与 browser_use_enabled 解耦,默认关闭 (安全优先)。

v2.2.1 F7: 安全加固
    - computer_type_text 新增危险文本黑名单 (format / del /f / rm -rf / shutdown / taskkill)
    - 检测危险组合键 (win+r / ctrl+alt+del / alt+f4)
    - computer_screenshot 截图后压缩到 1024x768 + JPEG quality=85 (修复 S8)

注意: 这些是 Rust computer_use 模块的 Python 兜底实现。
当 Rust 模块编译完成 (HAS_RUST=True) 时,应优先调用 Rust 实现。
"""
from __future__ import annotations

import asyncio
import base64
import io
import re

from .registry import BaseTool, ToolResult, register_tool


# v2.2.1 F7: computer_type_text 危险文本黑名单
# 检测 LLM 试图通过 type_text 执行破坏性命令
_DANGEROUS_TEXT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE), "format 格式化磁盘"),
    (re.compile(r"\bdel\s+/[sf]", re.IGNORECASE), "del /s /f 强制删除"),
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "rm -rf 递归删除"),
    (re.compile(r"\bshutdown\b", re.IGNORECASE), "shutdown 关机"),
    (re.compile(r"\btaskkill\s+/f", re.IGNORECASE), "taskkill /f 强制结束进程"),
    # 危险组合键
    (re.compile(r"\bwin\s*\+\s*r\b", re.IGNORECASE), "win+r 运行对话框 (可疑)"),
    (re.compile(r"\bctrl\s*\+\s*alt\s*\+\s*del\b", re.IGNORECASE), "ctrl+alt+del 系统快捷键"),
    (re.compile(r"\balt\s*\+\s*f4\b", re.IGNORECASE), "alt+f4 关闭窗口/关机"),
]

# v2.2.1 F7: 截图压缩参数 (修复 S8 内存爆炸)
_SCREENSHOT_MAX_WIDTH = 1024
_SCREENSHOT_MAX_HEIGHT = 768
_SCREENSHOT_JPEG_QUALITY = 85


def _is_cancelled(cancel_token) -> bool:
    """v2.3.1 P0-6: 检查协作式取消令牌是否被设置。

    cancel_token 由 tool_executor 注入 (threading.Event), 超时后 set。
    返回 True 表示已取消, 工具应尽快返回。
    """
    return cancel_token is not None and cancel_token.is_set()


def _check_text_safety(text: str) -> tuple[bool, str]:
    """检查 type_text 的文本是否安全

    Returns:
        (safe, reason): safe=True 时 reason 为空
    """
    if not text:
        return True, ""
    for pattern, desc in _DANGEROUS_TEXT_PATTERNS:
        if pattern.search(text):
            return False, f"危险输入被拦截: {desc}"
    return True, ""


def _check_dependencies() -> tuple[bool, str]:
    """检查计算机操作依赖是否可用。返回 (ok, error_message)。"""
    try:
        import PIL  # type: ignore  # noqa: F401
        import pyautogui  # type: ignore  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, f"计算机操作依赖未安装: {e}. 请运行 pip install pillow pyautogui"


@register_tool("computer_screenshot")
class ComputerScreenshotTool(BaseTool):
    name = "computer_screenshot"
    description = (
        "Take a full-screen screenshot of the desktop. Returns base64-encoded JPEG. "
        "Use to see the current screen state before clicking or typing."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = set()

    async def execute(self, **kwargs) -> ToolResult:
        # v2.3.1 P0-6: 协作式取消 — cancel_token 由 tool_executor 注入
        cancel_token = kwargs.get("cancel_token")
        if _is_cancelled(cancel_token):
            return ToolResult(success=False, output="", error="操作已取消")
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            # v2.3.1 P0-6: 进入线程前再次检查取消 (cooperative cancellation)
            if _is_cancelled(cancel_token):
                return ToolResult(success=False, output="", error="操作已取消")
            # v2.3.0 Phase 3-A1: 同步阻塞调用 (pyautogui + PIL) 包入 asyncio.to_thread
            # 避免阻塞事件循环 (截图 + 压缩可能耗时数百毫秒)
            img_w, img_h, img_b64 = await asyncio.to_thread(self._capture_and_compress)
            return ToolResult(
                success=True,
                output=f"截图成功 (JPEG {img_w}x{img_h}, base64 长度: {len(img_b64)})。前 200 字符: {img_b64[:200]}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"截图失败: {exc}")

    @staticmethod
    def _capture_and_compress() -> tuple[int, int, str]:
        """同步: 截图 + 压缩 + base64 编码。在线程中执行避免阻塞事件循环。"""
        import pyautogui  # type: ignore

        # pyautogui.screenshot() 返回 PIL.Image
        img = pyautogui.screenshot()

        # v2.2.1 F7: 截图压缩 (修复 S8) — 缩放到 1024x768 + JPEG quality=85
        # 保持比例,仅当原图大于目标尺寸时缩放
        # 使用 PIL 默认的 BICUBIC 重采样 (无需显式 import PIL.Image)
        orig_w, orig_h = img.size
        if orig_w > _SCREENSHOT_MAX_WIDTH or orig_h > _SCREENSHOT_MAX_HEIGHT:
            img.thumbnail((_SCREENSHOT_MAX_WIDTH, _SCREENSHOT_MAX_HEIGHT))
        # 转 RGB (JPEG 不支持 alpha 通道)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_SCREENSHOT_JPEG_QUALITY, optimize=True)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return img.size[0], img.size[1], img_b64


@register_tool("computer_click")
class ComputerClickTool(BaseTool):
    name = "computer_click"
    description = (
        "Click the mouse at the given screen coordinates (x, y). "
        "Use computer_screenshot first to identify the correct coordinates."
    )
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate (pixels from left)"},
            "y": {"type": "integer", "description": "Y coordinate (pixels from top)"},
            "button": {
                "type": "string",
                "description": "Mouse button: 'left', 'right', or 'middle'",
                "default": "left",
            },
        },
        "required": ["x", "y"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"x", "y", "button"}

    async def execute(self, x: int, y: int, button: str = "left", **kwargs) -> ToolResult:
        # v2.3.1 P0-6: 协作式取消
        cancel_token = kwargs.get("cancel_token")
        if _is_cancelled(cancel_token):
            return ToolResult(success=False, output="", error="操作已取消")
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            import pyautogui  # type: ignore

            # v2.3.1 P0-6: 进入线程前再次检查取消
            if _is_cancelled(cancel_token):
                return ToolResult(success=False, output="", error="操作已取消")
            # v2.3.0 Phase 3-A1: pyautogui.click 是同步阻塞调用,包入 asyncio.to_thread
            await asyncio.to_thread(pyautogui.click, x=x, y=y, button=button)
            return ToolResult(
                success=True,
                output=f"已在 ({x}, {y}) 点击 {button} 按钮",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"点击失败: {exc}")


@register_tool("computer_type_text")
class ComputerTypeTextTool(BaseTool):
    name = "computer_type_text"
    description = (
        "Type text using the keyboard. Simulates keystrokes for each character. "
        "Use computer_click first to focus the target input field."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to type"},
            "interval": {
                "type": "number",
                "description": "Delay between keystrokes in seconds",
                "default": 0.0,
            },
        },
        "required": ["text"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"text", "interval"}

    async def execute(self, text: str, interval: float = 0.0, **kwargs) -> ToolResult:
        # v2.3.1 P0-6: 协作式取消
        cancel_token = kwargs.get("cancel_token")
        if _is_cancelled(cancel_token):
            return ToolResult(success=False, output="", error="操作已取消")
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)

        # v2.2.1 F7: 危险文本黑名单检测
        safe, reason = _check_text_safety(text)
        if not safe:
            return ToolResult(success=False, output="", error=reason)

        try:
            import pyautogui as pa  # type: ignore

            # v2.3.1 P0-6: 进入线程前再次检查取消
            if _is_cancelled(cancel_token):
                return ToolResult(success=False, output="", error="操作已取消")

            # v2.2.1 P3: CJK 输入支持 — pyautogui.typewrite 仅支持 ASCII,
            # 非 ASCII 字符(中/日/韩等)需通过剪贴板粘贴
            has_non_ascii = any(ord(c) > 127 for c in text)

            if has_non_ascii:
                # CJK 字符用剪贴板粘贴
                try:
                    import pyperclip  # type: ignore
                except ImportError:
                    return ToolResult(
                        success=False,
                        output="",
                        error="pyperclip 未安装,无法输入 CJK 字符。请运行 pip install pyperclip",
                    )
                # v2.3.0 Phase 3-A1: pyperclip + hotkey 是同步阻塞,包入 to_thread
                import sys
                if sys.platform == "darwin":
                    await asyncio.to_thread(self._paste_cjk, pa, pyperclip, text, "command", "v")
                else:
                    await asyncio.to_thread(self._paste_cjk, pa, pyperclip, text, "ctrl", "v")
                return ToolResult(
                    success=True,
                    output=f"已通过剪贴板输入文本 (含 CJK, {len(text)} 字符)",
                )

            # ASCII 字符直接 typewrite (interval>0 时会阻塞,放线程)
            await asyncio.to_thread(pa.typewrite, text, interval=interval)
            return ToolResult(
                success=True,
                output=f"已输入文本: {text[:50]}{'...' if len(text) > 50 else ''}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"输入失败: {exc}")

    @staticmethod
    def _paste_cjk(pa_module, pyperclip_module, text: str, *hotkey_args) -> None:
        """同步: CJK 文本通过剪贴板粘贴。在线程中执行避免阻塞事件循环。"""
        pyperclip_module.copy(text)
        pa_module.hotkey(*hotkey_args)


@register_tool("computer_get_a11y_tree")
class ComputerGetA11yTreeTool(BaseTool):
    name = "computer_get_a11y_tree"
    description = (
        "Get the accessibility (a11y) tree of the current desktop. "
        "Returns UI elements with their properties (name, role, bounds). "
        "Windows-only: uses UI Automation API. On other platforms returns error."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_depth": {
                "type": "integer",
                "description": "Maximum tree depth to traverse",
                "default": 5,
            },
        },
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"max_depth"}

    async def execute(self, max_depth: int = 5, **kwargs) -> ToolResult:
        # v2.3.1 P0-6: 协作式取消
        cancel_token = kwargs.get("cancel_token")
        if _is_cancelled(cancel_token):
            return ToolResult(success=False, output="", error="操作已取消")
        try:
            import uiautomation as ua  # type: ignore
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="uiautomation 未安装 (Windows 专用). 请运行 pip install uiautomation",
            )

        try:
            # v2.3.1 P0-6: 进入线程前再次检查取消
            if _is_cancelled(cancel_token):
                return ToolResult(success=False, output="", error="操作已取消")
            # v2.3.0 Phase 3-A1: uiautomation 遍历是同步阻塞 (且可能很慢),
            # 包入 asyncio.to_thread 避免阻塞事件循环
            # v2.3.1 P0-6: cancel_token 传入线程, _walk_a11y 栈循环中检查
            output_text = await asyncio.to_thread(
                self._build_a11y_output, ua, max_depth, cancel_token
            )
            # 线程返回后若已取消, 标记为取消 (避免使用部分结果误导 LLM)
            if _is_cancelled(cancel_token):
                return ToolResult(success=False, output="", error="操作已取消 (无障碍树遍历被中断)")
            return ToolResult(success=True, output=output_text)
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"获取无障碍树失败: {exc}")

    def _build_a11y_output(self, ua_module, max_depth: int, cancel_token=None) -> str:
        """同步: 获取根控件 + 遍历 + 序列化。在线程中执行避免阻塞事件循环。"""
        import json
        root = ua_module.GetRootControl()
        tree = self._walk_a11y(root, depth=0, max_depth=max_depth, cancel_token=cancel_token)
        return f"无障碍树 (深度 {max_depth}):\n{json.dumps(tree, ensure_ascii=False, indent=2)[:2000]}"

    @staticmethod
    def _walk_a11y(control, depth: int, max_depth: int, cancel_token=None) -> dict:
        """v2.2.1 P2: 迭代式遍历无障碍树,用栈替代递归,防止深层 UI 树栈溢出。

        v2.3.1 P0-6: 栈循环中检查 cancel_token, 协作式退出耗时遍历。

        返回结构与原递归实现一致: 嵌套 dict 树,节点含
        name/control_type/class_name/depth/children (仅当有子节点时)。
        """
        # 根节点
        root_node = {
            "name": control.Name or "",
            "control_type": control.ControlTypeName if hasattr(control, "ControlTypeName") else "",
            "class_name": control.ClassName if hasattr(control, "ControlTypeName") else "",
            "depth": depth,
        }
        # 栈元素: (control, parent_node, node_depth) — 用栈替代递归
        stack: list[tuple] = [(control, root_node, depth)]
        while stack:
            # v2.3.1 P0-6: 协作式取消 — 在每次栈迭代前检查
            if _is_cancelled(cancel_token):
                break
            ctrl, node, cur_depth = stack.pop()
            if cur_depth >= max_depth:
                continue
            try:
                child_list = list(ctrl.GetChildren())
            except Exception:
                child_list = []
            children = []
            for child in child_list:
                child_node = {
                    "name": child.Name or "",
                    "control_type": child.ControlTypeName if hasattr(child, "ControlTypeName") else "",
                    "class_name": child.ClassName if hasattr(child, "ControlTypeName") else "",
                    "depth": cur_depth + 1,
                }
                children.append(child_node)
                stack.append((child, child_node, cur_depth + 1))
            if children:
                node["children"] = children
        return root_node
