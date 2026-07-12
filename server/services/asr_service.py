"""语音识别服务 (ASR) - 双模式: 有 OpenAI key 走 Whisper API, 无则降级为 mock"""

import os
import tempfile

import httpx

from ..providers.registry import get_provider, is_registered


# mock 模式返回的固定文本
_MOCK_ASR_TEXT = "[mock ASR] transcription placeholder"


def _get_openai_config() -> tuple[str, str]:
    """获取 OpenAI API 配置 (api_key, base_url)"""
    api_key = ""
    base_url = "https://api.openai.com/v1"

    # 优先从 provider 实例获取
    if is_registered("openai"):
        try:
            provider = get_provider("openai")
            api_key = getattr(provider, "api_key", "") or ""
            base_url = getattr(provider, "base_url", base_url) or base_url
        except Exception:
            pass

    # 环境变量兜底
    if not api_key:
        api_key = os.getenv("NEBULA_OPENAI_API_KEY", "") or os.getenv(
            "OPENAI_API_KEY", ""
        )
    if not base_url:
        base_url = os.getenv(
            "NEBULA_OPENAI_BASE_URL", "https://api.openai.com/v1"
        )

    return api_key, base_url.rstrip("/")


async def transcribe(audio_data: bytes, language: str = "zh") -> str:
    """语音转文字（双模式）

    - 配置了 OpenAI API key 时调用 Whisper API
    - 未配置 key 时返回 mock 文本

    Args:
        audio_data: 音频原始字节
        language: 语言代码 (zh/en/...)

    Returns:
        识别文本；mock 模式返回 "[mock ASR] transcription placeholder"
    """
    if not audio_data:
        return _MOCK_ASR_TEXT

    api_key, base_url = _get_openai_config()

    # 无 API key 时降级为 mock
    if not api_key:
        return _MOCK_ASR_TEXT

    # 写入临时文件供上传
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(audio_data)

        with open(tmp_path, "rb") as f:
            files = {"file": ("audio.wav", f, "audio/wav")}
            data = {"model": "whisper-1"}
            if language and language != "auto":
                data["language"] = language

            headers = {"Authorization": f"Bearer {api_key}"}

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(120.0)
                ) as client:
                    response = await client.post(
                        f"{base_url}/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                    )
                    response.raise_for_status()
                    result = response.json()
            except Exception:
                # API 调用失败时降级为 mock
                return _MOCK_ASR_TEXT
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    text = result.get("text", "") or ""
    if not text:
        return _MOCK_ASR_TEXT

    return text


class ASRService:
    """语音识别服务（兼容旧接口，封装模块级 transcribe 函数）

    双模式:
    - 配置了 OpenAI key 时调用 Whisper API
    - 未配置 key 时返回 mock 文本
    """

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "zh",
    ) -> str:
        """语音转文字（双模式，返回 str）

        Args:
            audio_data: 音频原始字节
            language: 语言代码 (zh/en/...)

        Returns:
            识别文本；mock 模式返回 "[mock ASR] transcription placeholder"
        """
        return await transcribe(audio_data, language)
