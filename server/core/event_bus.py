"""v2.3.0 Phase 0 — 进程内事件总线

跨模块联动的脊柱:25 类事件通过统一的 publish/subscribe 扇出,
前端经 /events/stream SSE 网关订阅,实现 DAG/记忆/进化/健康等模块的实时联动。

设计要点:
- 进程内 asyncio 广播,无外部 broker (NATS/Redis) 依赖
- 通配符订阅: "memory.*" / "dag.node.*" / "*" (全量)
- 背压保护: 每订阅者 asyncio.Queue maxsize=1024,满则丢弃最旧事件 + 告警
- 三层持久化钩子 (可选):
  * 审计层 (audit_sink): 全量事件落审计日志
  * 状态层 (state_sink): 仅保留最新值 (如 health.*)
  * 业务层 (business_sink): 领域事件落业务表 (如 evolution.log.appended)
- 单调递增 seq,支持 SSE Last-Event-ID 断点续传

借鉴:
- DeerFlow 2.0 的事件驱动编排
- LangGraph 的 interrupt/Checkpoint (通过 dag.node.interrupted 事件触发)
- 反教训: OpenClaw 5min 高频心跳与 LLM 主调用争抢 → 本总线异步扇出不阻塞 publisher
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Awaitable

logger = logging.getLogger(__name__)

# 背压保护: 每订阅者队列上限。满时丢弃最旧事件并告警(避免 OOM)。
_SUBSCRIBER_QUEUE_MAX = 1024


@dataclass(frozen=True)
class Event:
    """总线事件 — 不可变,跨订阅者共享"""
    seq: int                       # 单调递增序号,用于 SSE Last-Event-ID
    event_type: str                # 事件类型,如 "memory.graph.updated"
    payload: dict[str, Any]        # 事件负载
    source: str                    # 发布者标识,如 "chat_service"
    timestamp: str                 # ISO8601 UTC 时间戳

    def to_sse_data(self) -> dict[str, Any]:
        """转换为 SSE data 字段(JSON)"""
        return {
            "seq": self.seq,
            "event_type": self.event_type,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
        }


# 持久化钩子类型: (event) -> Awaitable[None]
# 任一钩子异常不会阻塞总线扇出,仅记录日志
PersistSink = Callable[[Event], Awaitable[None]]


class _Subscriber:
    """订阅者句柄 — 持有一个 asyncio.Queue,EventBus 扇出时 put 入队"""
    __slots__ = ("pattern", "queue", "_dropped_count")

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAX)
        self._dropped_count: int = 0

    def matches(self, event_type: str) -> bool:
        """通配符匹配: "memory.*" 匹配 "memory.graph.updated"; "*" 匹配全部"""
        if self.pattern == "*":
            return True
        if self.pattern.endswith(".*"):
            prefix = self.pattern[:-2]
            return event_type == prefix or event_type.startswith(prefix + ".")
        return event_type == self.pattern

    async def deliver(self, event: Event) -> None:
        """投递事件,队列满时丢弃最旧并告警(背压保护)"""
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # 丢弃最旧事件,腾出空间。丢弃计数用于监控告警。
            try:
                self.queue.get_nowait()
                self._dropped_count += 1
                if self._dropped_count % 100 == 1:
                    logger.warning(
                        "EventBus 订阅者 pattern=%s 队列满,已丢弃 %d 个最旧事件",
                        self.pattern, self._dropped_count,
                    )
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                logger.error("EventBus 投递失败 pattern=%s (队列状态异常)", self.pattern)


class EventBus:
    """进程内事件总线 — 单例,app.state.event_bus

    用法:
        # 发布 (任何服务)
        await app.state.event_bus.publish(
            "memory.graph.updated",
            {"node_id": 42, "action": "create"},
            source="memory_service",
        )
        # 订阅 (SSE 网关 / 内部服务)
        async for event in app.state.event_bus.subscribe("memory.*"):
            ...
    """

    def __init__(
        self,
        audit_sink: PersistSink | None = None,
        state_sink: PersistSink | None = None,
        business_sink: PersistSink | None = None,
    ) -> None:
        self._subscribers: list[_Subscriber] = []
        self._subscribers_lock = asyncio.Lock()
        self._seq: int = 0
        self._seq_lock = asyncio.Lock()
        self.audit_sink = audit_sink
        self.state_sink = state_sink
        self.business_sink = business_sink
        # 已发布事件缓存(用于 SSE Last-Event-ID 断点续传)
        # 环形缓冲,保留最近 N 条,超出则旧事件无法重放
        self._replay_buffer: asyncio.Queue[Event] = asyncio.Queue(maxsize=2048)

    async def publish(self, event_type: str, payload: dict[str, Any], source: str) -> Event:
        """发布事件 — 扇出所有匹配订阅者,触发持久化钩子

        持久化钩子异常不阻塞扇出(仅记录日志),保证发布者不被拖慢。
        """
        async with self._seq_lock:
            self._seq += 1
            seq = self._seq
        event = Event(
            seq=seq,
            event_type=event_type,
            payload=payload,
            source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 写入重放缓冲(用于 SSE 重连断点续传)。缓冲满时丢弃最旧。
        try:
            self._replay_buffer.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._replay_buffer.get_nowait()
                self._replay_buffer.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

        # 持久化钩子 (并行触发,任一异常不阻塞)
        await self._trigger_sinks(event)

        # 扇出到匹配订阅者 (快照订阅者列表,避免遍历时增删)
        # 复制列表避免遍历期间订阅/取消订阅导致并发修改
        subscribers_snapshot = list(self._subscribers)
        for sub in subscribers_snapshot:
            if sub.matches(event_type):
                try:
                    await sub.deliver(event)
                except Exception:
                    logger.exception("EventBus 投递异常 pattern=%s", sub.pattern)

        return event

    async def _trigger_sinks(self, event: Event) -> None:
        """触发三层持久化钩子,任一异常不阻塞"""
        for sink_name, sink in (
            ("audit", self.audit_sink),
            ("state", self.state_sink),
            ("business", self.business_sink),
        ):
            if sink is None:
                continue
            try:
                await sink(event)
            except Exception:
                logger.exception("EventBus %s_sink 异常 event_type=%s", sink_name, event.event_type)

    async def subscribe(self, pattern: str) -> AsyncIterator[Event]:
        """订阅事件 — 返回异步迭代器

        pattern 支持:
        - 精确: "memory.graph.updated"
        - 前缀通配: "memory.*" / "dag.node.*"
        - 全量: "*"

        调用方迭代此返回值,取消迭代(离开 async for)时自动注销订阅。
        """
        sub = _Subscriber(pattern)
        async with self._subscribers_lock:
            self._subscribers.append(sub)
        try:
            while True:
                # 阻塞等待下一个事件。调用方取消迭代时,GeneratorExit 触发 finally。
                event = await sub.queue.get()
                yield event
        finally:
            async with self._subscribers_lock:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)

    def replay_since(self, last_seq: int, pattern: str) -> list[Event]:
        """重放 last_seq 之后的所有匹配事件 (用于 SSE Last-Event-ID 断点续传)

        注意: 仅能重放缓冲区内的事件(最近 2048 条)。更早的事件无法重放。
        """
        result: list[Event] = []
        # asyncio.Queue 不支持遍历,转换为 list 快照
        # (重连频率低,性能可接受)
        try:
            snapshot = list(self._replay_buffer._queue)  # type: ignore[attr-defined]
        except AttributeError:
            # 某些 Python 版本 asyncio.Queue 内部实现不同,fallback 到空列表
            snapshot = []
        for event in snapshot:
            if event.seq > last_seq:
                # 用临时 _Subscriber 复用匹配逻辑
                tmp = _Subscriber(pattern)
                if tmp.matches(event.event_type):
                    result.append(event)
        return result

    def subscriber_count(self) -> int:
        """当前活跃订阅者数 (监控/调试用)"""
        return len(self._subscribers)

    def next_seq(self) -> int:
        """当前 seq (测试用)"""
        return self._seq


# 模块级单例 — 在 lifespan 中创建并挂到 app.state.event_bus
# 此处保留一个全局回退实例,供非 FastAPI 上下文(如后台任务)使用
_global_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线单例

    优先返回 app.state.event_bus (FastAPI 上下文),
    否则返回模块级单例(后台任务/测试场景)。
    """
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def set_global_event_bus(bus: EventBus) -> None:
    """设置全局事件总线 (lifespan 启动时调用)"""
    global _global_bus
    _global_bus = bus
