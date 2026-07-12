"""图片识别服务 - 双模式: 有 API key 走真实多模态 API, 无则降级为 mock"""

import base64
import os

import httpx

from ..providers.registry import get_provider, is_registered


# mock 模式返回的固定描述
_MOCK_VISION_TEXT = "[mock Vision] image description placeholder"


def _detect_mime_type(image_data: bytes) -> str:
    """根据图片字节头部检测 mime type"""
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_data.startswith(b"GIF8"):
        return "image/gif"
    if image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _get_vision_config() -> tuple[str, str, str]:
    """获取视觉识别 API 配置 (api_key, base_url, model_name)

    优先 OpenAI，回退到环境变量。
    """
    api_key = ""
    base_url = "https://api.openai.com/v1"
    model_name = "gpt-4o"

    # 从 provider 实例获取
    for provider_name in ("openai", "gemini"):
        if is_registered(provider_name):
            try:
                provider = get_provider(provider_name)
                api_key = getattr(provider, "api_key", "") or ""
                base_url = getattr(provider, "base_url", base_url) or base_url
                if api_key:
                    # 优先 OpenAI；若是 gemini，使用 Gemini 兼容端点
                    if provider_name == "gemini":
                        model_name = "gemini-1.5-flash"
                    break
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

    return api_key, base_url.rstrip("/"), model_name


async def describe_image(image_data: bytes, prompt: str = "") -> str:
    """图片内容识别（双模式）

    - 配置了 API key 时调用 OpenAI Vision API (gpt-4o) 或 Gemini Vision API
    - 未配置 key 时返回 mock 描述文本

    Args:
        image_data: 图片原始字节
        prompt: 识别提示词（空则使用默认描述提示）

    Returns:
        图片描述文本；mock 模式返回 "[mock Vision] image description placeholder"
    """
    if not image_data:
        return _MOCK_VISION_TEXT

    api_key, base_url, model_name = _get_vision_config()

    # 无 API key 时降级为 mock
    if not api_key:
        return _MOCK_VISION_TEXT

    # 准备 base64 编码
    mime_type = _detect_mime_type(image_data)
    image_b64 = base64.b64encode(image_data).decode("utf-8")
    data_url = f"data:{mime_type};base64,{image_b64}"

    # 默认提示词
    final_prompt = prompt or "请描述这张图片的内容"

    # 构建 OpenAI 兼容的多模态消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": final_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        }
    ]

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 4096,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        # API 调用失败时降级为 mock
        return _MOCK_VISION_TEXT

    # 提取回复文本
    choices = data.get("choices") or []
    if not choices:
        return _MOCK_VISION_TEXT
    message = choices[0].get("message") or {}
    description = message.get("content", "") or ""

    if not description:
        return _MOCK_VISION_TEXT

    return description


class VisionService:
    """图片识别服务（兼容旧接口，封装模块级 describe_image 函数）

    双模式:
    - 配置了 API key 时调用 OpenAI Vision API (gpt-4o) 或 Gemini Vision API
    - 未配置 key 时返回 mock 描述文本
    """

    async def describe_image(
        self,
        image_data: bytes,
        prompt: str = "",
    ) -> str:
        """图片内容识别（双模式，返回 str）

        Args:
            image_data: 图片原始字节
            prompt: 识别提示词

        Returns:
            图片描述文本；mock 模式返回 "[mock Vision] image description placeholder"
        """
        return await describe_image(image_data, prompt)
