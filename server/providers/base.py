from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    # 支持 str (纯文本) 或 list (多模态: [{"type":"text","text":...},{"type":"image_url",...}])
    content: Any = ""
    # v2.2.0: 工具调用相关 (OpenAI 风格)
    # assistant 消息携带 tool_calls 数组; role="tool" 消息携带 tool_call_id
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ProviderCapability(BaseModel):
    text: bool = False
    vision: bool = False
    function_calling: bool = False
    image_generation: bool = False
    embedding: bool = False


class BaseProvider(ABC):
    name: str
    capabilities: ProviderCapability
    supported_models: list[str] = []
    # 协议标识: "openai" | "anthropic" | "gemini" | "custom"
    # 由具体协议基类设置,用于运行时反射与协议路由
    protocol: str = "custom"

    @abstractmethod
    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def embed(self, text: str, model: str) -> list[float]:
        ...

    async def test_connection(self) -> bool:
        return True

    def info(self) -> dict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "protocol": self.protocol,
        }
