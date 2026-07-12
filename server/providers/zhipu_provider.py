"""Zhipu provider - 基于 OpenAIProtocol"""

from .protocols.openai_protocol import OpenAIProtocol
from .base import ProviderCapability
from .registry import register_provider


@register_provider("zhipu")
class ZhipuProvider(OpenAIProtocol):
    name = "zhipu"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=True,
    )
    supported_models = ["glm-4", "glm-4-flash", "glm-4v"]
    default_chat_model = "glm-4-flash"
    default_embed_model = "embedding-3"
    env_key = "NEBULA_ZHIPU_API_KEY"
    env_base_url = "NEBULA_ZHIPU_BASE_URL"
    default_base_url = "https://open.bigmodel.cn/api/paas/v4"
