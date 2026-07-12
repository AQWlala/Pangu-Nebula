"""多模态服务 mock 模式测试

测试 TTS / ASR / Vision 服务的双模式行为 (mock 或真实)，
以及 Video / Screen 服务的 stub 响应 (501)。
"""

import base64

import pytest

from server.services.asr_service import ASRService, transcribe as asr_transcribe
from server.services.screen_service import ScreenService
from server.services.tts_service import TTSService, synthesize as tts_synthesize
from server.services.video_service import VideoService
from server.services.vision_service import (
    VisionService,
    describe_image as vision_describe_image,
)


# ===== TTS =====


@pytest.mark.asyncio
async def test_tts_synthesize_returns_bytes():
    """TTS synthesize 应返回 bytes (mock 或真实)"""
    audio = await tts_synthesize("你好世界")
    assert isinstance(audio, bytes)
    assert len(audio) > 0


@pytest.mark.asyncio
async def test_tts_service_class_returns_bytes():
    """TTSService.synthesize 应返回 bytes"""
    service = TTSService()
    audio = await service.synthesize("测试文本")
    assert isinstance(audio, bytes)
    assert len(audio) > 0


@pytest.mark.asyncio
async def test_tts_mock_mode_returns_mock_data():
    """mock 模式下 (无 edge-tts 或调用失败) 返回固定 mock 字节"""
    # 无 edge-tts 时返回 mock；有 edge-tts 时返回真实音频
    # 两种情况都是 bytes，至少验证类型
    audio = await tts_synthesize("")
    assert isinstance(audio, bytes)
    # 空文本必走 mock 分支
    assert audio == b"mock_tts_audio_data"


# ===== ASR =====


@pytest.mark.asyncio
async def test_asr_transcribe_returns_str():
    """ASR transcribe 应返回 str (mock 或真实)"""
    text = await asr_transcribe(b"fake audio data")
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_asr_service_class_returns_str():
    """ASRService.transcribe 应返回 str"""
    service = ASRService()
    text = await service.transcribe(b"fake audio data")
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_asr_empty_audio_returns_mock():
    """空音频数据应返回 mock 文本"""
    text = await asr_transcribe(b"")
    assert isinstance(text, str)
    assert text == "[mock ASR] transcription placeholder"


# ===== Vision =====


@pytest.mark.asyncio
async def test_vision_describe_image_returns_str():
    """Vision describe_image 应返回 str (mock 或真实)"""
    # 1x1 PNG 透明图片
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    desc = await vision_describe_image(png_bytes)
    assert isinstance(desc, str)
    assert len(desc) > 0


@pytest.mark.asyncio
async def test_vision_service_class_returns_str():
    """VisionService.describe_image 应返回 str"""
    service = VisionService()
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    desc = await service.describe_image(png_bytes)
    assert isinstance(desc, str)
    assert len(desc) > 0


@pytest.mark.asyncio
async def test_vision_empty_image_returns_mock():
    """空图片数据应返回 mock 描述"""
    desc = await vision_describe_image(b"")
    assert isinstance(desc, str)
    assert desc == "[mock Vision] image description placeholder"


# ===== Video (stub) =====


@pytest.mark.asyncio
async def test_video_service_returns_501():
    """Video service 应返回 stub 501 响应"""
    service = VideoService()
    result = await service.analyze_video()
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("code") == 501
    assert "实验性服务" in result.get("error", "")


# ===== Screen (stub) =====


def test_screen_service_returns_501():
    """Screen service 应返回 stub 501 响应"""
    service = ScreenService()
    result = service.capture_screen()
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("code") == 501
    assert "实验性服务" in result.get("error", "")


def test_screen_service_status_returns_501():
    """Screen service get_status 也应返回 stub 501 响应"""
    service = ScreenService()
    result = service.get_status()
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("code") == 501


# ===== API 端点集成测试 =====


def test_multimodal_tts_endpoint(test_client):
    """POST /multimodal/tts 应返回 200 + base64 音频"""
    response = test_client.post(
        "/multimodal/tts",
        json={"text": "你好", "voice": "zh-CN-XiaoxiaoNeural"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "audio_base64" in body["data"]


def test_multimodal_asr_endpoint(test_client):
    """POST /multimodal/asr 应返回 200 + 识别文本"""
    audio_b64 = base64.b64encode(b"fake audio").decode("utf-8")
    response = test_client.post(
        "/multimodal/asr",
        json={"audio_base64": audio_b64, "language": "zh"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "text" in body["data"]
    assert isinstance(body["data"]["text"], str)


def test_multimodal_vision_endpoint(test_client):
    """POST /multimodal/vision 应返回 200 + 描述文本"""
    # 1x1 PNG
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    response = test_client.post(
        "/multimodal/vision",
        json={"image_base64": png_b64, "prompt": "描述图片"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "description" in body["data"]
    assert isinstance(body["data"]["description"], str)


def test_multimodal_video_endpoint_returns_501(test_client):
    """POST /multimodal/video 应返回 501"""
    response = test_client.post("/multimodal/video")
    assert response.status_code == 501
    body = response.json()
    detail = body.get("detail", {})
    assert detail.get("ok") is False
    assert "实验性服务" in detail.get("error", "")


def test_multimodal_screen_endpoint_returns_501(test_client):
    """POST /multimodal/screen 应返回 501"""
    response = test_client.post("/multimodal/screen")
    assert response.status_code == 501
    body = response.json()
    detail = body.get("detail", {})
    assert detail.get("ok") is False
    assert "实验性服务" in detail.get("error", "")
