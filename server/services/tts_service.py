"""语音合成服务 (TTS) - 支持 edge-tts（免费）和 OpenAI TTS API"""

import base64
import os
import tempfile

import httpx

from ..providers.registry import get_provider, is_registered


class TTSService:
    """语音合成服务，优先使用免费的 edge-tts，其次使用 OpenAI TTS API"""

    async def synthesize(
        self,
        text: str,
        voice: str = "alloy",
        model_name: str = "tts-1",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> dict:
        """文字转语音

        Args:
            text: 要合成的文本
            voice: 音色 (alloy/echo/fable/onyx/nova/shimmer)
            model_name: 模型名
            speed: 语速 (0.25 ~ 4.0)
            output_format: 输出格式 (mp3/opus/aac/flac)

        Returns:
            {"audio_base64": "...", "format": "mp3", "model": "..."}
        """
        if not text:
            raise ValueError("合成文本为空")

        # 尝试方式1: edge-tts（免费）
        try:
            result = await self._synthesize_with_edge_tts(
                text, voice, output_format
            )
            return result
        except ValueError:
            # edge-tts 不可用，尝试 OpenAI TTS
            pass

        # 尝试方式2: OpenAI TTS API
        result = await self._synthesize_with_openai(
            text, voice, model_name, speed, output_format
        )
        return result

    async def _synthesize_with_edge_tts(
        self, text: str, voice: str, output_format: str
    ) -> dict:
        """使用 edge-tts 进行语音合成（免费）"""
        try:
            import edge_tts  # type: ignore
        except ImportError as exc:
            raise ValueError("edge-tts 未安装") from exc

        # OpenAI 音色名映射到 edge-tts 音色
        voice_map = {
            "alloy": "zh-CN-XiaoxiaoNeural",
            "echo": "zh-CN-YunxiNeural",
            "fable": "zh-CN-YunyangNeural",
            "onyx": "zh-CN-YunjianNeural",
            "nova": "zh-CN-XiaoyiNeural",
            "shimmer": "zh-CN-XiaochenNeural",
        }
        edge_voice = voice_map.get(voice, voice)
        # 如果用户直接传了 edge-tts 的音色名，直接使用
        if "Neural" not in edge_voice and "neural" not in edge_voice.lower():
            edge_voice = voice_map.get("alloy")

        # edge-tts 支持的输出格式
        fmt = output_format if output_format in ("mp3", "opus", "wav") else "mp3"

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{fmt}")
        os.close(tmp_fd)
        try:
            try:
                communicate = edge_tts.Communicate(text, edge_voice)
                await communicate.save(tmp_path)
            except Exception as exc:
                raise ValueError(f"edge-tts 合成失败: {exc}") from exc

            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if not audio_bytes:
            raise ValueError("edge-tts 合成结果为空")

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {
            "audio_base64": audio_b64,
            "format": fmt,
            "model": "edge-tts",
        }

    async def _synthesize_with_openai(
        self,
        text: str,
        voice: str,
        model_name: str,
        speed: float,
        output_format: str,
    ) -> dict:
        """使用 OpenAI TTS API 进行语音合成"""
        api_key, base_url = self._get_openai_config()

        if not api_key:
            raise ValueError(
                "语音合成服务不可用：未安装 edge-tts，且未配置 OpenAI API Key"
            )

        payload = {
            "model": model_name,
            "input": text,
            "voice": voice,
            "response_format": output_format,
            "speed": speed,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{base_url}/audio/speech",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                audio_bytes = response.content
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"OpenAI TTS API 返回错误: {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"OpenAI TTS API 请求失败: {exc}") from exc

        if not audio_bytes:
            raise ValueError("OpenAI TTS API 返回空结果")

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {
            "audio_base64": audio_b64,
            "format": output_format,
            "model": model_name,
        }

    @staticmethod
    def _get_openai_config() -> tuple[str, str]:
        """获取 OpenAI API 配置"""
        api_key = ""
        base_url = "https://api.openai.com/v1"

        if is_registered("openai"):
            try:
                provider = get_provider("openai")
                api_key = getattr(provider, "api_key", "") or ""
                base_url = getattr(provider, "base_url", base_url) or base_url
            except Exception:
                pass

        if not api_key:
            api_key = os.getenv("NEBULA_OPENAI_API_KEY", "") or os.getenv(
                "OPENAI_API_KEY", ""
            )
        if not base_url:
            base_url = os.getenv(
                "NEBULA_OPENAI_BASE_URL", "https://api.openai.com/v1"
            )

        return api_key, base_url.rstrip("/")
