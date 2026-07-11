"""多模态 API 端点 - 图片识别、语音识别、语音合成、视频分析"""

from fastapi import APIRouter, HTTPException

from ..services.asr_service import ASRService
from ..services.tts_service import TTSService
from ..services.video_service import VideoService
from ..services.vision_service import VisionService
from .models import ASRRequest, ImageAnalyzeRequest, TTSRequest, VideoAnalyzeRequest

router = APIRouter(prefix="/multimodal", tags=["multimodal"])

# 服务实例
_vision = VisionService()
_asr = ASRService()
_tts = TTSService()
_video = VideoService()


@router.get("")
async def get_multimodal():
    """获取多模态能力信息"""
    capabilities = {
        "image": {
            "name": "图片识别",
            "endpoint": "/multimodal/image",
            "method": "POST",
            "description": "基于多模态 LLM 的图片内容识别",
        },
        "asr": {
            "name": "语音识别 (ASR)",
            "endpoint": "/multimodal/asr",
            "method": "POST",
            "description": "语音转文字，支持 OpenAI Whisper API 和本地 whisper",
        },
        "tts": {
            "name": "语音合成 (TTS)",
            "endpoint": "/multimodal/tts",
            "method": "POST",
            "description": "文字转语音，支持 edge-tts 和 OpenAI TTS API",
        },
        "video": {
            "name": "视频分析",
            "endpoint": "/multimodal/video",
            "method": "POST",
            "description": "视频关键帧抽取 + 多模态分析",
        },
    }
    return {"ok": True, "data": {"capabilities": capabilities}, "error": None}


# 注意: 静态路径端点必须在动态路径之前定义
@router.post("/image")
async def analyze_image(body: ImageAnalyzeRequest):
    """图片识别端点"""
    try:
        result = await _vision.analyze_image(
            persona_id=body.persona_id,
            image_base64=body.image_base64,
            prompt=body.prompt,
            model_name=body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"图片识别失败: {exc}"},
        ) from exc

    return {"ok": True, "data": result, "error": None}


@router.post("/asr")
async def transcribe_audio(body: ASRRequest):
    """语音识别端点"""
    try:
        result = await _asr.transcribe(
            audio_base64=body.audio_base64,
            language=body.language,
            model_name=body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"语音识别失败: {exc}"},
        ) from exc

    return {"ok": True, "data": result, "error": None}


@router.post("/tts")
async def synthesize_speech(body: TTSRequest):
    """语音合成端点"""
    try:
        result = await _tts.synthesize(
            text=body.text,
            voice=body.voice,
            model_name=body.model_name,
            speed=body.speed,
            output_format=body.output_format,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"语音合成失败: {exc}"},
        ) from exc

    return {"ok": True, "data": result, "error": None}


@router.post("/video")
async def analyze_video(body: VideoAnalyzeRequest):
    """视频分析端点"""
    try:
        result = await _video.analyze_video(
            persona_id=body.persona_id,
            video_base64=body.video_base64,
            video_path=body.video_path,
            prompt=body.prompt,
            max_frames=body.max_frames,
            model_name=body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"视频分析失败: {exc}"},
        ) from exc

    return {"ok": True, "data": result, "error": None}
