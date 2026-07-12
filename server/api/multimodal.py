"""多模态 API 端点 - 语音合成、语音识别、图片识别、视频/屏幕(stub)"""

import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.asr_service import ASRService
from ..services.tts_service import TTSService
from ..services.vision_service import VisionService

router = APIRouter(prefix="/multimodal", tags=["multimodal"])

# 服务实例
_vision = VisionService()
_asr = ASRService()
_tts = TTSService()


# ===== 请求模型 =====


class TTSRequest(BaseModel):
    """语音合成请求"""

    text: str
    voice: str = "zh-CN-XiaoxiaoNeural"


class ASRRequest(BaseModel):
    """语音识别请求"""

    audio_base64: str  # base64 编码的音频
    language: str = "zh"  # zh/en/auto


class VisionRequest(BaseModel):
    """图片识别请求"""

    image_base64: str  # base64 编码的图片
    prompt: str = ""


# ===== 端点 =====


@router.get("")
async def get_multimodal():
    """获取多模态能力信息"""
    capabilities = {
        "tts": {
            "name": "语音合成 (TTS)",
            "endpoint": "/multimodal/tts",
            "method": "POST",
            "description": "文字转语音，edge-tts 真实合成 / mock 降级",
        },
        "asr": {
            "name": "语音识别 (ASR)",
            "endpoint": "/multimodal/asr",
            "method": "POST",
            "description": "语音转文字，OpenAI Whisper API / mock 降级",
        },
        "vision": {
            "name": "图片识别 (Vision)",
            "endpoint": "/multimodal/vision",
            "method": "POST",
            "description": "图片内容识别，OpenAI Vision API / mock 降级",
        },
        "video": {
            "name": "视频分析 (实验性)",
            "endpoint": "/multimodal/video",
            "method": "POST",
            "description": "实验性服务，暂不可用 (501)",
        },
        "screen": {
            "name": "屏幕感知 (实验性)",
            "endpoint": "/multimodal/screen",
            "method": "POST",
            "description": "实验性服务，暂不可用 (501)",
        },
    }
    return {"ok": True, "data": {"capabilities": capabilities}, "error": None}


def _strip_data_uri(data: str) -> str:
    """去除 data URI 前缀"""
    if data.startswith("data:") and "," in data:
        return data.split(",", 1)[1]
    return data


@router.post("/tts")
async def synthesize_speech(body: TTSRequest):
    """语音合成端点 - 调用 tts_service.synthesize"""
    try:
        audio_bytes = await _tts.synthesize(text=body.text, voice=body.voice)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"语音合成失败: {exc}"},
        ) from exc

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    return {
        "ok": True,
        "data": {
            "audio_base64": audio_b64,
            "format": "mp3",
        },
        "error": None,
    }


@router.post("/asr")
async def transcribe_audio(body: ASRRequest):
    """语音识别端点 - 调用 asr_service.transcribe"""
    try:
        raw_base64 = _strip_data_uri(body.audio_base64)
        audio_bytes = base64.b64decode(raw_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": f"无效的音频数据: {exc}"},
        ) from exc

    try:
        text = await _asr.transcribe(audio_data=audio_bytes, language=body.language)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"语音识别失败: {exc}"},
        ) from exc

    return {"ok": True, "data": {"text": text, "language": body.language}, "error": None}


@router.post("/vision")
async def describe_image(body: VisionRequest):
    """图片识别端点 - 调用 vision_service.describe_image"""
    try:
        raw_base64 = _strip_data_uri(body.image_base64)
        image_bytes = base64.b64decode(raw_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": f"无效的图片数据: {exc}"},
        ) from exc

    try:
        description = await _vision.describe_image(
            image_data=image_bytes, prompt=body.prompt
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"图片识别失败: {exc}"},
        ) from exc

    return {"ok": True, "data": {"description": description}, "error": None}


@router.post("/video")
async def analyze_video():
    """视频分析端点 - 实验性服务，暂不可用"""
    raise HTTPException(
        status_code=501,
        detail={"ok": False, "data": None, "error": "实验性服务，暂不可用"},
    )


@router.post("/screen")
async def capture_screen():
    """屏幕感知端点 - 实验性服务，暂不可用"""
    raise HTTPException(
        status_code=501,
        detail={"ok": False, "data": None, "error": "实验性服务，暂不可用"},
    )
