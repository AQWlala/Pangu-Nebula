"""v2.3.0 Phase 0 — 统一 SSE 网关

前端通过单一 EventSource 连接订阅所有模块事件,替代各组件各自轮询。
支持 Last-Event-ID 断点续传 + 15s 心跳保活。

路由:
    GET /events/stream?patterns=memory.*,dag.node.*,&last_event_id=<seq>

前端用法:
    const es = new EventSource('/events/stream?patterns=memory.*,dag.node.*')
    es.onmessage = (e) => {
        const data = JSON.parse(e.data)
        // data.seq / data.event_type / data.payload / data.source / data.timestamp
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..core.event_bus import EventBus, get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

# SSE 心跳间隔(秒)— 保持连接活跃,防止代理/防火墙超时断开
_SSE_HEARTBEAT_INTERVAL = 15


def _parse_patterns(raw: str) -> list[str]:
    """解析 patterns 查询参数 — 逗号分隔,去空白,去重保序"""
    seen: set[str] = set()
    result: list[str] = []
    for p in raw.split(","):
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


@router.get("/stream", summary="统一事件流(SSE)", description="订阅事件总线,通过 Server-Sent Events 实时推送匹配事件")
async def event_stream(
    request: Request,
    patterns: str = Query("*", description="订阅模式,逗号分隔。如 'memory.*,dag.node.*'。默认 '*' 全量"),
    last_event_id: int | None = Query(None, alias="last_event_id", description="上次收到的最大 seq,用于断点续传"),
):
    """统一 SSE 事件流

    - patterns: 逗号分隔的订阅模式,支持通配符 (memory.* / dag.node.* / *)
    - last_event_id: 断点续传,重放此 seq 之后的事件(仅限缓冲区内)
    - 每 15s 发送心跳注释 (: heartbeat) 保持连接活跃
    """
    bus: EventBus = getattr(request.app.state, "event_bus", None) or get_event_bus()
    pattern_list = _parse_patterns(patterns)
    if not pattern_list:
        pattern_list = ["*"]

    async def stream():
        # 1. 断点续传: 重放 last_event_id 之后的事件
        if last_event_id is not None and last_event_id > 0:
            replayed: dict[str, list[Any]] = {}  # pattern -> events
            for pattern in pattern_list:
                events = bus.replay_since(last_event_id, pattern)
                if events:
                    replayed[pattern] = events
            # 去重 (同一事件可能被多个 pattern 匹配)
            seen_seq: set[int] = set()
            merged: list = []
            for events in replayed.values():
                for ev in events:
                    if ev.seq not in seen_seq:
                        seen_seq.add(ev.seq)
                        merged.append(ev)
            merged.sort(key=lambda e: e.seq)
            for ev in merged:
                # 客户端断开检查
                if await request.is_disconnected():
                    return
                yield f"id: {ev.seq}\nevent: {ev.event_type}\ndata: {json.dumps(ev.to_sse_data(), ensure_ascii=False)}\n\n"

        # 2. 为每个 pattern 创建订阅 (并发订阅多个 pattern)
        #    使用 asyncio.Queue 汇聚多个订阅的事件,保证顺序
        merged_queue: asyncio.Queue = asyncio.Queue(maxsize=4096)
        active_subscriptions: list[asyncio.Task] = []

        async def pump_subscription(pattern: str) -> None:
            try:
                async for event in bus.subscribe(pattern):
                    try:
                        merged_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        # 汇聚队列满,丢弃最旧(背压保护)
                        try:
                            merged_queue.get_nowait()
                            merged_queue.put_nowait(event)
                        except (asyncio.QueueEmpty, asyncio.QueueFull):
                            logger.warning("SSE 汇聚队列满,丢弃事件 seq=%d", event.seq)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("SSE 订阅 pump 异常 pattern=%s", pattern)

        for pattern in pattern_list:
            task = asyncio.create_task(pump_subscription(pattern))
            active_subscriptions.append(task)

        try:
            while True:
                # 客户端断开检查 + 心跳保活
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(merged_queue.get(), timeout=_SSE_HEARTBEAT_INTERVAL)
                    yield f"id: {event.seq}\nevent: {event.event_type}\ndata: {json.dumps(event.to_sse_data(), ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 心跳保活: 发送注释行,保持连接
                    yield ": heartbeat\n\n"
        finally:
            for task in active_subscriptions:
                task.cancel()
            # 等待所有订阅任务取消完成
            if active_subscriptions:
                await asyncio.gather(*active_subscriptions, return_exceptions=True)
            logger.info("SSE 连接关闭 patterns=%s", pattern_list)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx: 禁用缓冲,确保实时推送
        },
    )


@router.get("/stats", summary="事件总线统计", description="返回当前订阅者数、seq 等(调试用)")
async def event_stats(request: Request):
    bus: EventBus = getattr(request.app.state, "event_bus", None) or get_event_bus()
    return {
        "ok": True,
        "data": {
            "subscriber_count": bus.subscriber_count(),
            "last_seq": bus.next_seq(),
        },
        "error": None,
    }
