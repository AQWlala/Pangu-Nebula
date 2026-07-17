"""v2.3.0 Phase 3-C — 社区技能/MCP 注册表客户端

多源索引 + 搜索 + 安装, 借鉴:
- agentskills.io: 跨厂商 SKILL.md 标准 (Anthropic Skills 生态)
- Claude Code marketplace.json: 6 种 source 类型 (local/git/github/zip/http/virtual)
- Smithery.ai: MCP 服务器注册事实标准 (3000+ servers)

当前为占位实现 (接口就绪, 返回空/mock 数据), 生产环境应 fetch 各社区 API
并合并结果。占位实现的目的是:
1. 锁定 API 契约, 前端 UI 可先于后端联调
2. 避免无网络/无社区凭据时整个市场功能崩溃
3. 后续接入真实社区 API 时仅需替换 search/install 内部实现
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 社区注册表源 (当前为占位, 实际应 fetch 各社区 API)
_SOURCES = {
    "agentskills": {"name": "agentskills.io", "url": "https://agentskills.io/api/skills"},
    "claude": {"name": "Claude marketplace", "url": "https://claude.ai/api/marketplace"},
    "smithery": {"name": "Smithery", "url": "https://smithery.ai/api/servers"},
}


class CommunityRegistryClient:
    """社区技能/MCP 注册表客户端 — 多源索引 + 搜索 + 安装

    借鉴:
    - agentskills.io 跨厂商 SKILL.md 标准
    - Claude Code marketplace.json (6 种 source 类型)
    - Smithery.ai MCP 注册事实标准
    """

    async def search(self, query: str, source: str = "all", limit: int = 20) -> list[dict]:
        """搜索社区技能/MCP

        Args:
            query: 搜索关键词 (匹配 name/description)
            source: 指定源 ("all" 或 _SOURCES 的 key), 默认全源
            limit: 返回条数上限

        Returns:
            [{"name", "description", "source", "url", "install_type", "stars"}]
            当前为占位实现 (返回空列表), 实际应 fetch 各源 API 并合并结果。
        """
        # 占位: 返回空列表 (避免无网络时崩溃)
        # 生产环境应 fetch 各源 API 并合并结果
        # 示例伪代码:
        #   sources = _SOURCES if source == "all" else {source: _SOURCES[source]}
        #   results = []
        #   for sid, meta in sources.items():
        #       try:
        #           resp = await httpx.get(meta["url"], params={"q": query, "limit": limit})
        #           results.extend(_normalize(resp.json(), sid))
        #       except Exception as e:
        #           logger.warning("社区源 %s fetch 失败: %s", sid, e)
        #   return results[:limit]
        logger.debug("CommunityRegistry.search 占位实现 query=%r source=%s", query, source)
        return []

    async def install(self, skill_url: str, install_type: str = "git") -> dict:
        """安装社区技能

        Args:
            skill_url: 技能资源 URL (git repo / pip package / npm package / registry id)
            install_type: 安装类型, 取值:
                - "git": git clone 到 data/skills/
                - "pip": pip install 到 site-packages
                - "npm": npm install 到 node_modules
                - "registry": 从内置注册表安装

        Returns:
            {"success": bool, "path": str, "error": str | None}
        """
        # 占位实现 — 生产环境应按 install_type 分发到具体安装器
        logger.debug(
            "CommunityRegistry.install 占位实现 skill_url=%r install_type=%s",
            skill_url,
            install_type,
        )
        return {"success": False, "path": "", "error": "社区安装功能尚未实现 (占位)"}

    def list_sources(self) -> list[dict]:
        """列出支持的社区源

        Returns:
            [{"id", "name", "url"}, ...]
        """
        return [{"id": k, **v} for k, v in _SOURCES.items()]


# 模块级单例 — 与 mcp_client/mcp_server 一致的模式
_registry_client = CommunityRegistryClient()


def get_community_registry() -> CommunityRegistryClient:
    """获取社区注册表客户端单例"""
    return _registry_client
