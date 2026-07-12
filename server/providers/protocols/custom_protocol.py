"""自定义协议基类

适用于不遵循 OpenAI/Anthropic/Gemini 标准协议的 provider。
子类必须自行实现 generate / embed / test_connection,
但可复用 ProtocolBase 提供的多模态 fallback 与流式工具方法。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..base import Message, ProviderCapability
from .base import ProtocolBase, StreamChunk


class CustomProtocol(ProtocolBase):
    """自定义协议基类 - generate / embed 留给子类实现"""

    protocol: str = "custom"

    capabilities = ProviderCapability(
        text=True, vision=False, function_calling=False,
        image_generation=False, embedding=False,
    )
    supported_models: list[str] = []

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        raise NotImplementedError(
            f"{self.__class__.__name__}.generate() must be implemented"
        )
        # yield 让 Python 识别为 async generator
        yield ""  # pragma: no cover

    async def embed(self, text: str, model: str) -> list[float]:
        raise NotImplementedError(
            f"{self.__class__.__name__}.embed() must be implemented"
        )

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "available": bool(getattr(self, "api_key", "")),
            "protocol": self.protocol,
        }
