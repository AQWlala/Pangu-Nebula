"""v2.3.0 Phase 2 — LinkageCoordinator 单元测试

覆盖 7 条联动消费者 (链路 1/3/4/5/6/7/8):
- 链路 1: health.provider.toggled → persona.delegated (session_factory=None 降级)
- 链路 3: chat.tool.call.completed ×3 → health.check.requested (含成功重置)
- 链路 4: mcp.health.failed ×3 → mcp.disconnected (含计数重置)
- 链路 5: persona.delegated → persona.delegation.blocked (depth 越界告警 + payload 保留)
- 链路 6: dag.node.failed → GraphExecutor.interrupt (graph_executor=None 降级)
- 链路 7: chat.message.completed ×10 → evolution.log.appended
- 链路 8: skill.enabled.toggled → swarm.refresh.requested
- start/stop 幂等性
"""
from __future__ import annotations

import asyncio
import contextlib

import pytest

from server.core.event_bus import EventBus
from server.services.linkage_coordinator import LinkageCoordinator


@pytest.fixture
async def setup():
    """event_bus + linkage_coordinator, 启动并自动清理"""
    bus = EventBus()
    linkage = LinkageCoordinator(
        event_bus=bus, session_factory=None, graph_executor=None
    )
    await linkage.start()
    yield bus, linkage
    await linkage.stop()


@pytest.mark.asyncio
class TestLinkageCoordinator:
    async def test_linkage_1_health_to_persona(self, setup):
        """链路1: session_factory=None 时降级 (无异常, 无 persona.delegated)"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("persona.delegated"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        # enabled=True 不触发 (handler 早返回)
        await bus.publish(
            "health.provider.toggled",
            {"provider": "openai", "enabled": True},
            source="test",
        )
        # enabled=False 但 session_factory=None → 降级, 无 publish
        await bus.publish(
            "health.provider.toggled",
            {"provider": "openai", "enabled": False},
            source="test",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 0

    async def test_linkage_3_tool_timeout_to_health(self, setup):
        """链路3: chat.tool.call.completed success=False ×3 → health.check.requested"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("health.check.requested"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        # 连续 3 次失败
        for i in range(3):
            await bus.publish(
                "chat.tool.call.completed",
                {"persona_id": 1, "success": False},
                source="test",
            )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["persona_id"] == 1
        assert received[0].payload["reason"] == "tool_timeout_streak"

    async def test_linkage_3_tool_success_resets_streak(self, setup):
        """链路3: 成功调用重置失败计数 (2 失败 → 1 成功 → 2 失败 → 不触发)"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("health.check.requested"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        # 2 次失败
        for i in range(2):
            await bus.publish(
                "chat.tool.call.completed",
                {"persona_id": 1, "success": False},
                source="test",
            )
        # 1 次成功 → 重置计数
        await bus.publish(
            "chat.tool.call.completed",
            {"persona_id": 1, "success": True},
            source="test",
        )
        # 再 2 次失败 → 计数仅 2, 未达 3
        for i in range(2):
            await bus.publish(
                "chat.tool.call.completed",
                {"persona_id": 1, "success": False},
                source="test",
            )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 0

    async def test_linkage_4_mcp_health_to_disconnect(self, setup):
        """链路4: mcp.health.failed ×3 → mcp.disconnected"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("mcp.disconnected"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        for i in range(3):
            await bus.publish(
                "mcp.health.failed",
                {"server_name": "test-server"},
                source="test",
            )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["server_name"] == "test-server"
        assert received[0].payload["reason"] == "health_check_streak"

    async def test_linkage_4_resets_after_trigger(self, setup):
        """链路4: 触发后计数重置, 再 3 次失败再次触发"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("mcp.disconnected"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        # 第一轮: 3 次失败 → 触发 1 次
        for i in range(3):
            await bus.publish(
                "mcp.health.failed",
                {"server_name": "srv"},
                source="test",
            )
        await asyncio.sleep(0.05)
        # 第二轮: 再 3 次失败 → 再触发 1 次 (计数已重置)
        for i in range(3):
            await bus.publish(
                "mcp.health.failed",
                {"server_name": "srv"},
                source="test",
            )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 2

    async def test_linkage_5_delegation_audit_within_limit(self, setup):
        """链路5: persona.delegated depth<=3 → 仅审计, 无 persona.delegation.blocked"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("persona.delegation.blocked"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        await bus.publish(
            "persona.delegated",
            {"persona_id": 1, "depth": 2, "max_depth": 3},
            source="test",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 0

    async def test_linkage_5_delegation_audit_exceed_limit(self, setup):
        """链路5: persona.delegated depth>3 → persona.delegation.blocked"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("persona.delegation.blocked"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        await bus.publish(
            "persona.delegated",
            {"persona_id": 1, "depth": 5, "max_depth": 3},
            source="test",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["persona_id"] == 1
        assert received[0].payload["reason"] == "max_depth_exceeded"

    async def test_linkage_5_blocked_payload_preserved(self, setup):
        """链路5: blocked 事件保留原 payload 并添加 reason"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("persona.delegation.blocked"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        await bus.publish(
            "persona.delegated",
            {"persona_id": 7, "depth": 4, "max_depth": 3, "extra": "data"},
            source="test",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["persona_id"] == 7
        assert received[0].payload["depth"] == 4
        assert received[0].payload["extra"] == "data"
        assert received[0].payload["reason"] == "max_depth_exceeded"

    async def test_linkage_6_dag_failure_no_executor(self, setup):
        """链路6: graph_executor=None 时降级 (无异常)"""
        bus, linkage = setup
        # graph_executor=None, publish dag.node.failed → 无异常 (降级 log-only)
        await bus.publish(
            "dag.node.failed",
            {"dag_id": "test-dag", "node_id": "node1"},
            source="test",
        )
        await asyncio.sleep(0.05)
        # 到达此处说明降级成功 (无异常抛出)
        assert linkage.graph_executor is None

    async def test_linkage_7_chat_to_evolution(self, setup):
        """链路7: chat.message.completed ×10 → evolution.log.appended"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("evolution.log.appended"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        # 阈值是 10, publish 10 次 → 触发 1 次 evolution.log.appended
        for i in range(10):
            await bus.publish(
                "chat.message.completed",
                {"persona_id": 1},
                source="test",
            )
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["persona_id"] == 1
        assert received[0].payload["trigger"] == "chat_threshold"

    async def test_linkage_8_skill_to_swarm(self, setup):
        """链路8: skill.enabled.toggled → swarm.refresh.requested"""
        bus, linkage = setup
        received = []

        async def collector():
            async for event in bus.subscribe("swarm.refresh.requested"):
                received.append(event)

        task = asyncio.create_task(collector())
        await asyncio.sleep(0.01)
        await bus.publish(
            "skill.enabled.toggled",
            {"skill_id": "skill-1", "enabled": True},
            source="test",
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(received) == 1
        assert received[0].payload["skill_id"] == "skill-1"
        assert received[0].payload["reason"] == "skill_toggled"

    async def test_linkage_start_stop_idempotent(self):
        """start/stop 幂等: stop 后再 stop 不报错"""
        bus = EventBus()
        linkage = LinkageCoordinator(event_bus=bus)
        await linkage.start()
        await linkage.stop()
        await linkage.stop()  # 不报错