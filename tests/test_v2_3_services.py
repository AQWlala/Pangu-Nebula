"""v2.3.0 新增服务单元测试

覆盖:
- GraphExecutor (DAG 执行引擎: 线性/条件边/中断/失败/完成事件)
- HeartbeatService (5 节拍编排器: 注册执行/异常隔离/幂等/默认节拍)
- DelegationGuard (委派深度守卫: enter/exit/depth/can_delegate/事件)
- RoleMatcher (角色三元组匹配: 关系推断/相似度/DB 候选查询)

不修改源码,仅测试已实现 API。
"""
import asyncio

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from server.core.event_bus import EventBus
from server.db.orm import Persona
from server.services.delegation_guard import (
    DelegationGuard,
    MAX_DELEGATION_DEPTH,
)
from server.services.graph_executor import (
    DAG,
    DAGEdge,
    DAGNode,
    GraphExecutor,
    NodeStatus,
)
from server.services.heartbeat_service import (
    Beat,
    HeartbeatService,
    create_default_heartbeat,
)
from server.services.role_matcher import RoleMatcher


# ---------------------------------------------------------------------------
# GraphExecutor 辅助构造
# ---------------------------------------------------------------------------

def make_node(node_id, func=None):
    """构造 DAG 节点; execute_fn 为 None 时 GraphExecutor 视为 no-op 完成"""
    return DAGNode(id=node_id, title=node_id, execute_fn=func)


def make_linear_dag():
    """线性 DAG: a → b → c"""
    nodes = {nid: make_node(nid) for nid in ("a", "b", "c")}
    edges = [DAGEdge(source="a", target="b"), DAGEdge(source="b", target="c")]
    return DAG(id="test-dag", nodes=nodes, edges=edges)


async def _success_result_fn(node, context, event_bus):
    """返回带 result.success=True 的输出 (供条件边 result.success 求值)"""
    return {"result": {"success": True}}


async def _fail_fn(node, context, event_bus):
    """执行时抛异常"""
    raise RuntimeError("boom")


async def _collect_events(executor, dag):
    """收集 run_dag 产生的事件流"""
    return [event async for event in executor.run_dag(dag)]


# ---------------------------------------------------------------------------
# GraphExecutor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGraphExecutor:
    async def test_linear_dag_execution(self):
        """线性 DAG: a→b→c 顺序执行, 所有节点 completed, 末尾 dag.completed"""
        dag = make_linear_dag()
        executor = GraphExecutor(event_bus=EventBus())
        events = await _collect_events(executor, dag)

        completed = [e for e in events if e["type"] == "node_completed"]
        assert len(completed) == 3
        assert all(n.status == NodeStatus.COMPLETED for n in dag.nodes.values())
        assert events[-1]["type"] == "dag_completed"
        assert events[-1]["dag_id"] == "test-dag"

    async def test_conditional_edge_taken(self):
        """条件边: A→B (condition: result.success==true), A 输出 success=True → B 执行"""
        a = DAGNode(id="a", title="a", execute_fn=_success_result_fn)
        b = make_node("b")
        edges = [DAGEdge(source="a", target="b", condition="result.success == true")]
        dag = DAG(id="cond-take", nodes={"a": a, "b": b}, edges=edges)
        executor = GraphExecutor(event_bus=EventBus())
        events = await _collect_events(executor, dag)

        assert dag.nodes["a"].status == NodeStatus.COMPLETED
        assert dag.nodes["b"].status == NodeStatus.COMPLETED
        # B 被执行而非跳过
        assert any(e["type"] == "node_completed" and e["node_id"] == "b" for e in events)

    async def test_conditional_edge_skipped(self):
        """条件边: A→B (condition: result.success==false), A 输出 success=True → B 跳过"""
        a = DAGNode(id="a", title="a", execute_fn=_success_result_fn)
        b = make_node("b")
        edges = [DAGEdge(source="a", target="b", condition="result.success == false")]
        dag = DAG(id="cond-skip", nodes={"a": a, "b": b}, edges=edges)
        executor = GraphExecutor(event_bus=EventBus())
        events = await _collect_events(executor, dag)

        assert dag.nodes["a"].status == NodeStatus.COMPLETED
        assert dag.nodes["b"].status == NodeStatus.SKIPPED
        skipped = [e for e in events if e["type"] == "node_skipped" and e["node_id"] == "b"]
        assert len(skipped) == 1

    async def test_dag_interrupt(self):
        """interrupt: A 执行后调用 executor.interrupt(dag) → 后续节点被中断"""
        dag = make_linear_dag()
        executor = GraphExecutor(event_bus=EventBus())

        async def _interrupt_after(node, context, event_bus):
            # A 完成后中断整个 DAG
            executor.interrupt(dag)
            return {"success": True}

        dag.nodes["a"].execute_fn = _interrupt_after
        events = await _collect_events(executor, dag)

        assert dag.interrupted is True
        # A 仍正常完成
        assert dag.nodes["a"].status == NodeStatus.COMPLETED
        # B、C 被中断
        assert dag.nodes["b"].status == NodeStatus.INTERRUPTED
        assert dag.nodes["c"].status == NodeStatus.INTERRUPTED
        interrupted = [e for e in events if e["type"] == "node_interrupted"]
        assert len(interrupted) >= 2

    async def test_node_failure_publishes_event(self):
        """节点失败: 抛异常的节点 → node_failed 事件 + dag_interrupted"""
        a = DAGNode(id="a", title="a", execute_fn=_fail_fn)
        dag = DAG(id="fail-dag", nodes={"a": a}, edges=[])
        executor = GraphExecutor(event_bus=EventBus())
        events = await _collect_events(executor, dag)

        failed = [e for e in events if e["type"] == "node_failed"]
        assert len(failed) == 1
        assert "boom" in failed[0]["error"]
        assert dag.nodes["a"].status == NodeStatus.FAILED
        # 失败后中断 DAG
        dag_interrupted = [e for e in events if e["type"] == "dag_interrupted"]
        assert len(dag_interrupted) == 1
        assert dag_interrupted[0]["failed_node"] == "a"

    async def test_dag_completed_event(self):
        """DAG 完成: 所有节点成功 → 恰好一个 dag_completed 事件"""
        dag = make_linear_dag()
        executor = GraphExecutor(event_bus=EventBus())
        events = await _collect_events(executor, dag)

        completed = [e for e in events if e["type"] == "dag_completed"]
        assert len(completed) == 1
        assert completed[0]["dag_id"] == "test-dag"
        # 无 dag_failed / dag_interrupted
        assert not any(e["type"] == "dag_failed" for e in events)
        assert not any(e["type"] == "dag_interrupted" for e in events)


# ---------------------------------------------------------------------------
# HeartbeatService
# ---------------------------------------------------------------------------

async def _noop_beat():
    """空节拍任务"""
    pass


@pytest.mark.asyncio
class TestHeartbeatService:
    async def test_register_and_run_beat(self):
        """注册一个节拍并执行: 短周期 beat 启动后被回调多次"""
        calls = []

        async def _task():
            calls.append(1)

        bus = EventBus()
        service = HeartbeatService(event_bus=bus)
        service.register_beat(Beat(name="test", interval_seconds=0.05, task_fn=_task))
        await service.start()
        await asyncio.sleep(0.2)
        await service.stop()

        assert len(calls) >= 1
        # 历史记录应包含本节拍
        history = service.get_history()
        assert any(h["beat"] == "test" for h in history)

    async def test_beat_exception_isolation(self):
        """节拍异常不影响其他节拍: bad beat 抛异常, good beat 仍执行"""
        good_calls = []

        async def _good():
            good_calls.append(1)

        async def _bad():
            raise RuntimeError("beat failed")

        bus = EventBus()
        service = HeartbeatService(event_bus=bus)
        service.register_beat(Beat(name="good", interval_seconds=0.05, task_fn=_good))
        service.register_beat(Beat(name="bad", interval_seconds=0.05, task_fn=_bad))
        await service.start()
        await asyncio.sleep(0.2)
        await service.stop()

        # good beat 不受 bad beat 异常影响
        assert len(good_calls) >= 1
        # bad beat 失败记录在历史中
        history = service.get_history()
        bad_records = [h for h in history if h["beat"] == "bad"]
        assert any(h["success"] is False for h in bad_records)

    async def test_start_stop_idempotent(self):
        """start/stop 幂等: 重复调用不报错"""
        bus = EventBus()
        service = HeartbeatService(event_bus=bus)
        service.register_beat(Beat(name="slow", interval_seconds=10.0, task_fn=_noop_beat))

        await service.start()
        assert service.is_running() is True
        # 重复 start 不报错 (内部 warning 后 return)
        await service.start()
        assert service.is_running() is True

        await service.stop()
        assert service.is_running() is False
        # 重复 stop 不报错
        await service.stop()
        assert service.is_running() is False

    async def test_create_default_heartbeat(self):
        """create_default_heartbeat 返回 5 个节拍 (micro/small/medium/large/selfcheck)"""
        service = create_default_heartbeat(app_state=None)
        # 不 start, 仅验证节拍注册 (避免触发 DB 依赖)
        assert set(service._beats.keys()) == {
            "micro", "small", "medium", "large", "selfcheck",
        }
        assert len(service._beats) == 5
        # selfcheck 仅启动时执行 (interval=None, run_on_start=True)
        assert service._beats["selfcheck"].interval_seconds is None
        assert service._beats["selfcheck"].run_on_start is True
        # large 节拍有错峰延迟
        assert service._beats["large"].initial_delay > 0


# ---------------------------------------------------------------------------
# DelegationGuard
# ---------------------------------------------------------------------------

class TestDelegationGuard:
    def test_enter_exit_delegation(self):
        """enter/exit 配对, depth 正确归零"""
        guard = DelegationGuard()
        assert guard.get_depth(persona_id=1) == 0
        assert guard.enter_delegation(persona_id=1) is True
        assert guard.get_depth(persona_id=1) == 1
        guard.exit_delegation(persona_id=1)
        assert guard.get_depth(persona_id=1) == 0

    def test_can_delegate_within_limit(self):
        """depth < MAX_DELEGATION_DEPTH 时 can_delegate 返回 True"""
        guard = DelegationGuard()
        guard.enter_delegation(persona_id=1)
        guard.enter_delegation(persona_id=1)
        assert guard.get_depth(persona_id=1) == 2
        assert guard.can_delegate(persona_id=1) is True

    def test_can_delegate_exceed_limit(self):
        """depth >= MAX 时 can_delegate 返回 False, 再次 enter 被拒绝"""
        guard = DelegationGuard()
        assert MAX_DELEGATION_DEPTH == 3
        for _ in range(MAX_DELEGATION_DEPTH):
            assert guard.enter_delegation(persona_id=1) is True
        assert guard.get_depth(persona_id=1) == MAX_DELEGATION_DEPTH
        # 达到上限, 不再允许委派
        assert guard.can_delegate(persona_id=1) is False
        # 第 4 次 enter 被拒, 深度不变
        assert guard.enter_delegation(persona_id=1) is False
        assert guard.get_depth(persona_id=1) == MAX_DELEGATION_DEPTH

    def test_delegation_isolation_between_personas(self):
        """不同 persona 的委派深度相互独立"""
        guard = DelegationGuard()
        guard.enter_delegation(persona_id=1)
        guard.enter_delegation(persona_id=2)
        assert guard.get_depth(persona_id=1) == 1
        assert guard.get_depth(persona_id=2) == 1
        # persona 2 退出不影响 persona 1
        guard.exit_delegation(persona_id=2)
        assert guard.get_depth(persona_id=1) == 1
        assert guard.get_depth(persona_id=2) == 0

    @pytest.mark.asyncio
    async def test_enter_delegation_publishes_event(self):
        """enter_delegation 异步发布 persona.delegated 事件 (含 persona_id/depth/max_depth)"""
        captured = []

        async def _audit_sink(event):
            captured.append(event)

        bus = EventBus(audit_sink=_audit_sink)
        # delegation_guard.enter_delegation 内部调用模块级 get_event_bus()
        with patch(
            "server.services.delegation_guard.get_event_bus", return_value=bus
        ):
            guard = DelegationGuard()
            guard.enter_delegation(persona_id=42)

            # enter_delegation 内部 asyncio.create_task 异步发布, 需让事件循环运行
            await asyncio.sleep(0.05)

        delegated = [e for e in captured if e.event_type == "persona.delegated"]
        assert len(delegated) == 1
        payload = delegated[0].payload
        assert payload["persona_id"] == 42
        assert payload["depth"] == 1
        assert payload["max_depth"] == MAX_DELEGATION_DEPTH


# ---------------------------------------------------------------------------
# RoleMatcher
# ---------------------------------------------------------------------------

class TestRoleMatcher:
    def test_infer_relation_type_assist(self):
        """role 相似度高 (>0.6) → assist"""
        matcher = RoleMatcher()
        a = SimpleNamespace(role="架构师", goal="设计系统", backstory="十年经验")
        b = SimpleNamespace(role="架构师", goal="设计系统", backstory="五年经验")
        # role 完全相同 → SequenceMatcher ratio=1.0 > 0.6
        assert matcher._infer_relation_type(a, b) == "assist"

    def test_infer_relation_type_complement(self):
        """role 不同但 goal 相似 (>0.5) → complement"""
        matcher = RoleMatcher()
        a = SimpleNamespace(role="架构师", goal="交付高质量系统", backstory="架构背景")
        b = SimpleNamespace(role="测试工程师", goal="交付高质量系统", backstory="测试背景")
        # role 不同 (无共同字符 → ratio 0 < 0.6), goal 完全相同 (1.0 > 0.5)
        assert matcher._infer_relation_type(a, b) == "complement"

    def test_infer_relation_type_delegate(self):
        """role 与 goal 均不相似 → delegate"""
        matcher = RoleMatcher()
        a = SimpleNamespace(role="架构师", goal="设计系统架构", backstory="技术")
        b = SimpleNamespace(role="文档撰写员", goal="编写用户手册", backstory="文科")
        # role 无共同字符, goal 无共同字符
        assert matcher._infer_relation_type(a, b) == "delegate"

    def test_compute_similarity_role_weighted_highest(self):
        """相似度加权: role 权重 0.5 最高, role 相同的配对得分高于 goal 相同的配对"""
        matcher = RoleMatcher()
        base = SimpleNamespace(role="架构师", goal="设计系统", backstory="十年")
        # 仅 role 相同
        same_role = SimpleNamespace(role="架构师", goal="其他目标", backstory="其他背景")
        # 仅 goal 相同
        same_goal = SimpleNamespace(role="其他角色", goal="设计系统", backstory="其他背景")
        score_role = matcher._compute_similarity(base, same_role)
        score_goal = matcher._compute_similarity(base, same_goal)
        # role 权重 0.5 > goal 权重 0.3, 故 role 相同得分更高
        assert score_role > score_goal
        # 完全相同的角色相似度应为 1.0
        assert matcher._compute_similarity(base, base) == 1.0

    @pytest.mark.asyncio
    async def test_find_candidates_orders_by_score(self, db_session):
        """find_candidates: 按相似度降序返回, limit 截断低相似度候选"""
        p1 = Persona(name="p1", system_prompt="x", role="架构师",
                     goal="设计系统", backstory="十年经验")
        p2 = Persona(name="p2", system_prompt="x", role="架构师",
                     goal="设计系统", backstory="五年经验")  # 与 p1 高度相似
        p3 = Persona(name="p3", system_prompt="x", role="厨师",
                     goal="做菜", backstory="厨艺学校")  # 与 p1 低相似
        db_session.add_all([p1, p2, p3])
        await db_session.flush()  # 获取自增 id

        matcher = RoleMatcher()
        candidates = await matcher.find_candidates(db_session, persona_id=p1.id, limit=5)

        # 返回 p2、p3 (不含 p1 自身)
        assert len(candidates) == 2
        # 高相似度 (p2) 排第一
        assert candidates[0]["persona"]["id"] == p2.id
        assert candidates[0]["score"] >= candidates[1]["score"]
        # p2 role 相同 → assist
        assert candidates[0]["relation_type"] == "assist"
        # limit 截断
        limited = await matcher.find_candidates(db_session, persona_id=p1.id, limit=1)
        assert len(limited) == 1

    @pytest.mark.asyncio
    async def test_find_candidates_empty(self, db_session):
        """无其他 persona 或 persona 不存在 → 返回空候选列表"""
        only = Persona(name="only", system_prompt="x", role="架构师",
                       goal="设计", backstory="背景")
        db_session.add(only)
        await db_session.flush()

        matcher = RoleMatcher()
        # 仅有自身, 无其他角色
        candidates = await matcher.find_candidates(db_session, persona_id=only.id)
        assert candidates == []
        # persona_id 不存在
        candidates_missing = await matcher.find_candidates(db_session, persona_id=99999)
        assert candidates_missing == []
