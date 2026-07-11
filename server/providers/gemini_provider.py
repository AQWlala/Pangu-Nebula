import json
import os
from typing import AsyncIterator

import httpx

from .base import BaseProvider, Message, ProviderCapability
from .registry import register_provider


@register_provider("gemini")
class GeminiProvider(BaseProvider):
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

    def __init__(self):
        self.api_key = os.getenv("NEBULA_GEMINI_API_KEY", "")
        self.base_url = os.getenv(
            "NEBULA_GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")

    @staticmethod
    def _to_gemini_role(role: str) -> str:
        if role == "assistant":
            return "model"
        if role == "tool":
            return "user"
        return role

    def _build_contents(
        self, messages: list[Message]
    ) -> tuple[dict | None, list[dict]]:
        system_instruction: dict | None = None
        contents: list[dict] = []
        for m in messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
                continue
            contents.append(
                {
                    "role": self._to_gemini_role(m.role),
                    "parts": [{"text": m.content}],
                }
            )
        return system_instruction, contents

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        target_model = model or self.default_chat_model
        system_instruction, contents = self._build_contents(messages)
        payload: dict = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        generation_config = kwargs.pop("generation_config", None)
        if generation_config:
            payload["generationConfig"] = generation_config
        payload.update(kwargs)

        url = (
            f"{self.base_url}/models/{target_model}:streamGenerateContent"
            f"?alt=sse&key={self.api_key}"
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                url,
                headers={"Content-Type": "application/json"},
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
        candidates = obj.get("candidates") or []
        if not candidates:
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if text:
                return text
        return ""

    async def embed(self, text: str, model: str) -> list[float]:
        raise NotImplementedError("Gemini embedding not enabled in this provider")

    async def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    params={"key": self.api_key},
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False
