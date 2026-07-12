"""OpenAI provider - 基于 OpenAIProtocol

仅需声明类属性,所有实现由 OpenAIProtocol 提供。
"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("openai")
class OpenAIProvider(OpenAIProtocol):
    name = "openai"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=True,
    )
    supported_models = ["gpt-4o", "gpt-4o-mini"]
    default_chat_model = "gpt-4o-mini"
    default_embed_model = "text-embedding-3-small"
    env_key = "NEBULA_OPENAI_API_KEY"
    env_base_url = "NEBULA_OPENAI_BASE_URL"
    default_base_url = "https://api.openai.com/v1"
