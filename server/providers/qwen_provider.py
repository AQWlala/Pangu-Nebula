"""Qwen provider - 基于 OpenAIProtocol"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("qwen")
class QwenProvider(OpenAIProtocol):
    name = "qwen"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=True,
    )
    supported_models = ["qwen-max", "qwen-plus", "qwen-turbo"]
    default_chat_model = "qwen-turbo"
    default_embed_model = "text-embedding-v3"
    env_key = "NEBULA_QWEN_API_KEY"
    env_base_url = "NEBULA_QWEN_BASE_URL"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
