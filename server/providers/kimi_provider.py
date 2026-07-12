"""Kimi provider - 基于 OpenAIProtocol"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("kimi")
class KimiProvider(OpenAIProtocol):
    name = "kimi"
    capabilities = ProviderCapability(
        text=True,
        vision=False,
        function_calling=True,
        image_generation=False,
        embedding=False,
    )
    supported_models = ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
    default_chat_model = "moonshot-v1-8k"
    default_embed_model = None
    env_key = "NEBULA_KIMI_API_KEY"
    env_base_url = "NEBULA_KIMI_BASE_URL"
    default_base_url = "https://api.moonshot.cn/v1"
