"""屏幕实时感知服务(Phase 7B)

提供手动截图和定时截图功能,可选 OCR 文本识别。
出于隐私考虑,定时截图默认关闭,截图默认不存储。

依赖(均为可选,缺失时返回错误而不是崩溃):
- PIL(Pillow): ImageGrab 截图
- pytesseract: OCR 文本识别(需要 Tesseract OCR 引擎)
"""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import datetime
from typing import Any

from ..api.models import ScreenCaptureConfig

# 可选依赖:Pillow(截图)
try:
    from PIL import ImageGrab, Image  # type: ignore

    _HAS_PIL = True
except ImportError:
    ImageGrab = None  # type: ignore
    Image = None  # type: ignore
    _HAS_PIL = False

# 可选依赖:pytesseract(OCR)
try:
    import pytesseract  # type: ignore

    _HAS_PYTESSERACT = True
except ImportError:
    pytesseract = None  # type: ignore
    _HAS_PYTESSERACT = False


class ScreenService:
    """屏幕感知服务

    - capture_screen: 手动截图,可选 OCR
    - start_capture / stop_capture: 定时截图循环
    - 出于隐私考虑,默认 store_screenshots=False,只保存 OCR 文本
    """

    def __init__(self) -> None:
        self.config: ScreenCaptureConfig = ScreenCaptureConfig()
        self._task: asyncio.Task | None = None
        self.screenshots: list[dict[str, Any]] = []  # 截图历史
        self.ocr_results: list[dict[str, Any]] = []  # OCR 结果历史
        self._running: bool = False

    # ===== 手动截图 =====

    def capture_screen(self, monitor: int = 1, ocr: bool = True) -> dict[str, Any]:
        """手动截图

        - 使用 Pillow ImageGrab 截图
        - 如果 ocr=True,使用 pytesseract 进行 OCR
        - 返回 {"image_base64": "...", "ocr_text": "...", "timestamp": "..."}
        - 失败时返回 {"error": "..."}
        """
        if not _HAS_PIL:
            return {"error": "Pillow(PIL) 库未安装"}

        # ImageGrab 截图(monitor 参数:1=主屏)
        # Windows 下 all_screens=True 时 monitor 索引有效
        try:
            if monitor and monitor > 1:
                # 多显示器:使用 all_screens
                screens = ImageGrab.grab(all_screens=True)  # type: ignore[union-attr]
                # 注意:all_screens=True 返回单个 Image,这里仅做兼容
                image = screens
            else:
                image = ImageGrab.grab()  # type: ignore[union-attr]
        except Exception as exc:
            return {"error": f"截图失败: {exc}"}

        # 转 base64
        try:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        except Exception as exc:
            return {"error": f"图片编码失败: {exc}"}

        # OCR
        ocr_text = ""
        if ocr:
            if not _HAS_PYTESSERACT:
                ocr_text = "[OCR 不可用: pytesseract 库未安装]"
            else:
                try:
                    ocr_text = pytesseract.image_to_string(image, lang="chi_sim+eng")  # type: ignore[union-attr]
                except Exception as exc:
                    ocr_text = f"[OCR 失败: {exc}]"

        timestamp = datetime.now().isoformat()
        return {
            "image_base64": image_base64,
            "ocr_text": ocr_text,
            "timestamp": timestamp,
        }

    # ===== 定时截图 =====

    def start_capture(self, config: ScreenCaptureConfig | None = None) -> bool:
        """启动定时截图

        - 保存 config
        - 创建 asyncio.Task 执行 _capture_loop
        - 返回是否成功启动
        """
        if not _HAS_PIL:
            return False
        if self._running:
            return True
        if config is not None:
            self.config = config
        if not self.config.enabled:
            return False
        self._running = True
        try:
            self._task = asyncio.ensure_future(self._capture_loop())
        except RuntimeError:
            self._running = False
            return False
        return True

    def stop_capture(self) -> bool:
        """停止定时截图

        - 取消 asyncio.Task
        - 返回是否成功停止
        """
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        return True

    async def _capture_loop(self) -> None:
        """定时截图循环

        - 按 config.interval_seconds 截图
        - 如果 ocr_enabled,进行 OCR
        - 如果 store_screenshots,保存到 screenshots 列表(不超过 max_screenshots)
        - 否则只保存 OCR 文本
        """
        interval = max(1.0, float(self.config.interval_seconds))
        while self._running:
            try:
                await self._capture_once()
            except asyncio.CancelledError:
                break
            except Exception:
                # 任何异常都不应中断循环
                pass
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _capture_once(self) -> None:
        """执行一次定时截图

        在线程池中执行同步的 ImageGrab 操作,避免阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self.capture_screen, 1, bool(self.config.ocr_enabled)
        )

        if not isinstance(result, dict) or "error" in result:
            # 截图失败,跳过本次
            return

        timestamp = result.get("timestamp", datetime.now().isoformat())
        ocr_text = result.get("ocr_text", "")

        # 保存 OCR 结果(始终保存,体积小)
        if self.config.ocr_enabled and ocr_text:
            ocr_record = {
                "ocr_text": ocr_text,
                "timestamp": timestamp,
            }
            self.ocr_results.append(ocr_record)
            # 限制 OCR 历史大小
            if len(self.ocr_results) > 100:
                self.ocr_results = self.ocr_results[-100:]

        # 保存截图(仅在 store_screenshots=True 时)
        if self.config.store_screenshots:
            screenshot_record = {
                "image_base64": result.get("image_base64", ""),
                "ocr_text": ocr_text,
                "timestamp": timestamp,
            }
            self.screenshots.append(screenshot_record)
            # 按 max_screenshots 截断
            max_screenshots = max(1, int(self.config.max_screenshots))
            if len(self.screenshots) > max_screenshots:
                self.screenshots = self.screenshots[-max_screenshots:]

    # ===== 查询 =====

    def get_screenshots(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取截图历史(从最新开始)"""
        items = list(reversed(self.screenshots))
        if limit > 0:
            items = items[:limit]
        return items

    def get_ocr_results(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取 OCR 结果历史(从最新开始)"""
        items = list(reversed(self.ocr_results))
        if limit > 0:
            items = items[:limit]
        return items

    def get_status(self) -> dict[str, Any]:
        """获取屏幕感知状态"""
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "interval_seconds": self.config.interval_seconds,
            "ocr_enabled": self.config.ocr_enabled,
            "store_screenshots": self.config.store_screenshots,
            "max_screenshots": self.config.max_screenshots,
            "screenshots_count": len(self.screenshots),
            "ocr_results_count": len(self.ocr_results),
            "pil_available": _HAS_PIL,
            "pytesseract_available": _HAS_PYTESSERACT,
            "library_available": _HAS_PIL,
        }


# 模块级单例
screen_service = ScreenService()
