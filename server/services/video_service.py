"""实验性服务 — 当前为 stub，暂不可用"""

from __future__ import annotations

from typing import Any


# stub 模式返回的固定结构
_STUB_RESPONSE: dict[str, Any] = {
    "ok": False,
    "error": "实验性服务，暂不可用",
    "code": 501,
}


class VideoService:
    """视频分析服务（实验性 stub）

    当前为 stub，所有方法返回 501 错误。
    后续将实现 ffmpeg 抽帧 + 多模态 LLM 分析。
    """

    def __init__(self) -> None:
        # 保留 vision 属性以兼容旧代码引用
        pass

    async def analyze_video(
        self,
        persona_id: int | None = None,
        video_base64: str | None = None,
        video_path: str | None = None,
        prompt: str = "请分析这个视频的内容",
        max_frames: int = 10,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """视频分析（stub，暂不可用）"""
        return dict(_STUB_RESPONSE)

    async def extract_frames(
        self, video_path: str, max_frames: int, output_dir: str
    ) -> list[str]:
        """抽取关键帧（stub，暂不可用）"""
        return []


# 模块级单例
video_service = VideoService()
