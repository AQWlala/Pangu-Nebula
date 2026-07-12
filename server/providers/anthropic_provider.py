"""Anthropic provider - 基于 AnthropicProtocol"""

from .protocols.anthropic_protocol import AnthropicProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("anthropic")
class AnthropicProvider(AnthropicProtocol):
    name = "anthropic"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=False,
    )
    supported_models = ["claude-3-5-sonnet-latest", "claude-3-opus-20240229"]
    default_chat_model = "claude-3-5-sonnet-latest"
    api_version = "2023-06-01"
    env_key = "NEBULA_ANTHROPIC_API_KEY"
    env_base_url = "NEBULA_ANTHROPIC_BASE_URL"
    default_base_url = "https://api.anthropic.com"
