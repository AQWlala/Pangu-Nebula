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

所有工具需 persona.browser_use_enabled=True (由 ToolExecutor 权限矩阵拦截,
复用 browser_use_enabled 作为 "GUI 操作权限" 开关,避免新增 persona 字段)。

注意: 这些是 Rust computer_use 模块的 Python 兜底实现。
当 Rust 模块编译完成 (HAS_RUST=True) 时,应优先调用 Rust 实现。
"""
from __future__ import annotations

import base64
import io

from .registry import BaseTool, ToolResult, register_tool


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
        "Take a full-screen screenshot of the desktop. Returns base64-encoded PNG. "
        "Use to see the current screen state before clicking or typing."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs) -> ToolResult:
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            import pyautogui  # type: ignore

            # pyautogui.screenshot() 返回 PIL.Image
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return ToolResult(
                success=True,
                output=f"截图成功 (base64 长度: {len(img_b64)})。前 200 字符: {img_b64[:200]}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"截图失败: {exc}")


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

    async def execute(self, x: int, y: int, button: str = "left", **kwargs) -> ToolResult:
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            import pyautogui  # type: ignore

            pyautogui.click(x=x, y=y, button=button)
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

    async def execute(self, text: str, interval: float = 0.0, **kwargs) -> ToolResult:
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            import pyautogui  # type: ignore

            pyautogui.typewrite(text, interval=interval)
            return ToolResult(
                success=True,
                output=f"已输入文本: {text[:50]}{'...' if len(text) > 50 else ''}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"输入失败: {exc}")


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

    async def execute(self, max_depth: int = 5, **kwargs) -> ToolResult:
        try:
            import uiautomation as ua  # type: ignore
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="uiautomation 未安装 (Windows 专用). 请运行 pip install uiautomation",
            )

        try:
            root = ua.GetRootControl()
            tree = self._walk_a11y(root, depth=0, max_depth=max_depth)
            import json
            return ToolResult(
                success=True,
                output=f"无障碍树 (深度 {max_depth}):\n{json.dumps(tree, ensure_ascii=False, indent=2)[:2000]}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=f"获取无障碍树失败: {exc}")

    @staticmethod
    def _walk_a11y(control, depth: int, max_depth: int) -> dict:
        """递归遍历无障碍树,返回 dict 结构。"""
        import uiautomation as ua  # type: ignore

        node = {
            "name": control.Name or "",
            "control_type": control.ControlTypeName if hasattr(control, "ControlTypeName") else "",
            "class_name": control.ClassName if hasattr(control, "ClassName") else "",
            "depth": depth,
        }
        if depth < max_depth:
            children = []
            try:
                for child in control.GetChildren():
                    children.append(
                        ComputerGetA11yTreeTool._walk_a11y(child, depth + 1, max_depth)
                    )
            except Exception:
                pass
            if children:
                node["children"] = children
        return node
