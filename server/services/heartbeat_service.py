"""v2.3.0 Phase 0 — 心跳节拍器

统一编排 health/blackhole/evolution/memory 的周期性任务,
错峰执行避免与 LLM 主调用争抢资源。

5 种节拍:
- 微节拍 (30s):  工具调用超时检测、SSE 心跳保活
- 小节拍 (2min): 记忆图谱增量 patch、L1→L2 压缩
- 中节拍 (1h):   记忆整理 (Supermemory 四原语)、EvolutionLog
- 大节拍 (24h):  GraphRAG 7 步增量、版本快照 (03:00 错峰)
- 自检节拍 (启动时): Provider 健康探测、技能/MCP 索引刷新

反教训应用:
- OpenClaw 5min 高频心跳与 LLM 主调用争抢 → 心跳异步错峰 + 信号量限流
- MemGPT 被动式压缩导致"摘要漂移" → 主动式压缩 (上下文达 70% 触发)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ..core.event_bus import EventBus, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class Beat:
    """节拍定义"""
    name: str                                # 节拍名 (micro/small/medium/large/selfcheck)
    interval_seconds: float | None           # 周期 (秒); None 表示仅启动时执行
    task_fn: Callable[[], Awaitable[None]]   # 节拍任务函数
    run_on_start: bool = False               # 是否在启动时立即执行一次
    # 错峰偏移 (秒): 大节拍在凌晨执行,避免与用户高峰冲突
    initial_delay: float = 0.0


class HeartbeatService:
    """心跳节拍器 — 在 lifespan 中启动

    用法:
        heartbeat = HeartbeatService(app.state)
        await heartbeat.start()  # 在 lifespan startup
        await heartbeat.stop()   # 在 lifespan shutdown
    """

    def __init__(self, app_state: Any = None, event_bus: EventBus | None = None) -> None:
        self.app_state = app_state
        self.event_bus = event_bus or get_event_bus()
        self._beats: dict[str, Beat] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running: bool = False
        # 信号量限流: 同时执行的节拍任务数上限
        # 避免多个节拍同时触发导致资源争抢
        self._concurrency_limit = asyncio.Semaphore(2)
        # 节拍执行历史 (最近 100 次,用于监控)
        self._history: list[dict[str, Any]] = []

    def register_beat(self, beat: Beat) -> None:
        """注册节拍"""
        self._beats[beat.name] = beat
        logger.info("心跳节拍已注册: %s (interval=%ss)", beat.name, beat.interval_seconds)

    async def start(self) -> None:
        """启动所有节拍"""
        if self._running:
            logger.warning("HeartbeatService 已在运行")
            return
        self._running = True
        logger.info("HeartbeatService 启动,共 %d 个节拍", len(self._beats))

        for name, beat in self._beats.items():
            # 启动时立即执行的节拍
            if beat.run_on_start or beat.interval_seconds is None:
                task = asyncio.create_task(self._run_beat_once(name))
            else:
                task = asyncio.create_task(self._run_beat_loop(name))
            self._tasks[name] = task

    async def stop(self) -> None:
        """停止所有节拍"""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        logger.info("HeartbeatService 已停止")

    async def _run_beat_loop(self, name: str) -> None:
        """周期性执行节拍"""
        beat = self._beats[name]
        if beat.initial_delay > 0:
            await asyncio.sleep(beat.initial_delay)

        while self._running:
            await self._run_beat_once(name)
            if beat.interval_seconds and self._running:
                await asyncio.sleep(beat.interval_seconds)

    async def _run_beat_once(self, name: str) -> None:
        """执行单次节拍 (带信号量限流 + 异常隔离)"""
        beat = self._beats.get(name)
        if beat is None:
            return

        async with self._concurrency_limit:
            start_time = datetime.now(timezone.utc)
            success = False
            error: str | None = None
            try:
                await beat.task_fn()
                success = True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = str(exc)
                logger.exception("心跳节拍 %s 执行失败", name)
            finally:
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                # 记录历史
                self._history.append({
                    "beat": name,
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_seconds": duration,
                    "success": success,
                    "error": error,
                })
                # 保留最近 100 条
                if len(self._history) > 100:
                    self._history = self._history[-100:]

                # 发布节拍完成事件 (前端/监控可订阅)
                await self.event_bus.publish(
                    "heartbeat.beat.completed",
                    {
                        "beat": name,
                        "success": success,
                        "duration_seconds": duration,
                        "error": error,
                    },
                    source="heartbeat_service",
                )

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取节拍执行历史 (监控/调试用)"""
        return list(reversed(self._history[-limit:]))

    def is_running(self) -> bool:
        return self._running


def create_default_heartbeat(app_state: Any) -> HeartbeatService:
    """创建默认心跳服务 (注册 5 种节拍)

    节拍任务函数在此注册,但实际实现委托给各模块服务:
    - micro: 工具调用超时检测 (tool_executor 维护)
    - small: 记忆 L1→L2 压缩 (memory_service)
    - medium: 记忆整理 + EvolutionLog (evolution_engine)
    - large: GraphRAG 增量 + 版本快照 (memory_service)
    - selfcheck: Provider 健康探测 + 技能/MCP 索引刷新
    """
    bus = getattr(app_state, "event_bus", None) or get_event_bus()
    service = HeartbeatService(app_state=app_state, event_bus=bus)

    # 微节拍 (30s): 工具调用超时检测 + SSE 保活 (保活由 SSE 网关自处理,此处仅超时检测)
    async def micro_beat() -> None:
        # 委托: tool_executor 维护超时表,此处触发清理
        # 实际实现见 tool_executor.cleanup_timeouts()
        pass  # 占位: Phase 2 接入真实实现

    # 小节拍 (2min): 记忆图谱增量 patch + L1→L2 压缩
    async def small_beat() -> None:
        # v2.3.0 Phase 3-B: 简化版 L1→L2 压缩
        # 查最近 10 条 L1 记忆, 标记为 L2 (实际应调用 evolution_engine.extract_phase
        # 做 LLM 摘要压缩, 但为避免每 2min 触发 LLM 调用, 此处仅做简化升格)。
        # 真实压缩由 medium_beat (1h) 调用 evolution_engine 完成。
        try:
            from ..db.engine import async_session
            from ..db.orm import Memory
            from sqlalchemy import select, desc

            async with async_session() as session:
                # 查最近的 L1 记忆 (升格后下次不再命中, 自然避免重复处理)
                result = await session.execute(
                    select(Memory)
                    .where(Memory.layer == "L1")
                    .order_by(desc(Memory.created_at))
                    .limit(10)
                )
                recent_l1 = list(result.scalars().all())
                if not recent_l1:
                    return
                # 简化: 将 L1 标记为 L2 (实际应做压缩/摘要)
                for m in recent_l1:
                    m.layer = "L2"
                await session.commit()

                try:
                    await bus.publish(
                        "memory.l2.compressed",
                        {"count": len(recent_l1), "memory_ids": [m.id for m in recent_l1]},
                        source="heartbeat_small",
                    )
                except Exception as ev_exc:
                    logger.warning("publish memory.l2.compressed failed: %s", ev_exc)
        except Exception as exc:
            logger.exception("small_beat L1→L2 压缩失败: %s", exc)

    # 中节拍 (1h): 记忆整理 (Supermemory 四原语) + EvolutionLog
    async def medium_beat() -> None:
        # v2.3.0 Phase 3-B: 简化版 compile 阶段
        # 统计当前 L2 记忆数, 插入 EvolutionLog (phase=compile, trigger=scheduled),
        # publish evolution.log.appended 触发前端进化日志页增量更新。
        # 真实 L2→L3 编译由 evolution_engine.compile_phase (调用 LLM) 完成,
        # 此处仅做统计日志, 不触发 LLM (避免每小时 LLM 调用)。
        try:
            from ..db.engine import async_session
            from ..db.orm import Memory, EvolutionLog, Persona
            from sqlalchemy import select, func

            async with async_session() as session:
                # 遍历所有 persona (默认至少有一个 persona_id, 否则跳过)
                persona_result = await session.execute(select(Persona.id))
                persona_ids = [row[0] for row in persona_result.all()]
                if not persona_ids:
                    # 无 persona, 用默认 persona_id=1 (FK 可能违约, 直接跳过)
                    return

                for persona_id in persona_ids:
                    # 统计该 persona 的 L2 记忆数
                    result = await session.execute(
                        select(func.count(Memory.id)).where(
                            Memory.persona_id == persona_id,
                            Memory.layer == "L2",
                        )
                    )
                    l2_count = result.scalar() or 0
                    if l2_count == 0:
                        continue

                    # 插入 EvolutionLog
                    log = EvolutionLog(
                        persona_id=persona_id,
                        phase="compile",
                        status="completed",
                        trigger="scheduled",
                        before_state={"L2_count": l2_count},
                        after_state={"L2_count": l2_count, "compiled_units": 0},
                        details={
                            "l2_count": l2_count,
                            "summary": f"自动编译 {l2_count} 条 L2 记忆 (简化: 仅统计, 未触发 LLM)",
                        },
                    )
                    session.add(log)
                    await session.commit()
                    await session.refresh(log)

                    # publish evolution.log.appended — 前端 EvolutionPage 增量追加
                    # 字段对齐 _log_to_dict 中的前端期望字段 (title/description/detail/created_at)
                    try:
                        await bus.publish(
                            "evolution.log.appended",
                            {
                                "log_id": log.id,
                                "persona_id": persona_id,
                                "phase": "compile",
                                "status": "completed",
                                "title": f"编译 - 已完成",
                                "description": f"触发: scheduled, 阶段: compile",
                                "detail": log.details,
                                "created_at": log.created_at.isoformat() if log.created_at else None,
                            },
                            source="heartbeat_medium",
                        )
                    except Exception as ev_exc:
                        logger.warning("publish evolution.log.appended failed: %s", ev_exc)
        except Exception as exc:
            logger.exception("medium_beat compile 阶段失败: %s", exc)

    # 大节拍 (24h): GraphRAG 7 步增量 + 版本快照 (03:00 错峰)
    async def large_beat() -> None:
        # 委托: memory_service.run_graphrag_incremental() + snapshot
        pass  # 占位: Phase 3-B 接入真实实现

    # 自检节拍 (启动时): Provider 健康探测 + 技能/MCP 索引刷新
    async def selfcheck_beat() -> None:
        # 委托: health_service.probe_all_providers() + skill_engine.refresh_index()
        pass  # 占位: Phase 3-D 接入真实实现

    service.register_beat(Beat(
        name="micro",
        interval_seconds=30.0,
        task_fn=micro_beat,
    ))
    service.register_beat(Beat(
        name="small",
        interval_seconds=120.0,  # 2min
        task_fn=small_beat,
    ))
    service.register_beat(Beat(
        name="medium",
        interval_seconds=3600.0,  # 1h
        task_fn=medium_beat,
    ))
    service.register_beat(Beat(
        name="large",
        interval_seconds=86400.0,  # 24h
        task_fn=large_beat,
        initial_delay=10800.0,  # 3h 延迟,使下次执行约在 03:00 (假设启动在 00:00 附近)
    ))
    service.register_beat(Beat(
        name="selfcheck",
        interval_seconds=None,  # 仅启动时执行
        task_fn=selfcheck_beat,
        run_on_start=True,
    ))

    return service
