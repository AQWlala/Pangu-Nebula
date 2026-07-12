"""OS 感知 API(Phase 7B)

端点总览(均返回统一格式 {"ok", "data", "error"}):
- GET  /os_sense                          — OS 感知功能总览(各模块状态)
- GET  /os_sense/clipboard/status         — 剪贴板状态
- POST /os_sense/clipboard/start          — 启动剪贴板监控(ClipboardWatcherConfig)
- POST /os_sense/clipboard/stop           — 停止剪贴板监控
- GET  /os_sense/clipboard/history        — 获取剪贴板历史(limit, content_type)
- DELETE /os_sense/clipboard/history      — 清空剪贴板历史
- GET  /os_sense/file-watcher/status      — 文件监控状态
- POST /os_sense/file-watcher/start       — 启动文件监控(FileWatcherConfig)
- POST /os_sense/file-watcher/stop        — 停止文件监控
- GET  /os_sense/file-watcher/events      — 获取文件事件(limit, path, event_type)
- GET  /os_sense/tray/status              — 托盘状态
- POST /os_sense/tray/start               — 启动托盘(TrayConfig)
- POST /os_sense/tray/stop                — 停止托盘
- POST /os_sense/tray/shortcuts           — 设置快捷键(ShortcutConfig)
- GET  /os_sense/screen/status            — 屏幕感知状态
- POST /os_sense/screen/capture           — 手动截图(ScreenCaptureRequest)
- POST /os_sense/screen/start             — 启动定时截图(ScreenCaptureConfig)
- POST /os_sense/screen/stop              — 停止定时截图
- GET  /os_sense/screen/screenshots       — 获取截图历史(limit)
- GET  /os_sense/screen/ocr-results       — 获取 OCR 结果(limit)

注意:所有静态路径在参数路径之前(本模块无参数路径)。
"""

from fastapi import APIRouter, HTTPException, Query

from ..api.models import (
    ClipboardWatcherConfig,
    FileWatcherConfig,
    ScreenCaptureConfig,
    ScreenCaptureRequest,
    ShortcutConfig,
    TrayConfig,
)
from ..services.clipboard_watcher import clipboard_watcher
from ..services.file_watcher import file_watcher
from ..services.screen_service import screen_service
from ..services.tray_service import tray_service

router = APIRouter(prefix="/os_sense", tags=["os_sense"])


# ===== 总览 =====


@router.get("", summary="OS 感知总览", description="获取 OS 感知功能总览(剪贴板、文件监控、托盘、屏幕感知各模块状态)")
async def get_os_sense_overview():
    """获取 OS 感知功能总览(返回各模块状态)"""
    data = {
        "clipboard": clipboard_watcher.get_status(),
        "file_watcher": file_watcher.get_status(),
        "tray": tray_service.get_status(),
        "screen": screen_service.get_status(),
    }
    return {"ok": True, "data": data, "error": None}


# ===== 剪贴板 =====


@router.get("/clipboard/status", summary="剪贴板状态", description="获取剪贴板监控的运行状态和库可用性")
async def get_clipboard_status():
    """获取剪贴板监控状态"""
    data = clipboard_watcher.get_status()
    return {"ok": True, "data": data, "error": None}


@router.post("/clipboard/start", summary="启动剪贴板监控", description="启动剪贴板监控(请求体: ClipboardWatcherConfig)")
async def start_clipboard_watcher(req: ClipboardWatcherConfig):
    """启动剪贴板监控(请求体: ClipboardWatcherConfig)"""
    if not clipboard_watcher.get_status().get("library_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "pyperclip/win32clipboard 库未安装",
            },
        )
    ok = clipboard_watcher.start(req)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "剪贴板监控启动失败(可能已运行或配置禁用)",
            },
        )
    return {"ok": True, "data": clipboard_watcher.get_status(), "error": None}


@router.post("/clipboard/stop", summary="停止剪贴板监控", description="停止剪贴板监控")
async def stop_clipboard_watcher():
    """停止剪贴板监控"""
    ok = clipboard_watcher.stop()
    return {"ok": True, "data": {"stopped": ok, "status": clipboard_watcher.get_status()}, "error": None}


@router.get("/clipboard/history", summary="剪贴板历史", description="获取剪贴板历史记录,支持按 content_type 过滤")
async def get_clipboard_history(
    limit: int = Query(100, ge=1, le=1000, description="最多返回条数"),
    content_type: str | None = Query(None, description="按 text/image 过滤"),
):
    """获取剪贴板历史(查询参数: limit, content_type)"""
    data = clipboard_watcher.get_history(limit=limit, content_type=content_type)
    return {"ok": True, "data": data, "error": None}


@router.delete("/clipboard/history", summary="清空剪贴板历史", description="清空所有剪贴板历史记录")
async def clear_clipboard_history():
    """清空剪贴板历史"""
    count = clipboard_watcher.clear_history()
    return {"ok": True, "data": {"cleared": count}, "error": None}


# ===== 文件监控 =====


@router.get("/file-watcher/status", summary="文件监控状态", description="获取文件监控的运行状态和库可用性")
async def get_file_watcher_status():
    """获取文件监控状态"""
    data = file_watcher.get_status()
    return {"ok": True, "data": data, "error": None}


@router.post("/file-watcher/start", summary="启动文件监控", description="启动文件监控(请求体: FileWatcherConfig)")
async def start_file_watcher(req: FileWatcherConfig):
    """启动文件监控(请求体: FileWatcherConfig)"""
    if not file_watcher.get_status().get("library_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "watchdog 库未安装",
            },
        )
    ok = file_watcher.start(req)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "文件监控启动失败(可能已运行、配置禁用或路径无效)",
            },
        )
    return {"ok": True, "data": file_watcher.get_status(), "error": None}


@router.post("/file-watcher/stop", summary="停止文件监控", description="停止文件监控")
async def stop_file_watcher():
    """停止文件监控"""
    ok = file_watcher.stop()
    return {"ok": True, "data": {"stopped": ok, "status": file_watcher.get_status()}, "error": None}


@router.get("/file-watcher/events", summary="文件事件列表", description="获取文件事件列表,支持按路径和事件类型过滤")
async def get_file_watcher_events(
    limit: int = Query(100, ge=1, le=1000, description="最多返回条数"),
    path: str | None = Query(None, description="按路径前缀过滤"),
    event_type: str | None = Query(
        None, description="按事件类型过滤(created/modified/deleted/moved)"
    ),
):
    """获取文件事件(查询参数: limit, path, event_type)"""
    data = file_watcher.get_events(limit=limit, path=path, event_type=event_type)
    return {"ok": True, "data": data, "error": None}


# ===== 系统托盘 =====


@router.get("/tray/status", summary="托盘状态", description="获取系统托盘的运行状态和库可用性")
async def get_tray_status():
    """获取托盘状态"""
    data = tray_service.get_status()
    return {"ok": True, "data": data, "error": None}


@router.post("/tray/start", summary="启动托盘", description="启动系统托盘(请求体: TrayConfig)")
async def start_tray(req: TrayConfig):
    """启动托盘(请求体: TrayConfig)"""
    if not tray_service.get_status().get("tray_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "pystray/Pillow 库未安装",
            },
        )
    ok = tray_service.start_tray(req)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "托盘启动失败(可能已运行或配置禁用)",
            },
        )
    return {"ok": True, "data": tray_service.get_status(), "error": None}


@router.post("/tray/stop", summary="停止托盘", description="停止系统托盘")
async def stop_tray():
    """停止托盘"""
    ok = tray_service.stop_tray()
    return {"ok": True, "data": {"stopped": ok, "status": tray_service.get_status()}, "error": None}


@router.post("/tray/shortcuts", summary="设置快捷键", description="设置全局快捷键(请求体: ShortcutConfig,enabled=False 时仅停止)")
async def set_shortcuts(req: ShortcutConfig):
    """设置快捷键(请求体: ShortcutConfig)

    - 如果 shortcuts 已运行,会先停止再以新配置重启
    - 如果 shortcuts.enabled=False,仅停止
    """
    if not tray_service.get_status().get("shortcuts_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "keyboard 库未安装",
            },
        )
    # 先停止现有快捷键
    tray_service.stop_shortcuts()
    ok = True
    if req.enabled:
        ok = tray_service.start_shortcuts(req)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "data": None,
                    "error": "快捷键启动失败(可能已运行或注册失败)",
                },
            )
    return {"ok": True, "data": tray_service.get_status(), "error": None}


# ===== 屏幕感知 =====


@router.get("/screen/status", summary="屏幕感知状态", description="获取屏幕感知服务的运行状态和库可用性")
async def get_screen_status():
    """获取屏幕感知状态"""
    data = screen_service.get_status()
    return {"ok": True, "data": data, "error": None}


@router.post("/screen/capture", summary="手动截图", description="手动截图(请求体: ScreenCaptureRequest),可附 OCR")
async def capture_screen(req: ScreenCaptureRequest):
    """手动截图(请求体: ScreenCaptureRequest)"""
    if not screen_service.get_status().get("library_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "Pillow(PIL) 库未安装",
            },
        )
    result = screen_service.capture_screen(monitor=req.monitor, ocr=req.ocr)
    if not isinstance(result, dict) or "error" in result:
        error_msg = result.get("error", "截图失败") if isinstance(result, dict) else "截图失败"
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": error_msg},
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/screen/start", summary="启动定时截图", description="启动定时截图(请求体: ScreenCaptureConfig)")
async def start_screen_capture(req: ScreenCaptureConfig):
    """启动定时截图(请求体: ScreenCaptureConfig)"""
    if not screen_service.get_status().get("library_available"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "Pillow(PIL) 库未安装",
            },
        )
    ok = screen_service.start_capture(req)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "data": None,
                "error": "定时截图启动失败(可能已运行或配置禁用)",
            },
        )
    return {"ok": True, "data": screen_service.get_status(), "error": None}


@router.post("/screen/stop", summary="停止定时截图", description="停止定时截图任务")
async def stop_screen_capture():
    """停止定时截图"""
    ok = screen_service.stop_capture()
    return {"ok": True, "data": {"stopped": ok, "status": screen_service.get_status()}, "error": None}


@router.get("/screen/screenshots", summary="截图历史", description="获取截图历史记录")
async def get_screenshots(
    limit: int = Query(10, ge=1, le=100, description="最多返回条数"),
):
    """获取截图历史(查询参数: limit)"""
    data = screen_service.get_screenshots(limit=limit)
    return {"ok": True, "data": data, "error": None}


@router.get("/screen/ocr-results", summary="OCR 结果", description="获取 OCR 识别结果历史")
async def get_ocr_results(
    limit: int = Query(10, ge=1, le=100, description="最多返回条数"),
):
    """获取 OCR 结果(查询参数: limit)"""
    data = screen_service.get_ocr_results(limit=limit)
    return {"ok": True, "data": data, "error": None}
