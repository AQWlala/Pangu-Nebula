"""协议基类 - 提供统一的多模态 fallback 与流式响应接口

所有协议基类 (OpenAI/Anthropic/Gemini/Custom) 均继承自 ProtocolBase。
ProtocolBase 不直接实例化,仅提供共享工具方法:
- 多模态内容检测与图片剥离
- 统一的 StreamChunk 结构
- 统一的 mock 响应生成 (无 API key 时)
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from pydantic import BaseModel

from ..base import BaseProvider, Message


class StreamChunk(BaseModel):
    """统一流式响应块 - 跨协议统一的输出结构"""

    text: str = ""
    finish_reason: str | None = None
    raw: dict[str, Any] | None = None


class ProtocolBase(BaseProvider):
    """协议基类 - 所有协议 (OpenAI/Anthropic/Gemini/Custom) 的共同祖先

    子类需实现:
        - _headers() -> dict
        - _build_payload(messages, model, kwargs) -> dict
        - _parse_sse_line(line) -> str
        - _stream_url(model) -> str  (流式请求 URL)
        - generate(...)
        - embed(...)
    """

    protocol: str = "custom"

    # ---- 多模态 fallback 工具方法 ----

    @staticmethod
    def _has_image_content(content: Any) -> bool:
        """检测消息 content 是否包含图片 (OpenAI 多模态 content 数组格式)"""
        if not isinstance(content, list):
            return False
        for part in content:
            if isinstance(part, dict) and part.get("type") in (
                "image_url",
                "image",
                "input_image",
            ):
                return True
        return False

    @staticmethod
    def _messages_have_images(messages: list[Message]) -> bool:
        """检测消息列表中是否存在任意图片内容"""
        for m in messages:
            if ProtocolBase._has_image_content(m.content):
                return True
        return False

    @staticmethod
    def _strip_images(messages: list[Message]) -> list[Message]:
        """剥离图片内容,返回纯文本消息副本

        - 若 content 为 str: 原样保留
        - 若 content 为 list: 过滤掉 image 类型 part,保留 text part;
          若过滤后为空,填充空字符串以保持消息结构
        """
        stripped: list[Message] = []
        for m in messages:
            if not isinstance(m.content, list):
                stripped.append(Message(role=m.role, content=m.content))
                continue
            text_parts = [
                p
                for p in m.content
                if not (isinstance(p, dict) and p.get("type") in (
                    "image_url", "image", "input_image"
                ))
            ]
            # 拼接所有 text part 为单一字符串,保持 OpenAI 兼容
            text_chunks = []
            for p in text_parts:
                if isinstance(p, dict):
                    text_chunks.append(p.get("text", ""))
                elif isinstance(p, str):
                    text_chunks.append(p)
            new_content = "".join(text_chunks) if text_chunks else ""
            stripped.append(Message(role=m.role, content=new_content))
        return stripped

    def _apply_multimodal_fallback(
        self, messages: list[Message]
    ) -> tuple[list[Message], bool]:
        """应用多模态 fallback:若 provider 不支持 vision 且消息含图片,剥离图片

        返回 (处理后消息, 是否剥离了图片)
        """
        if not self.capabilities.vision and self._messages_have_images(messages):
            return self._strip_images(messages), True
        return messages, False

    # ---- mock 响应生成 ----

    def _mock_generate(self, messages: list[Message]) -> str:
        """无 API key 时的统一 mock 响应"""
        last = messages[-1] if messages else None
        preview = ""
        if last is not None:
            content = last.content
            if isinstance(content, str):
                preview = content[:50]
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get("text"):
                        preview = p["text"][:50]
                        break
        return f"[mock] {self.name} response for: {preview}"

    @staticmethod
    def _mock_embed(dim: int = 1536) -> list[float]:
        return [0.0] * dim

    # ---- 统一流式接口 ----

    async def stream(
        self, messages: list[Message], model: str, **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """统一流式接口 - 返回 StreamChunk 对象,跨协议一致

        默认实现基于 generate() 文本流,封装为 StreamChunk。
        子类可覆盖以提供更丰富的元数据 (finish_reason 等)。
        """
        async for text in self.generate(messages, model, **kwargs):
            yield StreamChunk(text=text)
