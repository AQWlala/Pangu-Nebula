"""Gemini CLI 适配器 (T3.5)

适配 Google Gemini CLI Agent,使其能够调用 Pangu Nebula 的
记忆系统、蜂群能力与技能系统。

实际调用走 ACPService(mock 响应),不依赖真实 Google API key。
"""

from __future__ import annotations

from .base import ACPAdapter, register_adapter


@register_adapter
class GeminiCLIAdapter(ACPAdapter):
    """Google Gemini CLI 适配器

    特性:
    - 完整支持 memory/swarm/skills 三项能力
    - 默认端点指向本地 Gemini CLI
    - 认证 token 可选(开放模式下放行)
    """

    name = "gemini_cli"
    display_name = "Gemini CLI"
    capabilities = ["memory", "swarm", "skills"]
    default_endpoint = "cli://gemini"
    description = "Google Gemini CLI 适配器,支持记忆/蜂群/技能调用"
