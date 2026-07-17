"""v2.3.0 Phase 0 — EventBus 单元测试

覆盖:
1. publish/subscribe 基本收发
2. 通配符订阅 ("*" / "memory.*" / 精确匹配)
3. replay_since 断点续传
4. seq 单调递增
5. 多订阅者广播
6. 订阅者自动注销 (task 取消后)
7. payload 投递隔离 (EventBus 不修改 payload, Event 不可变)
8. 全局单例 get/set_global_event_bus
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses

import pytest

from server.core.event_bus import (
    EventBus,
    Event,
    get_event_bus,
    set_global_event_bus,
)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.mark.asyncio
class TestEventBus:
    async def test_publish_subscribe_basic(self, event_bus):
        """publish 后订阅者能收到事件"""
        async def consumer():
            async for event in event_bus.subscribe("memory.*"):
                return event

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)  # 让订阅注册
        await event_bus.publish("memory.graph.updated", {"k": "v"}, source="test")
        event = await asyncio.wait_for(task, timeout=1.0)
        assert event.event_type == "memory.graph.updated"
        assert event.payload == {"k": "v"}
        assert event.source == "test"

    async def test_wildcard_subscribe(self, event_bus):
        """'*' 通配符订阅所有事件"""
        received = []

        async def consumer():
            async for event in event_bus.subscribe("*"):
                received.append(event)
                if len(received) >= 2:
                    return

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        await event_bus.publish("memory.graph.updated", {"k": 1}, source="test")
        await event_bus.publish("chat.message.completed", {"k": 2}, source="test")
        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 2
        assert received[0].event_type == "memory.graph.updated"
        assert received[1].event_type == "chat.message.completed"

    async def test_prefix_wildcard(self, event_bus):
        """'memory.*' 前缀通配订阅 memory.graph.updated 但不订阅 chat.message.completed"""
        received = []

        async def consumer():
            async for event in event_bus.subscribe("memory.*"):
                received.append(event)
                return

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        # 不匹配的事件先发 (不应被收到)
        await event_bus.publish("chat.message.completed", {"k": 1}, source="test")
        # 匹配的事件
        await event_bus.publish("memory.graph.updated", {"k": 2}, source="test")
        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 1
        assert received[0].event_type == "memory.graph.updated"

    async def test_exact_match(self, event_bus):
        """精确匹配: 订阅 'chat.message.completed' 只收到该类型"""
        received = []

        async def consumer():
            async for event in event_bus.subscribe("chat.message.completed"):
                received.append(event)
                return

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        await event_bus.publish("chat.message.completed", {"k": 1}, source="test")
        await event_bus.publish("chat.tool.call.completed", {"k": 2}, source="test")
        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 1
        assert received[0].event_type == "chat.message.completed"

    async def test_replay_since(self, event_bus):
        """replay_since 断点续传: publish 几个事件后, replay_since(last_seq) 返回后续事件"""
        e1 = await event_bus.publish("memory.graph.updated", {"k": 1}, source="test")
        e2 = await event_bus.publish("memory.graph.updated", {"k": 2}, source="test")
        e3 = await event_bus.publish("memory.graph.updated", {"k": 3}, source="test")
        # replay_since(e1.seq) → 返回 seq > e1.seq 的事件 (e2, e3)
        replayed = event_bus.replay_since(e1.seq, "memory.*")
        assert len(replayed) == 2
        assert replayed[0].seq == e2.seq
        assert replayed[1].seq == e3.seq

    async def test_seq_monotonic(self, event_bus):
        """seq 单调递增"""
        seqs = []
        for i in range(5):
            e = await event_bus.publish("memory.graph.updated", {"k": i}, source="test")
            seqs.append(e.seq)
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 5  # 全部唯一
        assert seqs[-1] > seqs[0]

    async def test_multiple_subscribers(self, event_bus):
        """多个订阅者都能收到同一事件 (广播)"""
        received1: list[Event] = []
        received2: list[Event] = []

        async def consumer(received):
            async for event in event_bus.subscribe("memory.*"):
                received.append(event)
                return

        t1 = asyncio.create_task(consumer(received1))
        t2 = asyncio.create_task(consumer(received2))
        await asyncio.sleep(0.01)
        await event_bus.publish("memory.graph.updated", {"k": "v"}, source="test")
        await asyncio.wait_for(t1, timeout=1.0)
        await asyncio.wait_for(t2, timeout=1.0)
        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0].seq == received2[0].seq  # 同一事件

    async def test_subscriber_auto_unregister(self, event_bus):
        """订阅者 task 取消后自动注销 (不影响其他订阅者)"""
        received: list[Event] = []

        async def consumer():
            async for event in event_bus.subscribe("memory.*"):
                received.append(event)

        t1 = asyncio.create_task(consumer())
        t2 = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        assert event_bus.subscriber_count() == 2

        # 取消 t1, 验证自动注销
        t1.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t1
        await asyncio.sleep(0.02)
        assert event_bus.subscriber_count() == 1

        # publish, 只有 t2 收到
        await event_bus.publish("memory.graph.updated", {"k": "v"}, source="test")
        await asyncio.sleep(0.02)
        t2.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t2
        assert len(received) == 1

    async def test_payload_isolation(self, event_bus):
        """payload 在投递过程中不被总线修改, Event 不可变 (frozen dataclass)"""
        received: list[Event] = []

        async def consumer():
            async for event in event_bus.subscribe("memory.*"):
                received.append(event)
                return

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        payload = {"k": "v", "nested": {"a": 1}, "list": [1, 2, 3]}
        event = await event_bus.publish("memory.graph.updated", payload, source="test")
        await asyncio.wait_for(task, timeout=1.0)
        # 总线不修改 payload 内容
        assert received[0].payload == {"k": "v", "nested": {"a": 1}, "list": [1, 2, 3]}
        # Event 是 frozen dataclass, 不可重新赋值字段
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.payload = {"other": "value"}


class TestGlobalEventBus:
    def test_get_set_global(self):
        """get_event_bus / set_global_event_bus 全局单例"""
        import server.core.event_bus as eb
        original = eb._global_bus
        try:
            bus = EventBus()
            set_global_event_bus(bus)
            assert get_event_bus() is bus
        finally:
            # 恢复全局状态 (避免影响其他测试)
            eb._global_bus = original
