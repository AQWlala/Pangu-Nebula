"""ACP 外部 Agent 适配器 (T3.5)

为常见外部 Agent (Claude Code, Codex, Gemini CLI) 提供统一适配器,
使其能够借用 Pangu Nebula 的记忆系统、蜂群能力与技能系统。

适配器实现统一的 ACPAdapter 接口,实际调用走 ACPService(mock 响应),
不依赖真实外部 API key,便于开发与测试。
"""

from .base import ACPAdapter, ADAPTER_REGISTRY, get_adapter, list_adapters
from .claude_code_adapter import ClaudeCodeAdapter
from .codex_adapter import CodexAdapter
from .gemini_cli_adapter import GeminiCLIAdapter

__all__ = [
    "ACPAdapter",
    "ADAPTER_REGISTRY",
    "get_adapter",
    "list_adapters",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "GeminiCLIAdapter",
]
