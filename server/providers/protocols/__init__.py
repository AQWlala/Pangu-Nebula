"""Provider 协议抽象层

提供 4 种协议基类,统一流式响应接口与多模态 fallback:
- OpenAIProtocol: OpenAI 兼容协议 (openai/deepseek/openrouter/qwen/kimi/zhipu)
- AnthropicProtocol: Anthropic 协议
- GeminiProtocol: Gemini 协议
- CustomProtocol: 自定义协议基类
"""

from .anthropic_protocol import AnthropicProtocol
from .base import ProtocolBase, StreamChunk
from .custom_protocol import CustomProtocol
from .gemini_protocol import GeminiProtocol
from .openai_protocol import OpenAIProtocol

__all__ = [
    "ProtocolBase",
    "StreamChunk",
    "OpenAIProtocol",
    "AnthropicProtocol",
    "GeminiProtocol",
    "CustomProtocol",
]
