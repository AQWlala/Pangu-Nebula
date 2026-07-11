from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


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
        }
