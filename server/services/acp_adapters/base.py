"""ACP 适配器基类 (T3.5)

定义统一的 ACPAdapter 接口,所有外部 Agent 适配器继承此类。
适配器内部通过 ACPService 调用 Pangu Nebula 的能力(mock 响应),
不依赖真实外部 API key。
"""

from __future__ import annotations

from typing import Any

from ..acp_service import ACPService


class ACPAdapter:
    """外部 Agent 适配器基类

    子类需覆盖:
    - name: 适配器标识 (claude_code / codex / gemini_cli)
    - display_name: 展示名称
    - capabilities: 支持的能力列表 ['memory', 'swarm', 'skills']
    - default_endpoint: 默认端点
    - description: 适配器描述
    """

    # 子类必须覆盖
    name: str = "generic"
    display_name: str = "Generic Agent"
    capabilities: list[str] = ["memory", "swarm", "skills"]
    default_endpoint: str | None = None
    description: str = "通用外部 Agent 适配器"

    def __init__(self, service: ACPService | None = None, auth_token: str | None = None):
        """初始化适配器

        - service: 注入的 ACPService 实例(便于测试 mock);默认新建
        - auth_token: 认证 token(可选)
        """
        self._service = service or ACPService()
        self._auth_token = auth_token
        # 注册后获得的 agent_id
        self._agent_id: int | None = None

    # ===== 属性 =====

    @property
    def service(self) -> ACPService:
        """底层 ACPService 实例"""
        return self._service

    @property
    def agent_id(self) -> int | None:
        """已注册的 Agent ID(未注册时为 None)"""
        return self._agent_id

    @property
    def auth_token(self) -> str | None:
        """认证 token"""
        return self._auth_token

    # ===== 注册 =====

    async def register(self, name: str | None = None, endpoint: str | None = None) -> dict:
        """向 Pangu Nebula 注册本适配器

        - name: 自定义名称(默认使用 display_name)
        - endpoint: 自定义端点(默认使用 default_endpoint)
        返回注册后的 Agent 信息(含 id)
        """
        agent = await self._service.register_agent(
            name=name or self.display_name,
            agent_type=self.name,
            endpoint=endpoint or self.default_endpoint,
            capabilities=list(self.capabilities),
            auth_token=self._auth_token,
        )
        self._agent_id = agent.get("id")
        return agent

    # ===== 能力调用 =====

    async def call_memory(self, query: str, action: str = "search") -> dict:
        """调用 Pangu Nebula 记忆系统

        - query: 查询/写入内容
        - action: read/write/search(默认 search)
        """
        self._ensure_registered()
        params: dict[str, Any] = {"auth_token": self._auth_token}
        if action == "read":
            params["memory_id"] = query
        elif action == "write":
            params["title"] = query
            params["content"] = query
            params["layer"] = "L3"
        elif action == "search":
            params["query"] = query
        else:
            params["query"] = query
        return await self._service.call_memory(self._agent_id, action, params)

    async def call_swarm(self, task: str, config: dict | None = None) -> dict:
        """调用 Pangu Nebula 蜂群能力 - 发起蜂群任务

        - task: 蜂群任务目标
        - config: 蜂群配置 {persona_id, worker_count, ...}
        """
        self._ensure_registered()
        cfg = dict(config or {})
        cfg["auth_token"] = self._auth_token
        return await self._service.call_swarm(self._agent_id, task, cfg)

    async def call_skill(self, skill_id: str, input: dict | None = None) -> dict:
        """调用 Pangu Nebula 技能系统

        - skill_id: 技能名称/标识
        - input: 技能输入参数
        """
        self._ensure_registered()
        params = dict(input or {})
        params["auth_token"] = self._auth_token
        return await self._service.call_skill(self._agent_id, skill_id, params)

    # ===== 日志 =====

    async def get_logs(self, limit: int = 100) -> list[dict]:
        """获取本适配器的调用日志"""
        self._ensure_registered()
        return await self._service.get_call_logs(agent_id=self._agent_id, limit=limit)

    # ===== 启用/禁用 =====

    async def enable(self) -> dict:
        """启用本适配器对应的 Agent"""
        self._ensure_registered()
        return await self._service.enable_agent(self._agent_id)

    async def disable(self) -> dict:
        """禁用本适配器对应的 Agent"""
        self._ensure_registered()
        return await self._service.disable_agent(self._agent_id)

    # ===== 元信息 =====

    def info(self) -> dict:
        """返回适配器元信息(不含敏感 token)"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "default_endpoint": self.default_endpoint,
            "description": self.description,
            "agent_id": self._agent_id,
            "registered": self._agent_id is not None,
        }

    # ===== 内部辅助 =====

    def _ensure_registered(self) -> None:
        """确保适配器已注册"""
        if self._agent_id is None:
            raise RuntimeError(
                f"适配器 {self.name} 尚未注册,请先调用 register()"
            )


# ===== 适配器注册表 =====

# 全局适配器注册表: name -> ACPAdapter 子类
ADAPTER_REGISTRY: dict[str, type[ACPAdapter]] = {}


def register_adapter(cls: type[ACPAdapter]) -> type[ACPAdapter]:
    """装饰器:注册适配器到全局注册表"""
    ADAPTER_REGISTRY[cls.name] = cls
    return cls


def get_adapter(name: str, service: ACPService | None = None,
                auth_token: str | None = None) -> ACPAdapter:
    """按名称获取适配器实例

    - name: 适配器标识 (claude_code / codex / gemini_cli)
    - service: 注入的 ACPService(可选)
    - auth_token: 认证 token(可选)
    """
    if name not in ADAPTER_REGISTRY:
        raise KeyError(f"未知适配器: {name},可用: {list(ADAPTER_REGISTRY.keys())}")
    cls = ADAPTER_REGISTRY[name]
    return cls(service=service, auth_token=auth_token)


def list_adapters() -> list[dict]:
    """列出所有已注册适配器的元信息"""
    return [cls(service=None).info() for cls in ADAPTER_REGISTRY.values()]
