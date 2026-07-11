"""语音识别服务 (ASR) - 支持 OpenAI Whisper API 和本地 whisper 模型"""

import base64
import os
import tempfile

import httpx

from ..providers.registry import get_provider, is_registered


class ASRService:
    """语音识别服务，优先使用 OpenAI Whisper API，其次使用本地 whisper"""

    async def transcribe(
        self,
        audio_base64: str,
        language: str = "zh",
        model_name: str = "whisper-1",
    ) -> dict:
        """语音转文字

        Args:
            audio_base64: base64 编码的音频（可含 data URI 前缀）
            language: 语言代码 (zh/en/auto)
            model_name: 模型名

        Returns:
            {"text": "...", "language": "...", "model": "..."}
        """
        if not audio_base64:
            raise ValueError("音频数据为空")

        # 解码 base64 为临时文件
        raw_base64 = self._strip_data_uri(audio_base64)
        try:
            audio_bytes = base64.b64decode(raw_base64)
        except Exception as exc:
            raise ValueError("无效的 base64 音频数据") from exc

        if not audio_bytes:
            raise ValueError("音频数据为空")

        # 尝试方式1: OpenAI Whisper API
        try:
            result = await self._transcribe_with_openai(
                audio_bytes, language, model_name
            )
            return result
        except ValueError:
            # API 不可用，尝试本地 whisper
            pass

        # 尝试方式2: 本地 whisper 模型
        result = await self._transcribe_with_local_whisper(
            audio_bytes, language, model_name
        )
        return result

    async def detect_language(self, audio_base64: str) -> str | None:
        """语言检测（简单实现，返回 None）

        完整实现可使用 whisper 的 detect_language 功能。
        """
        return None

    async def _transcribe_with_openai(
        self, audio_bytes: bytes, language: str, model_name: str
    ) -> dict:
        """使用 OpenAI Whisper API 进行语音识别"""
        api_key, base_url = self._get_openai_config()

        if not api_key:
            raise ValueError("未配置 OpenAI API Key")

        # 写入临时文件
        suffix = ".wav"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(audio_bytes)

            with open(tmp_path, "rb") as f:
                files = {"file": (f"audio{suffix}", f, "audio/wav")}
                data = {"model": model_name}
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
                except httpx.HTTPStatusError as exc:
                    raise ValueError(
                        f"Whisper API 返回错误: {exc.response.status_code}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise ValueError(f"Whisper API 请求失败: {exc}") from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        text = result.get("text", "") or ""
        detected_lang = result.get("language", language) or language

        return {
            "text": text,
            "language": detected_lang,
            "model": model_name,
        }

    async def _transcribe_with_local_whisper(
        self, audio_bytes: bytes, language: str, model_name: str
    ) -> dict:
        """使用本地 whisper 模型进行语音识别"""
        try:
            import whisper  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "语音识别服务不可用：未配置 OpenAI API Key，且未安装本地 whisper (openai-whisper)"
            ) from exc

        # 写入临时文件
        suffix = ".wav"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(audio_bytes)

            # 本地 whisper 模型名映射
            local_model = "base"
            if "tiny" in model_name:
                local_model = "tiny"
            elif "small" in model_name:
                local_model = "small"
            elif "medium" in model_name:
                local_model = "medium"
            elif "large" in model_name:
                local_model = "large"

            # whisper 模型加载和转录是同步操作
            model = whisper.load_model(local_model)
            transcribe_kwargs: dict = {}
            if language and language != "auto":
                transcribe_kwargs["language"] = language
            result = model.transcribe(tmp_path, **transcribe_kwargs)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        text = result.get("text", "") or ""
        detected_lang = result.get("language", language) or language

        return {
            "text": text,
            "language": detected_lang,
            "model": f"whisper-local-{local_model}",
        }

    @staticmethod
    def _get_openai_config() -> tuple[str, str]:
        """获取 OpenAI API 配置"""
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

    @staticmethod
    def _strip_data_uri(data: str) -> str:
        """去除 data URI 前缀"""
        if data.startswith("data:") and "," in data:
            return data.split(",", 1)[1]
        return data
