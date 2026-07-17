"""v2.3.0 Phase 0 — Swarm + DAG 统一执行引擎

修复问题 #2 (蜂群失效) 的核心:替换 SwarmService 的 Mock run_swarm,
接入真实编排链路 Coordinator → Planner → GraphExecutor。

节点状态机:
    pending → running → completed
                    ↘ → failed → interrupted (后续节点)
                    ↘ → skipped (条件边不满足)

支持:
- 条件边动态求值 (基于上游节点 output)
- interrupt/resume (人工干预或健康检查触发)
- Checkpoint 回退 (失败时回退到最近 checkpoint)
- 每个状态变更 publish 到 EventBus (dag.node.* 事件)

借鉴:
- DeerFlow 2.0: Coordinator/Planner 分离 + Plan Revision Loop
- LangGraph: StateGraph + interrupt/Checkpoint
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Awaitable

from ..core.event_bus import EventBus, get_event_bus

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """DAG 节点状态机"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"          # 条件边不满足,跳过
    INTERRUPTED = "interrupted"  # 人工/健康检查干预


@dataclass
class DAGNode:
    """DAG 节点定义"""
    id: str                              # 节点唯一标识
    title: str                           # 节点标题(展示用)
    node_type: str = "task"              # task/checkpoint/subtask/persona_switch
    persona_id: int | None = None        # 执行该节点的 persona
    inputs: dict[str, Any] = field(default_factory=dict)   # 静态输入
    execute_fn: Callable[..., Awaitable[dict]] | None = None  # 执行函数(注入)
    # 运行时状态
    status: NodeStatus = NodeStatus.PENDING
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class DAGEdge:
    """DAG 边定义 — 支持条件边"""
    source: str                          # 源节点 id
    target: str                          # 目标节点 id
    condition: str | None = None         # 条件表达式 (None 表示无条件边)
    # 条件求值上下文: {"source.output.key": "value"} 形式
    # 表达式如 "result.success == true" 会被求值


@dataclass
class DAG:
    """DAG 定义 — 节点 + 边 + 入口"""
    id: str
    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: list[DAGEdge] = field(default_factory=list)
    entry_node_ids: list[str] = field(default_factory=list)
    # 中断标志 (健康检查/人工可设置)
    interrupted: bool = False
    # 当前 checkpoint (用于回退)
    last_checkpoint_id: str | None = None


class GraphExecutor:
    """DAG 执行器 — 跑通节点状态机 + 条件边 + 中断 + 事件推送

    用法:
        executor = GraphExecutor(event_bus=app.state.event_bus)
        async for event in executor.run_dag(dag):
            # event: {"type": "node_started"/"node_completed"/...}
            ...
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus or get_event_bus()
        # 节点级超时(秒)。可被 node.inputs["timeout"] 覆盖
        self.default_timeout: float = 300.0
        # 活跃 DAG 注册表: dag_id -> DAG (供链路 6 查找并 interrupt)
        self._active_dags: dict[str, DAG] = {}

    async def run_dag(self, dag: DAG) -> AsyncIterator[dict[str, Any]]:
        """执行 DAG 主循环

        yield 事件流:
        - {"type": "dag_started", "dag_id": ...}
        - {"type": "node_started", "node_id": ..., "title": ...}
        - {"type": "node_completed", "node_id": ..., "output": ...}
        - {"type": "node_failed", "node_id": ..., "error": ...}
        - {"type": "node_skipped", "node_id": ..., "reason": ...}
        - {"type": "node_interrupted", "node_id": ...}
        - {"type": "dag_completed", "dag_id": ...}
        - {"type": "dag_failed", "dag_id": ..., "error": ...}
        - {"type": "dag_interrupted", "dag_id": ...}
        """
        # 注册到活跃 DAG 表 (供链路 6 dag.node.failed → interrupt 查找)
        self._active_dags[dag.id] = dag
        try:
            yield {"type": "dag_started", "dag_id": dag.id}
            await self.event_bus.publish(
                "dag.node.started",
                {"dag_id": dag.id, "phase": "dag_started"},
                source="graph_executor",
            )

            # 拓扑排序(简易:基于入度)
            order = self._topological_sort(dag)
            if order is None:
                error_msg = f"DAG {dag.id} 存在环,无法拓扑排序"
                yield {"type": "dag_failed", "dag_id": dag.id, "error": error_msg}
                await self.event_bus.publish(
                    "dag.node.failed",
                    {"dag_id": dag.id, "error": error_msg},
                    source="graph_executor",
                )
                return

            for node_id in order:
                # 中断检查 (外部设置 dag.interrupted = True)
                if dag.interrupted:
                    node = dag.nodes[node_id]
                    if node.status == NodeStatus.PENDING:
                        node.status = NodeStatus.INTERRUPTED
                        yield {"type": "node_interrupted", "node_id": node_id}
                        await self.event_bus.publish(
                            "dag.node.interrupted",
                            {"dag_id": dag.id, "node_id": node_id, "title": node.title},
                            source="graph_executor",
                        )
                    continue

                node = dag.nodes[node_id]

                # 条件边检查: 若任一入边的条件不满足,跳过
                if not self._check_incoming_conditions(dag, node_id):
                    node.status = NodeStatus.SKIPPED
                    yield {"type": "node_skipped", "node_id": node_id, "reason": "条件不满足"}
                    await self.event_bus.publish(
                        "dag.node.skipped",
                        {"dag_id": dag.id, "node_id": node_id, "reason": "条件不满足"},
                        source="graph_executor",
                    )
                    continue

                # 入口节点或上游已完成才能执行
                if not self._predecessors_completed(dag, node_id):
                    # 上游未完成(被跳过或失败),本节点也跳过
                    node.status = NodeStatus.SKIPPED
                    yield {"type": "node_skipped", "node_id": node_id, "reason": "上游未完成"}
                    continue

                # 执行节点
                import time
                node.status = NodeStatus.RUNNING
                node.started_at = time.time()
                yield {"type": "node_started", "node_id": node_id, "title": node.title}
                await self.event_bus.publish(
                    "dag.node.started",
                    {"dag_id": dag.id, "node_id": node_id, "title": node.title, "persona_id": node.persona_id},
                    source="graph_executor",
                )

                try:
                    # 节点超时控制
                    timeout = float(node.inputs.get("timeout", self.default_timeout))
                    if node.execute_fn is None:
                        # 无执行函数:视为 no-op 完成(占位/checkpoint 节点)
                        node.output = {"success": True, "result": "no-op"}
                    else:
                        # 注入上游输出作为上下文
                        context = self._build_node_context(dag, node_id)
                        node.output = await asyncio.wait_for(
                            node.execute_fn(node=node, context=context, event_bus=self.event_bus),
                            timeout=timeout,
                        )
                    node.status = NodeStatus.COMPLETED
                    node.completed_at = time.time()
                    yield {"type": "node_completed", "node_id": node_id, "output": node.output}
                    await self.event_bus.publish(
                        "dag.node.completed",
                        {"dag_id": dag.id, "node_id": node_id, "output": node.output},
                        source="graph_executor",
                    )

                    # checkpoint 节点: 记录回退点
                    if node.node_type == "checkpoint":
                        dag.last_checkpoint_id = node_id

                except asyncio.TimeoutError:
                    node.status = NodeStatus.FAILED
                    node.error = f"节点执行超时 ({timeout}s)"
                    yield {"type": "node_failed", "node_id": node_id, "error": node.error}
                    await self.event_bus.publish(
                        "dag.node.failed",
                        {"dag_id": dag.id, "node_id": node_id, "error": node.error, "reason": "timeout"},
                        source="graph_executor",
                    )
                    # 失败后中断后续节点
                    yield {"type": "dag_interrupted", "dag_id": dag.id, "failed_node": node_id}
                    await self.event_bus.publish(
                        "dag.node.interrupted",
                        {"dag_id": dag.id, "reason": "node_failed", "failed_node": node_id},
                        source="graph_executor",
                    )
                    return
                except Exception as exc:
                    node.status = NodeStatus.FAILED
                    node.error = str(exc)
                    logger.exception("DAG 节点执行失败 dag=%s node=%s", dag.id, node_id)
                    yield {"type": "node_failed", "node_id": node_id, "error": node.error}
                    await self.event_bus.publish(
                        "dag.node.failed",
                        {"dag_id": dag.id, "node_id": node_id, "error": node.error},
                        source="graph_executor",
                    )
                    yield {"type": "dag_interrupted", "dag_id": dag.id, "failed_node": node_id}
                    await self.event_bus.publish(
                        "dag.node.interrupted",
                        {"dag_id": dag.id, "reason": "node_failed", "failed_node": node_id},
                        source="graph_executor",
                    )
                    return

            yield {"type": "dag_completed", "dag_id": dag.id}
            await self.event_bus.publish(
                "dag.completed",
                {"dag_id": dag.id, "phase": "dag_completed"},
                source="graph_executor",
            )
        finally:
            # 无论成功/失败/中断, 都从活跃注册表注销
            self._active_dags.pop(dag.id, None)

    def _topological_sort(self, dag: DAG) -> list[str] | None:
        """Kahn 拓扑排序。返回 None 表示存在环"""
        in_degree: dict[str, int] = {nid: 0 for nid in dag.nodes}
        for edge in dag.edges:
            in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        # 使用 deque.popleft() 替代 list.pop(0) — O(1) vs O(N)
        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        while queue:
            nid = queue.popleft()
            order.append(nid)
            for edge in dag.edges:
                if edge.source == nid:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)

        if len(order) != len(dag.nodes):
            return None  # 存在环
        return order

    def _check_incoming_conditions(self, dag: DAG, node_id: str) -> bool:
        """检查节点的所有入边条件是否满足"""
        for edge in dag.edges:
            if edge.target != node_id:
                continue
            if edge.condition is None:
                continue
            # 求值条件表达式
            source_node = dag.nodes.get(edge.source)
            if source_node is None or source_node.output is None:
                return False
            if not self._evaluate_condition(edge.condition, source_node.output):
                return False
        return True

    def _evaluate_condition(self, expr: str, output: dict[str, Any]) -> bool:
        """求值条件表达式 (简易实现,避免 eval 安全风险)

        支持格式:
        - "result.success == true"
        - "result.status == 'completed'"
        - "result.score > 0.8"
        """
        # 简易解析: 仅支持 == != > < >= <= 与 true/false/数字/字符串
        # 生产环境应使用 ast 安全求值,这里保持最小实现
        expr = expr.strip()
        for op in ("==", "!=", ">=", "<=", ">", "<"):
            if op in expr:
                left, right = expr.split(op, 1)
                left = left.strip()
                right = right.strip()
                left_val = self._resolve_value(left, output)
                right_val = self._resolve_value(right, output)
                try:
                    if op == "==":
                        return left_val == right_val
                    if op == "!=":
                        return left_val != right_val
                    if op == ">=":
                        return float(left_val) >= float(right_val)
                    if op == "<=":
                        return float(left_val) <= float(right_val)
                    if op == ">":
                        return float(left_val) > float(right_val)
                    if op == "<":
                        return float(left_val) < float(right_val)
                except (ValueError, TypeError):
                    return False
        # 无操作符: 视为 truthy 检查
        val = self._resolve_value(expr, output)
        return bool(val)

    def _resolve_value(self, token: str, output: dict[str, Any]) -> Any:
        """解析 token: 字面量 or 路径访问 output"""
        token = token.strip()
        # 字面量
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1]
        if token.startswith('"') and token.endswith('"'):
            return token[1:-1]
        try:
            return float(token) if "." in token else int(token)
        except ValueError:
            pass
        # 路径访问: result.success → output["result"]["success"]
        parts = token.split(".")
        val: Any = output
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return None
        return val

    def _predecessors_completed(self, dag: DAG, node_id: str) -> bool:
        """检查所有前驱节点是否已完成(或被跳过)"""
        for edge in dag.edges:
            if edge.target != node_id:
                continue
            source = dag.nodes.get(edge.source)
            if source is None:
                continue
            if source.status not in (NodeStatus.COMPLETED, NodeStatus.SKIPPED):
                return False
        return True

    def _build_node_context(self, dag: DAG, node_id: str) -> dict[str, Any]:
        """构建节点执行上下文: 上游节点的输出"""
        context: dict[str, Any] = {}
        for edge in dag.edges:
            if edge.target != node_id:
                continue
            source = dag.nodes.get(edge.source)
            if source and source.output is not None:
                context[edge.source] = source.output
        return context

    def interrupt(self, dag: DAG) -> None:
        """中断 DAG (外部调用,如健康检查触发)"""
        dag.interrupted = True
        logger.info("DAG %s 已请求中断", dag.id)

    def rollback_to_checkpoint(self, dag: DAG) -> str | None:
        """回退到最近的 checkpoint 节点

        返回 checkpoint 节点 id,或 None(无 checkpoint)
        """
        if dag.last_checkpoint_id is None:
            return None
        # 将 checkpoint 之后的所有节点重置为 pending
        checkpoint = dag.nodes.get(dag.last_checkpoint_id)
        if checkpoint is None:
            return None
        # 简易回退: 重置所有 status 为 pending (生产环境应基于拓扑序精确回退)
        for nid, node in dag.nodes.items():
            if nid != dag.last_checkpoint_id:
                node.status = NodeStatus.PENDING
                node.output = None
                node.error = None
                node.started_at = None
                node.completed_at = None
        dag.interrupted = False
        return dag.last_checkpoint_id
