"""v2.3.0 Phase 2 — 跨模块联动协调器 (后端消费端)

EventBus 已建立 publish 侧 (41 处调用),但 subscribe 侧缺乏"联动消费"逻辑。
本模块创建统一的 LinkageCoordinator,在应用启动时注册所有跨模块联动消费者,
把孤立的模块信号 (健康检查/工具调用/MCP/委派/DAG) 串成自适应联动链路。

设计原则:
- 每条链路独立 asyncio.Task,互不影响
- 容错: 单条 handler 异常仅 log warning,不传播 (其他链路 + 同链路后续事件不受影响)
- 可观测: logger 记录关键决策点 (info) 与异常 (warning)
- 不阻断: 联动仅发事件/记日志,真正动作由各模块在调用点自行决定
  (如 DelegationGuard.can_delegate 在调用点阻断, 此处仅审计告警)

已实现链路:
- 链路 1: health.provider.toggled  → persona.delegated        (健康失败 → 角色切换提示)
- 链路 3: chat.tool.call.completed  → health.check.requested  (工具连续失败 → 触发健康检查)
- 链路 4: mcp.health.failed         → mcp.disconnected        (MCP 连续失败 → 自动断开通知)
- 链路 5: persona.delegated         → persona.delegation.blocked (委派链路审计 + 越界告警)
- 链路 6: dag.node.failed           → GraphExecutor.interrupt (DAG 节点失败 → 中断整个 DAG)
- 链路 7: chat.message.completed    → evolution.log.appended  (对话累计阈值 → 触发进化日志建议)
- 链路 8: skill.enabled.toggled     → swarm.refresh.requested (技能启停 → 通知蜂群刷新)

注: 缺链路 2 (前端联动), 后端消费端不注册该链路。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from ..core.event_bus import EventBus, Event

logger = logging.getLogger(__name__)


class LinkageCoordinator:
    """跨模块联动协调器 — 注册并运行所有后端联动消费者

    用法 (main.py lifespan):
        linkage = LinkageCoordinator(event_bus=event_bus, session_factory=async_session)
        await linkage.start()
        # ... shutdown ...
        await linkage.stop()
    """

    # v2.3.1 P1-8: 委派深度上限 (从硬编码 magic number 提取为类常量)
    # 链路 5 中 depth > _MAX_DELEGATION_DEPTH → 发布 persona.delegation.blocked
    _MAX_DELEGATION_DEPTH: int = 3

    def __init__(
        self,
        event_bus: EventBus,
        session_factory: Any | None = None,
        graph_executor: Any | None = None,
    ) -> None:
        self.event_bus = event_bus
        # async_sessionmaker, 用于链路 1 查询依赖被关闭 provider 的 persona
        self.session_factory = session_factory
        # GraphExecutor 实例, 用于链路 6 调用 interrupt(dag)
        # 若为 None (main.py 无全局实例), 链路 6 降级为 log-only
        self.graph_executor = graph_executor
        self._tasks: list[asyncio.Task] = []
        # 链路 3: persona_id -> 连续工具调用失败数
        self._tool_fail_streak: dict[int, int] = {}
        # 链路 4: server_name -> 连续 MCP 健康检查失败数
        self._mcp_fail_streak: dict[str, int] = {}
        # 链路 7: persona_id -> 对话完成累计数 (达阈值触发进化日志)
        self._chat_complete_count: dict[int, int] = {}
        self._stopped: bool = False

    async def start(self) -> None:
        """注册所有联动消费者 (每个消费者一个独立 asyncio.Task)"""
        self._stopped = False
        self._tasks = [
            asyncio.create_task(
                self._linkage_health_to_persona(), name="linkage-health-persona"
            ),
            asyncio.create_task(
                self._linkage_tool_timeout_to_health(), name="linkage-tool-health"
            ),
            asyncio.create_task(
                self._linkage_mcp_health_to_disconnect(), name="linkage-mcp-health"
            ),
            asyncio.create_task(
                self._linkage_persona_delegation_audit(), name="linkage-delegation-audit"
            ),
            asyncio.create_task(
                self._linkage_dag_failure_to_interrupt(), name="linkage-dag-interrupt"
            ),
            asyncio.create_task(
                self._linkage_chat_to_evolution(), name="linkage-chat-evolution"
            ),
            asyncio.create_task(
                self._linkage_skill_to_swarm(), name="linkage-skill-swarm"
            ),
        ]
        logger.info(
            "LinkageCoordinator 已启动, 注册 %d 条联动消费者", len(self._tasks)
        )

    async def stop(self) -> None:
        """停止所有联动消费者 (取消任务并等待清理)"""
        self._stopped = True
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("LinkageCoordinator 已停止")

    async def _consume(
        self, pattern: str, handler: Callable[[Event], Awaitable[None]]
    ) -> None:
        """通用消费循环: 订阅 pattern, 对每个 event 调用 handler, 容错

        - 单个 event 处理异常仅 log warning, 不退出循环 (后续事件继续消费)
        - stop() 取消任务时, async for 抛出 CancelledError 自然退出
        """
        try:
            async for event in self.event_bus.subscribe(pattern):
                if self._stopped:
                    return
                try:
                    await handler(event)
                except Exception as e:
                    logger.warning(
                        "联动处理失败 pattern=%s event=%s err=%s",
                        pattern,
                        event.event_type,
                        e,
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            # 正常停止路径: stop() 取消任务
            raise

    # ===== 链路 1: 健康检查 → 角色自动切换 (提示) =====

    async def _linkage_health_to_persona(self) -> None:
        """当某 provider 被关闭 (enabled=False), 查找依赖该 provider 的 persona,
        publish persona.delegated 事件供前端提示 (不真正切换角色)。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            provider = payload.get("provider")
            enabled = payload.get("enabled")
            # 仅当 provider 被关闭 (enabled is False) 时触发
            if enabled is not False or not provider:
                return

            affected = await self._find_personas_by_provider(provider)
            if not affected:
                logger.debug(
                    "provider=%s 被关闭, 但无 persona 依赖它", provider
                )
                return

            logger.info(
                "链路1: provider=%s 被关闭, 触发 %d 个角色的 failover 提示",
                provider,
                len(affected),
            )
            for persona_id in affected:
                try:
                    await self.event_bus.publish(
                        "persona.delegated",
                        {
                            "from_persona_id": persona_id,
                            "to_persona_id": None,  # 不真正切换, 无目标角色
                            "reason": "health_failover",
                            "provider": provider,
                        },
                        source="linkage_coordinator",
                    )
                except Exception:
                    logger.warning(
                        "链路1: publish persona.delegated 失败 persona_id=%s",
                        persona_id,
                        exc_info=True,
                    )

        await self._consume("health.provider.toggled", handler)

    async def _find_personas_by_provider(self, provider: str) -> list[int]:
        """查询 DB 中 model_provider == provider 的 persona id 列表

        容错: session_factory 为 None 或查询失败时返回空列表 (仅 log warning)
        """
        if self.session_factory is None:
            logger.debug("session_factory 未配置, 跳过 persona 查询 provider=%s", provider)
            return []
        try:
            from sqlalchemy import select
            from ..db.orm import Persona

            async with self.session_factory() as session:
                result = await session.execute(
                    select(Persona.id).where(Persona.model_provider == provider)
                )
                return [int(row[0]) for row in result.all()]
        except Exception:
            logger.warning(
                "查询依赖 provider=%s 的 persona 失败", provider, exc_info=True
            )
            return []

    # ===== 链路 3: 工具调用超时 → 健康检查触发 =====

    async def _linkage_tool_timeout_to_health(self) -> None:
        """累计每个 persona 的工具调用连续失败数, 连续 3 次失败 →
        publish health.check.requested 触发该 persona 对应 provider 的健康检查。

        注意: chat.tool.call.completed 的 payload 当前不含 persona_id 字段,
        需用 payload.get("persona_id") 安全获取; 缺失时跳过计数 (无法归因)。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            persona_id = payload.get("persona_id")
            success = payload.get("success")

            # 无 persona_id 无法按角色计数, 跳过 (不报错)
            if persona_id is None:
                return
            try:
                pid = int(persona_id)
            except (TypeError, ValueError):
                logger.debug("链路3: persona_id 不可转 int: %s", persona_id)
                return

            if success is True:
                # 成功: 重置连续失败计数
                self._tool_fail_streak.pop(pid, None)
                return

            # 失败 (success is False 或缺失均视为失败)
            count = self._tool_fail_streak.get(pid, 0) + 1
            self._tool_fail_streak[pid] = count

            if count == 3:
                logger.info(
                    "链路3: persona_id=%s 工具调用连续失败 %d 次, 触发健康检查",
                    pid,
                    count,
                )
                try:
                    await self.event_bus.publish(
                        "health.check.requested",
                        {
                            "persona_id": pid,
                            "reason": "tool_timeout_streak",
                            "count": count,
                        },
                        source="linkage_coordinator",
                    )
                except Exception:
                    logger.warning(
                        "链路3: publish health.check.requested 失败 persona_id=%s",
                        pid,
                        exc_info=True,
                    )
            else:
                logger.debug(
                    "链路3: persona_id=%s 工具调用失败计数=%d", pid, count
                )

        await self._consume("chat.tool.call.completed", handler)

    # ===== 链路 4: MCP 健康失败 → 自动禁用 + 通知 =====

    async def _linkage_mcp_health_to_disconnect(self) -> None:
        """累计同一 server_name 的 MCP 健康检查失败次数, 3 次后
        publish mcp.disconnected 事件 (自动断开通知) 并重置计数。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            server_name = payload.get("server_name")
            if not server_name:
                logger.debug("链路4: mcp.health.failed 缺少 server_name, 跳过")
                return

            count = self._mcp_fail_streak.get(server_name, 0) + 1

            if count >= 3:
                logger.info(
                    "链路4: server_name=%s MCP 健康检查连续失败 %d 次, 触发自动断开通知",
                    server_name,
                    count,
                )
                try:
                    await self.event_bus.publish(
                        "mcp.disconnected",
                        {
                            "server_name": server_name,
                            "reason": "health_check_streak",
                            "count": count,
                        },
                        source="linkage_coordinator",
                    )
                except Exception:
                    logger.warning(
                        "链路4: publish mcp.disconnected 失败 server_name=%s",
                        server_name,
                        exc_info=True,
                    )
                # 重置计数, 避免持续告警
                self._mcp_fail_streak.pop(server_name, None)
            else:
                self._mcp_fail_streak[server_name] = count
                logger.debug(
                    "链路4: server_name=%s MCP 健康检查失败计数=%d",
                    server_name,
                    count,
                )

        await self._consume("mcp.health.failed", handler)

    # ===== 链路 5: 角色委派 → 委派深度守卫审计 =====

    async def _linkage_persona_delegation_audit(self) -> None:
        """审计 persona.delegated 事件: 记录委派链路到 logger (info),
        若 payload 中 depth > _MAX_DELEGATION_DEPTH (超过 MAX_DELEGATION_DEPTH), publish
        persona.delegation.blocked 事件 (越界告警)。

        纯审计 + 越界告警, 不阻断 (阻断由 DelegationGuard.can_delegate 在调用点做)。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            persona_id = payload.get("persona_id")
            depth = payload.get("depth", 0)
            max_depth = payload.get("max_depth")

            logger.info(
                "链路5: 委派审计 persona_id=%s depth=%s max_depth=%s",
                persona_id,
                depth,
                max_depth,
            )

            try:
                depth_val = int(depth)
            except (TypeError, ValueError):
                depth_val = 0

            if depth_val > self._MAX_DELEGATION_DEPTH:
                logger.warning(
                    "链路5: 委派深度越界 persona_id=%s depth=%s (>%s), 发布阻断告警",
                    persona_id,
                    depth,
                    self._MAX_DELEGATION_DEPTH,
                )
                blocked_payload = dict(payload)
                blocked_payload["reason"] = "max_depth_exceeded"
                try:
                    await self.event_bus.publish(
                        "persona.delegation.blocked",
                        blocked_payload,
                        source="linkage_coordinator",
                    )
                except Exception:
                    logger.warning(
                        "链路5: publish persona.delegation.blocked 失败 persona_id=%s",
                        persona_id,
                        exc_info=True,
                    )

        await self._consume("persona.delegated", handler)

    # ===== 链路 6: DAG 节点失败 → 自动 interrupt =====

    async def _linkage_dag_failure_to_interrupt(self) -> None:
        """订阅 dag.node.failed: 获取 dag_id, 查找对应活跃 DAG 实例,
        调用 GraphExecutor.interrupt(dag) 中断后续节点。

        降级: 若 graph_executor 为 None (main.py 无全局实例), 仅 log debug;
        若 DAG 实例不在活跃注册表中 (可能已结束), 仅 log debug。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            dag_id = payload.get("dag_id")
            if not dag_id:
                logger.debug("链路6: dag.node.failed 缺少 dag_id, 跳过")
                return

            if self.graph_executor is None:
                logger.debug(
                    "链路6: graph_executor 未配置, 跳过 interrupt dag_id=%s",
                    dag_id,
                )
                return

            # 防御性获取 _active_dags 注册表 (若 GraphExecutor 未提供则视为空)
            active_dags: dict[str, Any] = getattr(
                self.graph_executor, "_active_dags", {}
            )
            dag = active_dags.get(dag_id)
            if dag is None:
                logger.debug(
                    "链路6: dag_id=%s 不在活跃注册表中 (可能已结束), 跳过 interrupt",
                    dag_id,
                )
                return

            try:
                self.graph_executor.interrupt(dag)
                logger.info(
                    "链路6: dag_id=%s 节点失败, 已请求中断整个 DAG", dag_id
                )
            except Exception:
                logger.warning(
                    "链路6: interrupt dag_id=%s 失败", dag_id, exc_info=True
                )

        await self._consume("dag.node.failed", handler)

    # ===== 链路 7: 对话完成 → 进化日志触发 =====

    _EVOLUTION_CHAT_THRESHOLD = 10
    """链路 7: persona 累计对话完成数达此阈值时触发一次进化日志记录"""

    async def _linkage_chat_to_evolution(self) -> None:
        """累计每个 persona 的对话完成数, 达阈值 (_EVOLUTION_CHAT_THRESHOLD) →
        publish evolution.log.appended 事件 (trigger="chat_threshold"),
        并重置该 persona 的计数。

        设计: 阈值触发而非每次触发, 避免进化日志爆炸; 真正的进化逻辑由
        EvolutionEngine 在 heartbeat medium_beat 中定期执行, 此处仅发"建议"信号。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            persona_id = payload.get("persona_id")
            if persona_id is None:
                return
            try:
                pid = int(persona_id)
            except (TypeError, ValueError):
                logger.debug("链路7: persona_id 不可转 int: %s", persona_id)
                return

            count = self._chat_complete_count.get(pid, 0) + 1

            if count >= self._EVOLUTION_CHAT_THRESHOLD:
                logger.info(
                    "链路7: persona_id=%s 对话完成累计 %d 次, 触发进化日志建议",
                    pid,
                    count,
                )
                try:
                    await self.event_bus.publish(
                        "evolution.log.appended",
                        {
                            "persona_id": pid,
                            "trigger": "chat_threshold",
                            "count": count,
                            "suggestion": "consider_reflection",
                        },
                        source="linkage_coordinator",
                    )
                except Exception:
                    logger.warning(
                        "链路7: publish evolution.log.appended 失败 persona_id=%s",
                        pid,
                        exc_info=True,
                    )
                # 重置计数, 避免持续告警
                self._chat_complete_count.pop(pid, None)
            else:
                self._chat_complete_count[pid] = count
                logger.debug(
                    "链路7: persona_id=%s 对话完成计数=%d", pid, count
                )

        await self._consume("chat.message.completed", handler)

    # ===== 链路 8: 技能启停 → 蜂群刷新通知 =====

    async def _linkage_skill_to_swarm(self) -> None:
        """订阅 skill.enabled.toggled: 当技能被启用/禁用时, publish
        swarm.refresh.requested 事件, 通知蜂群重新加载技能配置。

        设计: 纯转发通知, 不直接操作蜂群 (蜂群在下次编排时自行读取最新技能列表)。
        """

        async def handler(event: Event) -> None:
            payload = event.payload or {}
            skill_id = payload.get("skill_id")
            enabled = payload.get("enabled")

            logger.info(
                "链路8: 技能 %s 状态变更 (enabled=%s), 通知蜂群刷新",
                skill_id,
                enabled,
            )
            try:
                await self.event_bus.publish(
                    "swarm.refresh.requested",
                    {
                        "skill_id": skill_id,
                        "enabled": enabled,
                        "reason": "skill_toggled",
                    },
                    source="linkage_coordinator",
                )
            except Exception:
                logger.warning(
                    "链路8: publish swarm.refresh.requested 失败 skill_id=%s",
                    skill_id,
                    exc_info=True,
                )

        await self._consume("skill.enabled.toggled", handler)
