"""DeepSeek provider - 基于 OpenAIProtocol"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("deepseek")
class DeepSeekProvider(OpenAIProtocol):
    name = "deepseek"
    capabilities = ProviderCapability(
        text=True,
        vision=False,
        function_calling=True,
        image_generation=False,
        embedding=True,
    )
    supported_models = ["deepseek-chat", "deepseek-reasoner"]
    default_chat_model = "deepseek-chat"
    default_embed_model = "deepseek-chat"
    env_key = "NEBULA_DEEPSEEK_API_KEY"
    env_base_url = "NEBULA_DEEPSEEK_BASE_URL"
    default_base_url = "https://api.deepseek.com/v1"
