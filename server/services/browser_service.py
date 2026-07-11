"""浏览器自动化服务(Phase 7C)

基于 Playwright Python 实现浏览器自动化,支持页面导航、元素操作、截图等。
融合来源: NomiFun 的 Browser Use(nomi-browser),但用 Playwright Python 替代自建 CDP。

依赖(可选,缺失时返回错误而不是崩溃):
- playwright: 浏览器自动化引擎
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import Any

# 可选依赖:playwright
try:
    from playwright.async_api import async_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None  # type: ignore
    _HAS_PLAYWRIGHT = False


class BrowserService:
    """浏览器自动化服务

    使用 Playwright Python 控制 Chromium 浏览器,支持:
    - 启动/关闭浏览器会话
    - 页面导航
    - 元素操作(click/type/scroll)
    - 截图(返回 base64)
    - 执行 JS 脚本
    - 等待选择器
    - 多标签页管理

    所有操作通过 asyncio.Lock 串行执行(Playwright 不支持并发操作同一页面)。
    """

    def __init__(self) -> None:
        self.playwright: Any = None  # Playwright 实例
        self.browser: Any = None  # 浏览器实例
        self.context: Any = None  # 浏览器上下文
        self.page: Any = None  # 当前页面
        self._lock = asyncio.Lock()  # 异步锁(确保操作串行)
        self._session_id: str | None = None  # 当前会话 ID

    def _not_installed_error(self) -> dict:
        """playwright 未安装时的统一错误响应"""
        return {
            "ok": False,
            "data": None,
            "error": "playwright 未安装,请运行 pip install playwright && playwright install chromium",
        }

    async def start_session(
        self, headless: bool = True, viewport_width: int = 1280, viewport_height: int = 720
    ) -> dict:
        """启动浏览器会话

        启动 Playwright,打开 Chromium 浏览器,创建上下文和页面。
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        async with self._lock:
            # 若已有会话,先关闭
            if self.browser is not None:
                await self._close_internal()

            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=headless)
                self.context = await self.browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height}
                )
                self.page = await self.context.new_page()
                self._session_id = uuid.uuid4().hex
                return {
                    "ok": True,
                    "data": {
                        "session_id": self._session_id,
                        "headless": headless,
                        "viewport": {"width": viewport_width, "height": viewport_height},
                    },
                    "error": None,
                }
            except Exception as e:
                # 启动失败时清理资源
                await self._close_internal()
                return {"ok": False, "data": None, "error": f"启动浏览器会话失败: {e}"}

    async def _close_internal(self) -> None:
        """内部清理方法(不加锁,由调用方负责加锁)"""
        # 按相反顺序关闭
        if self.page is not None:
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None
        if self.context is not None:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
        self._session_id = None

    async def close_session(self) -> bool:
        """关闭浏览器会话

        关闭 page/context/browser,停止 playwright。
        返回是否成功关闭。
        """
        if not _HAS_PLAYWRIGHT:
            return False

        async with self._lock:
            if self.browser is None and self.playwright is None:
                return True
            await self._close_internal()
            return True

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict:
        """导航到指定 URL

        使用 page.goto 进行页面跳转,返回页面信息。
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        async with self._lock:
            if self.page is None:
                return {"ok": False, "data": None, "error": "浏览器会话未启动,请先调用 /browser/session"}
            try:
                response = await self.page.goto(url, wait_until=wait_until)
                status = response.status if response is not None else None
                title = await self.page.title()
                return {
                    "ok": True,
                    "data": {
                        "url": self.page.url,
                        "title": title,
                        "status": status,
                    },
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"导航失败: {e}"}

    async def execute_action(
        self,
        action: str,
        selector: str | None = None,
        text: str | None = None,
        script: str | None = None,
        timeout: int = 30000,
    ) -> dict:
        """执行浏览器操作

        支持的 action:
        - click: 点击元素(selector 必填)
        - type: 在输入框填入文本(selector、text 必填)
        - screenshot: 截图并返回 base64
        - scroll: 向下滚动 500px
        - evaluate: 执行 JS 脚本(script 必填)
        - wait_for_selector: 等待元素出现(selector 必填)
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        async with self._lock:
            if self.page is None:
                return {"ok": False, "data": None, "error": "浏览器会话未启动,请先调用 /browser/session"}

            try:
                if action == "click":
                    if not selector:
                        return {"ok": False, "data": None, "error": "click 操作需要 selector 参数"}
                    await self.page.click(selector, timeout=timeout)
                    return {"ok": True, "data": {"action": "click", "selector": selector}, "error": None}

                elif action == "type":
                    if not selector:
                        return {"ok": False, "data": None, "error": "type 操作需要 selector 参数"}
                    if text is None:
                        return {"ok": False, "data": None, "error": "type 操作需要 text 参数"}
                    await self.page.fill(selector, text, timeout=timeout)
                    return {
                        "ok": True,
                        "data": {"action": "type", "selector": selector, "text": text},
                        "error": None,
                    }

                elif action == "screenshot":
                    screenshot_bytes = await self.page.screenshot()
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                    return {
                        "ok": True,
                        "data": {"action": "screenshot", "image_base64": screenshot_b64},
                        "error": None,
                    }

                elif action == "scroll":
                    await self.page.evaluate("window.scrollBy(0, 500)")
                    return {"ok": True, "data": {"action": "scroll", "delta_y": 500}, "error": None}

                elif action == "evaluate":
                    if not script:
                        return {"ok": False, "data": None, "error": "evaluate 操作需要 script 参数"}
                    result = await self.page.evaluate(script)
                    return {
                        "ok": True,
                        "data": {"action": "evaluate", "result": result},
                        "error": None,
                    }

                elif action == "wait_for_selector":
                    if not selector:
                        return {
                            "ok": False,
                            "data": None,
                            "error": "wait_for_selector 操作需要 selector 参数",
                        }
                    await self.page.wait_for_selector(selector, timeout=timeout)
                    return {
                        "ok": True,
                        "data": {"action": "wait_for_selector", "selector": selector},
                        "error": None,
                    }

                else:
                    return {"ok": False, "data": None, "error": f"不支持的操作: {action}"}
            except Exception as e:
                return {"ok": False, "data": None, "error": f"执行操作 {action} 失败: {e}"}

    async def get_page_info(self) -> dict:
        """获取当前页面信息

        返回当前页面的 URL、标题和视口大小。
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        async with self._lock:
            if self.page is None:
                return {"ok": False, "data": None, "error": "浏览器会话未启动,请先调用 /browser/session"}
            try:
                title = await self.page.title()
                viewport = self.page.viewport_size or {}
                return {
                    "ok": True,
                    "data": {
                        "url": self.page.url,
                        "title": title,
                        "viewport": {
                            "width": viewport.get("width"),
                            "height": viewport.get("height"),
                        },
                    },
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"获取页面信息失败: {e}"}

    async def get_status(self) -> dict:
        """获取浏览器状态

        返回浏览器是否激活、当前 URL 和标题。
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        # 状态查询无需长时间持锁,但仍需读取一致状态
        async with self._lock:
            if self.browser is None or self.page is None:
                return {
                    "ok": True,
                    "data": {"active": False, "url": None, "title": None},
                    "error": None,
                }
            try:
                title = await self.page.title()
                return {
                    "ok": True,
                    "data": {"active": True, "url": self.page.url, "title": title},
                    "error": None,
                }
            except Exception as e:
                return {
                    "ok": True,
                    "data": {"active": True, "url": None, "title": None},
                    "error": f"读取状态失败: {e}",
                }

    async def list_tabs(self) -> dict:
        """列出所有标签页

        返回当前浏览器上下文中所有标签页的信息。
        """
        if not _HAS_PLAYWRIGHT:
            return self._not_installed_error()

        async with self._lock:
            if self.context is None:
                return {"ok": False, "data": None, "error": "浏览器会话未启动,请先调用 /browser/session"}
            try:
                pages = self.context.pages
                tabs = []
                for idx, p in enumerate(pages):
                    try:
                        title = await p.title()
                    except Exception:
                        title = None
                    tabs.append(
                        {
                            "index": idx,
                            "url": p.url,
                            "title": title,
                            "is_current": p == self.page,
                        }
                    )
                return {"ok": True, "data": {"tabs": tabs, "count": len(tabs)}, "error": None}
            except Exception as e:
                return {"ok": False, "data": None, "error": f"列出标签页失败: {e}"}


# 模块级单例
browser_service = BrowserService()
