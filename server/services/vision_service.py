"""图片识别服务 - 基于 OpenAI 兼容 API 的多模态视觉识别"""

import base64
import os

import httpx
from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import Persona
from ..providers.registry import get_provider, is_registered


class VisionService:
    """图片识别服务，使用 OpenAI 兼容的多模态 API 进行图片分析"""

    async def analyze_image(
        self,
        persona_id: int | None,
        image_base64: str,
        prompt: str = "请描述这张图片的内容",
        model_name: str | None = None,
    ) -> dict:
        """图片识别：调用多模态 LLM 分析图片内容

        Args:
            persona_id: Persona ID，用于获取 provider 配置
            image_base64: base64 编码的图片（可含 data URI 前缀）
            prompt: 识别提示词
            model_name: 指定模型名（可选）

        Returns:
            {"description": "...", "model": "..."}
        """
        # 验证图片
        valid, mime_type = self.validate_image(image_base64)
        if not valid:
            raise ValueError("无效的 base64 图片数据")

        # 获取 provider 配置
        config = await self._get_provider_config(persona_id, model_name)

        if not config["api_key"]:
            raise ValueError("未配置 API Key，无法调用视觉识别服务")

        # 清理 base64 数据（去除 data URI 前缀）
        raw_base64 = self._strip_data_uri(image_base64)

        # 构建 OpenAI 兼容的多模态消息
        data_url = f"data:{mime_type};base64,{raw_base64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ]

        payload = {
            "model": config["model_name"],
            "messages": messages,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{config['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"视觉识别 API 返回错误: {exc.response.status_code} - {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"视觉识别 API 请求失败: {exc}") from exc

        # 提取回复文本
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("视觉识别 API 返回空结果")
        message = choices[0].get("message") or {}
        description = message.get("content", "") or ""

        return {
            "description": description,
            "model": config["model_name"],
        }

    @staticmethod
    def validate_image(image_base64: str) -> tuple[bool, str]:
        """验证 base64 图片数据是否有效

        Args:
            image_base64: base64 编码的图片（可含 data URI 前缀）

        Returns:
            (是否有效, mime_type)
        """
        if not image_base64:
            return False, ""

        raw = VisionService._strip_data_uri(image_base64)

        # 尝试解码 base64
        try:
            decoded = base64.b64decode(raw, validate=False)
        except Exception:
            return False, ""
        if not decoded:
            return False, ""

        # 从 data URI 前缀检测 mime type
        mime_type = "image/png"  # 默认
        if image_base64.startswith("data:"):
            prefix = image_base64.split(",", 1)[0]
            # 格式: data:image/png;base64
            if ":" in prefix and ";" in prefix:
                mime_type = prefix.split(":")[1].split(";")[0]

        # 如果没有 data URI 前缀，尝试从内容头部检测
        if not image_base64.startswith("data:"):
            if raw.startswith("iVBORw0KGgo"):
                mime_type = "image/png"
            elif raw.startswith("/9j/"):
                mime_type = "image/jpeg"
            elif raw.startswith("R0lGOD"):
                mime_type = "image/gif"
            elif raw.startswith("UklGR"):
                mime_type = "image/webp"

        return True, mime_type

    @staticmethod
    def _strip_data_uri(image_base64: str) -> str:
        """去除 data URI 前缀，返回纯 base64 字符串"""
        if image_base64.startswith("data:") and "," in image_base64:
            return image_base64.split(",", 1)[1]
        return image_base64

    async def _get_provider_config(
        self, persona_id: int | None, model_name: str | None = None
    ) -> dict:
        """获取 provider 的 API 配置（endpoint、api_key、model_name）

        优先从 persona 获取 provider 名称和模型，其次从环境变量读取。
        """
        provider_name = "openai"
        persona_model_name: str | None = None

        if persona_id is not None:
            async with async_session() as session:
                result = await session.execute(
                    select(Persona).where(Persona.id == persona_id)
                )
                persona = result.scalar_one_or_none()
                if persona:
                    provider_name = persona.model_provider or "openai"
                    persona_model_name = persona.model_name

        # 从 provider 实例获取 api_key 和 base_url
        api_key = ""
        base_url = "https://api.openai.com/v1"

        if is_registered(provider_name):
            try:
                provider = get_provider(provider_name)
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

        # 确定模型名
        final_model = (
            model_name
            or persona_model_name
            or "gpt-4o-mini"
        )

        return {
            "api_key": api_key,
            "base_url": base_url.rstrip("/"),
            "model_name": final_model,
            "provider_name": provider_name,
        }
