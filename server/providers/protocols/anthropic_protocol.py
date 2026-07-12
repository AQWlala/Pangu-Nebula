"""Anthropic 协议基类

适用于 Anthropic Claude API。子类只需声明类属性即可。
关键差异:
- 使用 x-api-key + anthropic-version 头
- system 消息需从 messages 中分离
- SSE 事件类型为 content_block_delta
- 需要 max_tokens 参数
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from ..base import Message, ProviderCapability
from .base import ProtocolBase, StreamChunk


class AnthropicProtocol(ProtocolBase):
    """Anthropic 协议基类"""

    protocol: str = "anthropic"

    env_key: str = "NEBULA_ANTHROPIC_API_KEY"
    env_base_url: str = "NEBULA_ANTHROPIC_BASE_URL"
    default_base_url: str = "https://api.anthropic.com"
    default_chat_model: str = "claude-3-5-sonnet-latest"
    api_version: str = "2023-06-01"
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
                system = m.content if isinstance(m.content, str) else str(m.content)
            else:
                out.append({"role": m.role, "content": m.content})
        return system, out

    def _build_payload(
        self, messages: list[Message], model: str, kwargs: dict
    ) -> dict[str, Any]:
        system, api_messages = self._split_system(messages)
        payload: dict[str, Any] = {
            "model": model or self.default_chat_model,
            "messages": api_messages,
            "max_tokens": kwargs.pop("max_tokens", 1024),
            "stream": True,
        }
        if system:
            payload["system"] = system
        payload.update(kwargs)
        return payload

    def _stream_url(self) -> str:
        return f"{self.base_url}/v1/messages"

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
        if obj.get("type") != "content_block_delta":
            return ""
        delta = obj.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text", "") or ""
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
        if obj.get("type") == "content_block_delta":
            delta = obj.get("delta") or {}
            if delta.get("type") == "text_delta":
                return StreamChunk(text=delta.get("text", "") or "", raw=obj)
        if obj.get("type") == "message_stop":
            return StreamChunk(text="", finish_reason="stop", raw=obj)
        return None

    # ---- 生成 / 流式 ----

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        if not self.api_key:
            yield self._mock_generate(messages)
            return

        effective_messages, _ = self._apply_multimodal_fallback(messages)
        payload = self._build_payload(effective_messages, model, kwargs)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                async with client.stream(
                    "POST",
                    self._stream_url(),
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
                        self._stream_url(),
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

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                self._stream_url(),
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
        raise NotImplementedError("Anthropic does not provide embeddings")

    # ---- 连接测试 ----

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

    # ---- info ----

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "available": bool(self.api_key),
            "protocol": self.protocol,
        }
