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
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
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
            return ToolResult(
                success=True,
                output=f"截图成功 (JPEG {img.size[0]}x{img.size[1]}, base64 长度: {len(img_b64)})。前 200 字符: {img_b64[:200]}",
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
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"x", "y", "button"}

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
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"text", "interval"}

    async def execute(self, text: str, interval: float = 0.0, **kwargs) -> ToolResult:
        ok, err = _check_dependencies()
        if not ok:
            return ToolResult(success=False, output="", error=err)

        # v2.2.1 F7: 危险文本黑名单检测
        safe, reason = _check_text_safety(text)
        if not safe:
            return ToolResult(success=False, output="", error=reason)

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
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"max_depth"}

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
