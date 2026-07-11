import json
import os
from typing import AsyncIterator

import httpx

from .base import BaseProvider, Message, ProviderCapability
from .registry import register_provider


@register_provider("anthropic")
class AnthropicProvider(BaseProvider):
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

    def __init__(self):
        self.api_key = os.getenv("NEBULA_ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv(
            "NEBULA_ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _split_system(
        messages: list[Message],
    ) -> tuple[str | None, list[dict]]:
        system = None
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                out.append({"role": m.role, "content": m.content})
        return system, out

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        system, api_messages = self._split_system(messages)
        payload: dict = {
            "model": model or self.default_chat_model,
            "messages": api_messages,
            "max_tokens": kwargs.pop("max_tokens", 1024),
            "stream": True,
        }
        if system:
            payload["system"] = system
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
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
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return ""
        if obj.get("type") != "content_block_delta":
            return ""
        delta = obj.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text", "") or ""
        return ""

    async def embed(self, text: str, model: str) -> list[float]:
        raise NotImplementedError("Anthropic does not provide embeddings")

    async def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers=self._headers(),
                    json={
                        "model": self.default_chat_model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False
