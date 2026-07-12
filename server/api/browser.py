"""浏览器自动化 API 端点(Phase 7C)

基于 Playwright Python 的浏览器自动化接口。
所有端点返回统一格式 {"ok", "data", "error"}。
"""

from fastapi import APIRouter, HTTPException

from ..services.browser_service import browser_service
from .models import BrowserActionRequest, BrowserNavigateRequest, BrowserSessionRequest

router = APIRouter(prefix="/browser", tags=["browser"])


@router.get("", summary="浏览器状态", description="获取浏览器自动化服务的状态(是否已启动会话、当前页面等)")
async def get_browser_status():
    """获取浏览器状态(静态路由在前)"""
    result = await browser_service.get_status()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/page-info")
async def get_page_info():
    """获取当前页面信息(静态路由在前)"""
    result = await browser_service.get_page_info()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/tabs")
async def list_tabs():
    """列出所有标签页(静态路由在前)"""
    result = await browser_service.list_tabs()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/session", summary="启动浏览器会话", description="启动一个新的浏览器会话,可指定 headless 模式和视口尺寸")
async def start_session(req: BrowserSessionRequest):
    """启动浏览器会话"""
    result = await browser_service.start_session(
        headless=req.headless,
        viewport_width=req.viewport_width,
        viewport_height=req.viewport_height,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.delete("/session")
async def close_session():
    """关闭浏览器会话"""
    closed = await browser_service.close_session()
    if not closed:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "playwright 未安装,请运行 pip install playwright && playwright install chromium",
            },
        )
    return {"ok": True, "data": {"closed": True}, "error": None}


@router.post("/navigate", summary="导航到 URL", description="导航到指定 URL,可设置等待策略(load/domcontentloaded/networkidle)")
async def navigate(req: BrowserNavigateRequest):
    """导航到指定 URL"""
    result = await browser_service.navigate(url=req.url, wait_until=req.wait_until)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/action", summary="执行浏览器操作", description="执行浏览器操作: click/type/screenshot/scroll/evaluate/wait_for_selector")
async def execute_action(req: BrowserActionRequest):
    """执行浏览器操作(click/type/screenshot/scroll/evaluate/wait_for_selector)"""
    result = await browser_service.execute_action(
        action=req.action,
        selector=req.selector,
        text=req.text,
        script=req.script,
        timeout=req.timeout,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result
