# server/tools/browser_tools.py
"""v2.2.0 Phase 5 — Browser Use 工具集

将 BrowserService (Playwright) 暴露为 LLM 可调用的工具:
- browser_navigate: 导航到 URL
- browser_screenshot: 截图返回 base64
- browser_click: 点击元素 (CSS selector)
- browser_type: 在输入框填入文本

所有工具需 persona.browser_use_enabled=True (由 ToolExecutor 权限矩阵拦截)。
会话管理: 首次调用时自动启动浏览器会话 (headless),后续调用复用。
"""
from __future__ import annotations

from .registry import BaseTool, ToolResult, register_tool


async def _ensure_session():
    """确保浏览器会话已启动,返回 (browser_service, error_dict)。

    若会话未启动,自动以 headless 模式启动。
    """
    from ..services.browser_service import browser_service

    status = await browser_service.get_status()
    if not status.get("data", {}).get("active"):
        start_result = await browser_service.start_session(headless=True)
        if not start_result.get("ok"):
            return None, start_result.get("error", "启动浏览器会话失败")
    return browser_service, None


@register_tool("browser_navigate")
class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = (
        "Navigate the browser to a URL. Auto-starts a headless browser session "
        "if none is active. Returns the page title and final URL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to navigate to"},
        },
        "required": ["url"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"url"}

    async def execute(self, url: str, **kwargs) -> ToolResult:
        # F8 安全修复: 在调用 browser_service.navigate 之前,
        # 用 ssrf_guard.validate_url_safe 校验 URL,防止 LLM 访问
        # 内网(192.168.x / 10.x / 127.x)或云元数据(169.254.169.254)。
        from ..services.ssrf_guard import ssrf_guard

        is_safe, reason = ssrf_guard.validate_url_safe(url)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"URL 被 SSRF 防护拒绝: {reason}",
            )
        svc, err = await _ensure_session()
        if svc is None:
            return ToolResult(success=False, output="", error=err)
        result = await svc.navigate(url)
        if result.get("ok"):
            data = result["data"]
            return ToolResult(
                success=True,
                output=f"已导航到: {data.get('title','')} — {data.get('url','')} (HTTP {data.get('status','')})",
            )
        return ToolResult(success=False, output="", error=result.get("error", "导航失败"))


@register_tool("browser_screenshot")
class BrowserScreenshotTool(BaseTool):
    name = "browser_screenshot"
    description = (
        "Take a screenshot of the current browser page. Returns base64-encoded PNG. "
        "Use after navigate/click/type to verify the page state."
    )
    parameters = {
        "type": "object",
        "properties": {},
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = set()

    async def execute(self, **kwargs) -> ToolResult:
        svc, err = await _ensure_session()
        if svc is None:
            return ToolResult(success=False, output="", error=err)
        result = await svc.execute_action(action="screenshot")
        if result.get("ok"):
            img_b64 = result["data"].get("image_base64", "")
            # 截图 base64 可能很长,返回前 200 字符作为预览 + 完整长度
            return ToolResult(
                success=True,
                output=f"截图成功 (base64 长度: {len(img_b64)})。前 200 字符: {img_b64[:200]}",
            )
        return ToolResult(success=False, output="", error=result.get("error", "截图失败"))


@register_tool("browser_click")
class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = (
        "Click an element on the current browser page identified by CSS selector. "
        "Example selectors: 'button#submit', 'input[name=q]', 'a[href=\"/about\"]'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector of the element to click",
            },
        },
        "required": ["selector"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"selector"}

    async def execute(self, selector: str, **kwargs) -> ToolResult:
        svc, err = await _ensure_session()
        if svc is None:
            return ToolResult(success=False, output="", error=err)
        result = await svc.execute_action(action="click", selector=selector)
        if result.get("ok"):
            return ToolResult(success=True, output=f"已点击元素: {selector}")
        return ToolResult(success=False, output="", error=result.get("error", "点击失败"))


@register_tool("browser_type")
class BrowserTypeTool(BaseTool):
    name = "browser_type"
    description = (
        "Type text into an input element on the current browser page. "
        "Identifies the element by CSS selector. Clears existing text before typing."
    )
    parameters = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector of the input element",
            },
            "text": {
                "type": "string",
                "description": "Text to type into the element",
            },
        },
        "required": ["selector", "text"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"selector", "text"}

    async def execute(self, selector: str, text: str, **kwargs) -> ToolResult:
        svc, err = await _ensure_session()
        if svc is None:
            return ToolResult(success=False, output="", error=err)
        result = await svc.execute_action(action="type", selector=selector, text=text)
        if result.get("ok"):
            return ToolResult(
                success=True,
                output=f"已在元素 {selector} 输入文本: {text[:50]}{'...' if len(text) > 50 else ''}",
            )
        return ToolResult(success=False, output="", error=result.get("error", "输入失败"))
