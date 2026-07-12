"""Claude Code 适配器 (T3.5)

适配 Anthropic Claude Code CLI Agent,使其能够调用 Pangu Nebula 的
记忆系统、蜂群能力与技能系统。

实际调用走 ACPService(mock 响应),不依赖真实 Anthropic API key。
"""

from __future__ import annotations

from .base import ACPAdapter, register_adapter


@register_adapter
class ClaudeCodeAdapter(ACPAdapter):
    """Claude Code CLI 适配器

    特性:
    - 完整支持 memory/swarm/skills 三项能力
    - 默认端点指向本地 Claude Code CLI
    - 认证 token 可选(开放模式下放行)
    """

    name = "claude_code"
    display_name = "Claude Code"
    capabilities = ["memory", "swarm", "skills"]
    default_endpoint = "cli://claude-code"
    description = "Anthropic Claude Code CLI 适配器,支持记忆/蜂群/技能调用"
