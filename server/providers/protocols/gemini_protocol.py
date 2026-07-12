"""Gemini 协议基类

适用于 Google Gemini API。子类只需声明类属性即可。
关键差异:
- 使用 contents + parts 结构,而非 messages
- system 消息需转为 systemInstruction
- assistant -> model, tool -> user 角色映射
- API key 作为 query 参数,非 header
- SSE 解析 candidates[0].content.parts
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from ..base import Message, ProviderCapability
from .base import ProtocolBase, StreamChunk


class GeminiProtocol(ProtocolBase):
    """Gemini 协议基类"""

    protocol: str = "gemini"

    env_key: str = "NEBULA_GEMINI_API_KEY"
    env_base_url: str = "NEBULA_GEMINI_BASE_URL"
    default_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    default_chat_model: str = "gemini-2.0-flash"
    capabilities = ProviderCapability(
        text=True, vision=True, function_calling=True,
        image_generation=False, embedding=False,
    )
    supported_models: list[str] = []

    def __init__(self) -> None:
        self.api_key = os.getenv(self.env_key, "")
        self.base_url = os.getenv(
            self.env_base_url, self.default_base_url
        ).rstrip("/")

    # ---- 协议实现 ----

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

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
            content = m.content
            if m.role == "system":
                text = content if isinstance(content, str) else str(content)
                system_instruction = {"parts": [{"text": text}]}
                continue
            # 支持 str 或 list content
            if isinstance(content, str):
                parts = [{"text": content}]
            else:
                parts = content if isinstance(content, list) else [{"text": str(content)}]
            contents.append(
                {
                    "role": self._to_gemini_role(m.role),
                    "parts": parts,
                }
            )
        return system_instruction, contents

    def _build_payload(
        self, messages: list[Message], model: str, kwargs: dict
    ) -> dict[str, Any]:
        system_instruction, contents = self._build_contents(messages)
        payload: dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        generation_config = kwargs.pop("generation_config", None)
        if generation_config:
            payload["generationConfig"] = generation_config
        payload.update(kwargs)
        return payload

    def _stream_url(self, model: str) -> str:
        target = model or self.default_chat_model
        return (
            f"{self.base_url}/models/{target}:streamGenerateContent"
            f"?alt=sse&key={self.api_key}"
        )

    @staticmethod
    def _parse_sse_line(line: str) -> str:
        line = line.strip()
        if not line or not line.startswith("data:"):
            return ""
        data = line[len("data:"):].strip()
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

    @staticmethod
    def _parse_sse_chunk(line: str) -> StreamChunk | None:
        line = line.strip()
        if not line or not line.startswith("data:"):
            return None
        data = line[len("data:"):].strip()
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return None
        candidates = obj.get("candidates") or []
        if not candidates:
            return None
        candidate = candidates[0]
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = ""
        for part in parts:
            t = part.get("text")
            if t:
                text += t
        finish = candidate.get("finishReason")
        return StreamChunk(
            text=text,
            finish_reason=finish.lower() if finish else None,
            raw=obj,
        )

    # ---- 生成 / 流式 ----

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        if not self.api_key:
            yield self._mock_generate(messages)
            return

        effective_messages, _ = self._apply_multimodal_fallback(messages)
        payload = self._build_payload(effective_messages, model, kwargs)
        url = self._stream_url(model)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        chunk = self._parse_sse_line(line)
                        if chunk:
                            yield chunk
        except httpx.HTTPStatusError as exc:
            if self._messages_have_images(effective_messages):
                stripped = self._strip_images(effective_messages)
                retry_payload = self._build_payload(stripped, model, kwargs)
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                    async with client.stream(
                        "POST",
                        url,
                        headers=self._headers(),
                        json=retry_payload,
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            chunk = self._parse_sse_line(line)
                            if chunk:
                                yield chunk
                return
            raise exc

    async def stream(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[StreamChunk]:
        if not self.api_key:
            yield StreamChunk(text=self._mock_generate(messages), finish_reason="mock")
            return

        effective_messages, _ = self._apply_multimodal_fallback(messages)
        payload = self._build_payload(effective_messages, model, kwargs)
        url = self._stream_url(model)

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    chunk = self._parse_sse_chunk(line)
                    if chunk is not None and chunk.text:
                        yield chunk

    # ---- 嵌入 ----

    async def embed(self, text: str, model: str) -> list[float]:
        raise NotImplementedError("Gemini embedding not enabled in this provider")

    # ---- 连接测试 ----

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

    # ---- info ----

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "available": bool(self.api_key),
            "protocol": self.protocol,
        }
