"""Gemini provider - 基于 GeminiProtocol"""

from .protocols.gemini_protocol import GeminiProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("gemini")
class GeminiProvider(GeminiProtocol):
    name = "gemini"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=False,
    )
    supported_models = ["gemini-2.0-flash", "gemini-1.5-pro"]
    default_chat_model = "gemini-2.0-flash"
    env_key = "NEBULA_GEMINI_API_KEY"
    env_base_url = "NEBULA_GEMINI_BASE_URL"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
