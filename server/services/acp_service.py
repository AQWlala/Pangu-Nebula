"""ACP (Agent Communication Protocol) 服务 (T3.4-T3.6)

允许外部 Agent (Claude Code, Codex, Gemini CLI) 借用 Pangu Nebula 的:
- 记忆系统 (读写记忆)
- 蜂群能力 (发起蜂群任务)
- 技能系统 (调用技能)

所有外部调用均记录到 ACPCallLog,便于审计与配额追踪。
当前实现使用 mock 响应(不依赖真实外部服务),便于开发与测试。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from ..db.acp_models import ACPCallLog, ExternalAgent
from ..db.engine import async_session


def _agent_to_dict(agent: ExternalAgent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_type": agent.agent_type,
        "endpoint": agent.endpoint,
        "capabilities": agent.capabilities or [],
        "auth_token": agent.auth_token,
        "enabled": bool(agent.enabled),
        "last_called": agent.last_called.isoformat() if agent.last_called else None,
        "call_count": agent.call_count,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def _log_to_dict(log: ACPCallLog) -> dict:
    return {
        "id": log.id,
        "agent_id": log.agent_id,
        "action": log.action,
        "request": log.request,
        "response": log.response,
        "status": log.status,
        "duration_ms": log.duration_ms,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


class ACPService:
    """Agent Communication Protocol 服务

    允许外部 Agent (Claude Code, Codex, Gemini CLI) 借用 Pangu Nebula 的:
    - 记忆系统 (读写记忆)
    - 蜂群能力 (发起蜂群任务)
    - 技能系统 (调用技能)
    """

    # 支持的 agent_type 白名单
    SUPPORTED_AGENT_TYPES = ("generic", "claude_code", "codex", "gemini_cli")

    # ===== Agent CRUD =====

    async def register_agent(
        self,
        name: str,
        agent_type: str = "generic",
        endpoint: str | None = None,
        capabilities: list[str] | None = None,
        auth_token: str | None = None,
    ) -> dict:
        """注册外部 Agent

        - name: Agent 名称
        - agent_type: generic/claude_code/codex/gemini_cli
        - endpoint: 调用端点(可选)
        - capabilities: 能力声明(可选)
        - auth_token: 认证 token(可选)
        """
        async with async_session() as session:
            agent = ExternalAgent(
                name=name,
                agent_type=agent_type or "generic",
                endpoint=endpoint,
                capabilities=capabilities or [],
                auth_token=auth_token,
                enabled=True,
            )
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
            return _agent_to_dict(agent)

    async def list_agents(self, enabled_only: bool = True) -> list[dict]:
        """列出已注册的外部 Agent"""
        async with async_session() as session:
            stmt = select(ExternalAgent).order_by(ExternalAgent.created_at.desc())
            if enabled_only:
                stmt = stmt.where(ExternalAgent.enabled.is_(True))
            result = await session.execute(stmt)
            return [_agent_to_dict(a) for a in result.scalars().all()]

    async def get_agent(self, agent_id: int) -> dict | None:
        """获取单个 Agent"""
        async with async_session() as session:
            agent = await session.get(ExternalAgent, agent_id)
            return _agent_to_dict(agent) if agent else None

    async def enable_agent(self, agent_id: int) -> dict:
        """启用 Agent"""
        async with async_session() as session:
            agent = await session.get(ExternalAgent, agent_id)
            if agent is None:
                return {"ok": False, "error": "Agent not found"}
            agent.enabled = True
            await session.commit()
            await session.refresh(agent)
            return {"ok": True, "agent": _agent_to_dict(agent)}

    async def disable_agent(self, agent_id: int) -> dict:
        """禁用 Agent"""
        async with async_session() as session:
            agent = await session.get(ExternalAgent, agent_id)
            if agent is None:
                return {"ok": False, "error": "Agent not found"}
            agent.enabled = False
            await session.commit()
            await session.refresh(agent)
            return {"ok": True, "agent": _agent_to_dict(agent)}

    async def delete_agent(self, agent_id: int) -> dict:
        """删除 Agent"""
        async with async_session() as session:
            agent = await session.get(ExternalAgent, agent_id)
            if agent is None:
                return {"ok": False, "error": "Agent not found"}
            await session.delete(agent)
            await session.commit()
            return {"ok": True, "id": agent_id, "deleted": True}

    # ===== ACP 调用 =====

    async def call_memory(
        self, agent_id: int, action: str, params: dict | None = None
    ) -> dict:
        """调用记忆系统

        - action: read/write/search
        - params: {memory_id, layer, title, content, query, ...}
        """
        start = time.time()
        params = params or {}

        # 认证校验
        auth = await self._authenticate(agent_id, params.get("auth_token"))
        if not auth["ok"]:
            await self._log_call(
                agent_id, "call_memory",
                json.dumps({"action": action, "params": params}, ensure_ascii=False),
                json.dumps(auth, ensure_ascii=False), "error",
                int((time.time() - start) * 1000),
            )
            return auth

        # Agent 必须启用
        agent_data = await self.get_agent(agent_id)
        if agent_data is None:
            return {"ok": False, "error": "Agent not found"}
        if not agent_data["enabled"]:
            return {"ok": False, "error": "Agent is disabled"}

        # Mock 响应:不真正调用记忆系统
        response: dict[str, Any]
        if action == "read":
            response = {
                "ok": True,
                "action": "read",
                "memory_id": params.get("memory_id"),
                "content": "[mock memory content]",
                "mock": True,
            }
        elif action == "write":
            response = {
                "ok": True,
                "action": "write",
                "title": params.get("title"),
                "layer": params.get("layer", "L3"),
                "memory_id": 0,  # mock id
                "mock": True,
            }
        elif action == "search":
            response = {
                "ok": True,
                "action": "search",
                "query": params.get("query"),
                "results": [],
                "mock": True,
            }
        else:
            response = {"ok": False, "error": f"Unknown memory action: {action}"}

        duration_ms = int((time.time() - start) * 1000)
        status = "ok" if response.get("ok") else "error"
        await self._log_call(
            agent_id, "call_memory",
            json.dumps({"action": action, "params": params}, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False), status, duration_ms,
        )
        await self._touch_agent(agent_id)
        return response

    async def call_swarm(
        self, agent_id: int, task: str, config: dict | None = None
    ) -> dict:
        """调用蜂群能力 - 发起蜂群任务

        - task: 蜂群任务目标
        - config: {persona_id, worker_count, ...}
        """
        start = time.time()
        config = config or {}

        auth = await self._authenticate(agent_id, config.get("auth_token"))
        if not auth["ok"]:
            await self._log_call(
                agent_id, "call_swarm",
                json.dumps({"task": task, "config": config}, ensure_ascii=False),
                json.dumps(auth, ensure_ascii=False), "error",
                int((time.time() - start) * 1000),
            )
            return auth

        agent_data = await self.get_agent(agent_id)
        if agent_data is None:
            return {"ok": False, "error": "Agent not found"}
        if not agent_data["enabled"]:
            return {"ok": False, "error": "Agent is disabled"}

        # Mock 响应:不真正发起蜂群任务
        response = {
            "ok": True,
            "swarm_id": 0,  # mock id
            "task": task,
            "persona_id": config.get("persona_id"),
            "worker_count": config.get("worker_count", 3),
            "status": "pending",
            "mock": True,
        }

        duration_ms = int((time.time() - start) * 1000)
        await self._log_call(
            agent_id, "call_swarm",
            json.dumps({"task": task, "config": config}, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False), "ok", duration_ms,
        )
        await self._touch_agent(agent_id)
        return response

    async def call_skill(
        self, agent_id: int, skill_name: str, params: dict | None = None
    ) -> dict:
        """调用技能系统

        - skill_name: 技能名称
        - params: 技能参数
        """
        start = time.time()
        params = params or {}

        auth = await self._authenticate(agent_id, params.get("auth_token"))
        if not auth["ok"]:
            await self._log_call(
                agent_id, "call_skill",
                json.dumps({"skill_name": skill_name, "params": params}, ensure_ascii=False),
                json.dumps(auth, ensure_ascii=False), "error",
                int((time.time() - start) * 1000),
            )
            return auth

        agent_data = await self.get_agent(agent_id)
        if agent_data is None:
            return {"ok": False, "error": "Agent not found"}
        if not agent_data["enabled"]:
            return {"ok": False, "error": "Agent is disabled"}

        # Mock 响应:不真正调用技能
        response = {
            "ok": True,
            "skill": skill_name,
            "result": f"[mock skill result for {skill_name}]",
            "mock": True,
        }

        duration_ms = int((time.time() - start) * 1000)
        await self._log_call(
            agent_id, "call_skill",
            json.dumps({"skill_name": skill_name, "params": params}, ensure_ascii=False),
            json.dumps(response, ensure_ascii=False), "ok", duration_ms,
        )
        await self._touch_agent(agent_id)
        return response

    # ===== 调用日志 =====

    async def get_call_logs(
        self, agent_id: int | None = None, limit: int = 100
    ) -> list[dict]:
        """获取调用日志

        - agent_id: 过滤指定 Agent(可选)
        - limit: 返回条数上限
        """
        async with async_session() as session:
            stmt = select(ACPCallLog).order_by(ACPCallLog.created_at.desc()).limit(limit)
            if agent_id is not None:
                stmt = stmt.where(ACPCallLog.agent_id == agent_id)
            result = await session.execute(stmt)
            return [_log_to_dict(log) for log in result.scalars().all()]

    # ===== 内部辅助 =====

    async def _authenticate(self, agent_id: int, token: str | None) -> dict:
        """认证校验

        - 如果 Agent 未设置 auth_token,则放行(开放模式)
        - 如果 Agent 设置了 auth_token,则要求 token 匹配
        """
        async with async_session() as session:
            agent = await session.get(ExternalAgent, agent_id)
            if agent is None:
                return {"ok": False, "error": "Agent not found"}
            if not agent.enabled:
                return {"ok": False, "error": "Agent is disabled"}
            if agent.auth_token:
                if not token or token != agent.auth_token:
                    return {"ok": False, "error": "Authentication failed"}
            return {"ok": True, "agent_id": agent_id}

    async def _log_call(
        self,
        agent_id: int,
        action: str,
        request: str | None,
        response: str | None,
        status: str,
        duration_ms: int,
    ) -> None:
        """记录调用日志"""
        async with async_session() as session:
            log = ACPCallLog(
                agent_id=agent_id,
                action=action,
                request=request,
                response=response,
                status=status,
                duration_ms=duration_ms,
            )
            session.add(log)
            await session.commit()

    async def _touch_agent(self, agent_id: int) -> None:
        """更新 Agent 的最后调用时间和调用次数"""
        async with async_session() as session:
            await session.execute(
                update(ExternalAgent)
                .where(ExternalAgent.id == agent_id)
                .values(
                    last_called=datetime.utcnow(),
                    call_count=ExternalAgent.call_count + 1,
                )
            )
            await session.commit()
