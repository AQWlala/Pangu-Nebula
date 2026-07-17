"""OpenAI 兼容协议基类

适用于所有 OpenAI API 兼容的 provider:
- openai, deepseek, openrouter, qwen, kimi, zhipu

子类只需声明类属性:
    name, env_key, env_base_url, default_base_url,
    capabilities, supported_models, default_chat_model, default_embed_model

即可自动获得完整的 generate/embed/test_connection/info 实现。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from ..base import Message, ProviderCapability
from ..registry import register_provider
from ..config_store import resolve_api_key, resolve_base_url
from .base import ProtocolBase, StreamChunk


class OpenAIProtocol(ProtocolBase):
    """OpenAI 兼容协议基类 - 7 个 provider 共用"""

    protocol: str = "openai"

    # 子类必须覆盖以下类属性
    env_key: str = "NEBULA_OPENAI_API_KEY"
    env_base_url: str = "NEBULA_OPENAI_BASE_URL"
    default_base_url: str = "https://api.openai.com/v1"
    default_chat_model: str = "gpt-4o-mini"
    default_embed_model: str | None = "text-embedding-3-small"
    capabilities = ProviderCapability(
        text=True, vision=True, function_calling=True,
        image_generation=False, embedding=True,
    )
    supported_models: list[str] = []

    def __init__(self) -> None:
        # env var 优先，config 文件作为 fallback
        self.api_key = resolve_api_key(self.env_key, self.name)
        self.base_url = resolve_base_url(
            self.env_base_url, self.name, self.default_base_url
        )

    # ---- 协议实现 ----

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self, messages: list[Message], model: str, kwargs: dict
    ) -> dict[str, Any]:
        msgs: list[dict[str, Any]] = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            # v2.2.0: 序列化工具调用相关字段
            if m.tool_calls is not None:
                entry["tool_calls"] = m.tool_calls
                # assistant 工具调用消息 content 为空时传 null,兼容严格 provider
                if entry["content"] == "":
                    entry["content"] = None
            if m.tool_call_id is not None:
                entry["tool_call_id"] = m.tool_call_id
            msgs.append(entry)
        payload: dict[str, Any] = {
            "model": model or self.default_chat_model,
            "messages": msgs,
            "stream": True,
        }
        payload.update(kwargs)
        # v2.2.0: function calling — 携带 tools 时缺省 tool_choice=auto
        if payload.get("tools") and "tool_choice" not in payload:
            payload["tool_choice"] = "auto"
        return payload

    def _stream_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    @staticmethod
    def _parse_sse_line(line: str) -> str:
        line = line.strip()
        if not line or not line.startswith("data:"):
            return ""
        data = line[len("data:"):].strip()
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

    @staticmethod
    def _parse_sse_chunk(line: str) -> StreamChunk | None:
        """解析为 StreamChunk,包含 finish_reason"""
        line = line.strip()
        if not line or not line.startswith("data:"):
            return None
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            return StreamChunk(text="", finish_reason="stop")
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return None
        choices = obj.get("choices") or []
        if not choices:
            return None
        choice = choices[0]
        delta = choice.get("delta") or {}
        # v2.2.0: 解析工具调用增量 (delta.tool_calls)
        tool_calls = delta.get("tool_calls") or None
        # v2.3.0 Phase 3-A1: 推理过程解析
        # - DeepSeek / 通用推理模型用 delta.reasoning_content
        # - OpenAI o1 / 部分 provider 用 delta.reasoning
        reasoning_text = delta.get("reasoning_content") or delta.get("reasoning") or ""
        # 推理阶段标识 (部分 provider 在 reasoning 块上携带 phase 字段)
        reasoning_phase = delta.get("reasoning_phase")
        return StreamChunk(
            text=delta.get("content", "") or "",
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            reasoning=reasoning_text,
            reasoning_phase=reasoning_phase,
            raw=obj,
        )

    # ---- 生成 / 流式 ----

    async def generate(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[str]:
        # 无 API key 时返回 mock
        if not self.api_key:
            yield self._mock_generate(messages)
            return

        # 多模态 fallback:不支持 vision 时剥离图片
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
            # 多模态 fallback:若原图含图片且本次失败,剥离图片重试一次
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
        """OpenAI 协议的 stream - 直接产出 StreamChunk 含 finish_reason"""
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
                    if chunk is None:
                        continue
                    # v2.2.0: 产出文本块 / 工具调用块 / 结束块 (任一非空)
                    # v2.3.0 Phase 3-A1: 新增 reasoning 块 (推理过程)
                    if (
                        chunk.text
                        or chunk.tool_calls
                        or chunk.finish_reason
                        or chunk.reasoning
                    ):
                        yield chunk

    # ---- 嵌入 ----

    async def embed(self, text: str, model: str) -> list[float]:
        if not self.api_key:
            return self._mock_embed()

        embed_model = model or self.default_embed_model or "text-embedding-3-small"
        payload = {"model": embed_model, "input": text}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["data"][0]["embedding"]

    # ---- 连接测试 ----

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

    # ---- info ----

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities.model_dump(),
            "supported_models": list(self.supported_models),
            "available": bool(self.api_key),
            "protocol": self.protocol,
        }


# 便捷注册函数 - 子类用 register_openai_provider("name") 装饰
def register_openai_provider(name: str):
    """注册一个 OpenAI 兼容 provider"""
    return register_provider(name)
