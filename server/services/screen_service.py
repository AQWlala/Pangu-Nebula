"""实验性服务 — 当前为 stub，暂不可用"""

from __future__ import annotations

from typing import Any


# stub 模式返回的固定结构
_STUB_RESPONSE: dict[str, Any] = {
    "ok": False,
    "error": "实验性服务，暂不可用",
    "code": 501,
}


class ScreenService:
    """屏幕感知服务（实验性 stub）

    当前为 stub，所有方法返回 501 错误。
    后续将实现截图 + OCR 文本识别。
    """

    def __init__(self) -> None:
        pass

    # ===== 手动截图 =====

    def capture_screen(self, monitor: int = 1, ocr: bool = True) -> dict[str, Any]:
        """手动截图（stub，暂不可用）"""
        return dict(_STUB_RESPONSE)

    # ===== 定时截图 =====

    def start_capture(self, config: Any = None) -> bool:
        """启动定时截图（stub，暂不可用）"""
        return False

    def stop_capture(self) -> bool:
        """停止定时截图（stub，暂不可用）"""
        return False

    # ===== 查询 =====

    def get_screenshots(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取截图历史（stub，暂不可用）"""
        return []

    def get_ocr_results(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取 OCR 结果历史（stub，暂不可用）"""
        return []

    def get_status(self) -> dict[str, Any]:
        """获取屏幕感知状态（stub，暂不可用）"""
        return dict(_STUB_RESPONSE)


# 模块级单例
screen_service = ScreenService()
