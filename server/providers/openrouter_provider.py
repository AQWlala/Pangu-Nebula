"""OpenRouter provider - 基于 OpenAIProtocol"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("openrouter")
class OpenRouterProvider(OpenAIProtocol):
    name = "openrouter"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=False,
    )
    supported_models = [
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash",
        "deepseek/deepseek-chat",
    ]
    default_chat_model = "openai/gpt-4o"
    default_embed_model = None
    env_key = "NEBULA_OPENROUTER_API_KEY"
    env_base_url = "NEBULA_OPENROUTER_BASE_URL"
    default_base_url = "https://openrouter.ai/api/v1"
