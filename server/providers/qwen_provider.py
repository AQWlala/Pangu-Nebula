import json
import os
from typing import AsyncIterator

import httpx

from .base import BaseProvider, Message, ProviderCapability
from .registry import register_provider


@register_provider("qwen")
class QwenProvider(BaseProvider):
    name = "qwen"
    capabilities = ProviderCapability(
        text=True,
        vision=True,
        function_calling=True,
        image_generation=False,
        embedding=True,
    )
    supported_models = ["qwen-max", "qwen-plus", "qwen-turbo"]
    default_chat_model = "qwen-turbo"
    default_embed_model = "text-embedding-v3"

    def __init__(self):
        self.api_key = os.getenv("NEBULA_QWEN_API_KEY", "")
        self.base_url = os.getenv(
            "NEBULA_QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        if not self.api_key:
            yield f"[mock] {self.name} response for: {messages[-1].content[:50]}"
            return

        payload = {
            "model": model or self.default_chat_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    chunk = self._parse_sse_line(line)
                    if chunk:
                        yield chunk

    @staticmethod
    def _parse_sse_line(line: str) -> str:
        line = line.strip()
        if not line or not line.startswith("data:"):
            return ""
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return ""
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return ""
        choices = obj.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content", "") or ""

    async def embed(self, text: str, model: str) -> list[float]:
        if not self.api_key:
            return [0.0] * 1536

        payload = {"model": model or self.default_embed_model, "input": text}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["data"][0]["embedding"]

    async def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def info(self) -> dict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "available": bool(self.api_key),
        }
