"""DAG 编排数据模型服务层 (T2.1)。

提供 DAG 图的创建、查询、节点状态更新、审批与可执行节点计算。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.dag_models import DAGNode, DAGEdge


def _node_to_dict(n: DAGNode) -> dict:
    return {
        "id": n.id,
        "dag_id": n.dag_id,
        "node_id": n.node_id,
        "title": n.title,
        "node_type": n.node_type,
        "status": n.status,
        "model": n.model,
        "brief": n.brief,
        "config": n.config or {},
        "result": n.result,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _edge_to_dict(e: DAGEdge) -> dict:
    return {
        "id": e.id,
        "dag_id": e.dag_id,
        "source_node_id": e.source_node_id,
        "target_node_id": e.target_node_id,
        "edge_type": e.edge_type,
        "condition": e.condition,
    }


class DAGService:
    """DAG 编排服务"""

    async def create_dag(
        self,
        session: AsyncSession,
        dag_id: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> dict:
        # 先删除同 dag_id 的旧数据(幂等创建)
        old_nodes = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id)
        )
        for n in old_nodes.scalars().all():
            await session.delete(n)
        old_edges = await session.execute(
            select(DAGEdge).where(DAGEdge.dag_id == dag_id)
        )
        for e in old_edges.scalars().all():
            await session.delete(e)
        await session.flush()

        created_nodes = []
        for node_data in nodes:
            node = DAGNode(
                dag_id=dag_id,
                node_id=node_data["node_id"],
                title=node_data.get("title", node_data["node_id"]),
                node_type=node_data.get("node_type", "task"),
                status=node_data.get("status", "pending"),
                model=node_data.get("model"),
                brief=node_data.get("brief"),
                config=node_data.get("config", {}),
            )
            session.add(node)
            created_nodes.append(node)

        created_edges = []
        for edge_data in edges:
            edge = DAGEdge(
                dag_id=dag_id,
                source_node_id=edge_data["source_node_id"],
                target_node_id=edge_data["target_node_id"],
                edge_type=edge_data.get("edge_type", "sequence"),
                condition=edge_data.get("condition"),
            )
            session.add(edge)
            created_edges.append(edge)

        await session.commit()
        for n in created_nodes:
            await session.refresh(n)
        for e in created_edges:
            await session.refresh(e)

        return {
            "dag_id": dag_id,
            "nodes": [_node_to_dict(n) for n in created_nodes],
            "edges": [_edge_to_dict(e) for e in created_edges],
        }

    async def get_dag(self, session: AsyncSession, dag_id: str) -> dict | None:
        nodes_result = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id).order_by(DAGNode.id)
        )
        nodes = nodes_result.scalars().all()
        if not nodes:
            return None

        edges_result = await session.execute(
            select(DAGEdge).where(DAGEdge.dag_id == dag_id).order_by(DAGEdge.id)
        )
        edges = edges_result.scalars().all()

        return {
            "dag_id": dag_id,
            "nodes": [_node_to_dict(n) for n in nodes],
            "edges": [_edge_to_dict(e) for e in edges],
        }

    async def update_node_status(
        self,
        session: AsyncSession,
        dag_id: str,
        node_id: str,
        status: str,
        result: str | None = None,
    ) -> dict:
        result_set = await session.execute(
            select(DAGNode).where(
                DAGNode.dag_id == dag_id, DAGNode.node_id == node_id
            )
        )
        node = result_set.scalar_one_or_none()
        if not node:
            return None
        node.status = status
        if result is not None:
            node.result = result
        await session.commit()
        await session.refresh(node)
        return _node_to_dict(node)

    async def get_pending_nodes(
        self, session: AsyncSession, dag_id: str
    ) -> list[dict]:
        """获取可执行的 pending 节点: 所有前驱节点已 completed 的 pending 节点"""
        # 获取 DAG 全部节点和边
        dag = await self.get_dag(session, dag_id)
        if not dag:
            return []

        nodes_by_id = {n["node_id"]: n for n in dag["nodes"]}
        # 构建前驱映射: target -> [sources]
        predecessors: dict[str, list[str]] = {}
        for edge in dag["edges"]:
            predecessors.setdefault(edge["target_node_id"], []).append(
                edge["source_node_id"]
            )

        pending_executable = []
        for node in dag["nodes"]:
            if node["status"] != "pending":
                continue
            preds = predecessors.get(node["node_id"], [])
            # 所有前驱节点都已完成
            if all(
                nodes_by_id.get(p, {}).get("status") == "completed" for p in preds
            ):
                pending_executable.append(node)

        return pending_executable

    async def approve_dag(self, session: AsyncSession, dag_id: str) -> dict:
        """审批通过:将所有 approval 类型且 pending 的节点标记为 completed"""
        result_set = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id)
        )
        nodes = result_set.scalars().all()
        if not nodes:
            return None
        approved = 0
        for node in nodes:
            if node.node_type == "approval" and node.status == "pending":
                node.status = "completed"
                approved += 1
        await session.commit()
        return {
            "dag_id": dag_id,
            "action": "approved",
            "approved_nodes": approved,
        }

    async def get_approval_status(
        self, session: AsyncSession, dag_id: str
    ) -> dict | None:
        """获取 DAG 审批状态 (T2.3)

        返回:
          - plan_ready: 是否所有非 approval 节点已就绪(等待审批)
          - pending_approvals: 待审批的 approval 节点列表
          - approved_count / pending_count / rejected_count
          - overall_status: pending / approved / rejected / no_approval_needed
        """
        result_set = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id).order_by(DAGNode.id)
        )
        nodes = result_set.scalars().all()
        if not nodes:
            return None

        approval_nodes = [n for n in nodes if n.node_type == "approval"]
        non_approval_pending = [
            n for n in nodes
            if n.node_type != "approval" and n.status == "pending"
        ]

        pending_approvals = [
            _node_to_dict(n) for n in approval_nodes if n.status == "pending"
        ]
        approved_count = sum(1 for n in approval_nodes if n.status == "completed")
        rejected_count = sum(1 for n in approval_nodes if n.status == "skipped")

        # 判定整体状态
        if not approval_nodes:
            overall = "no_approval_needed"
            plan_ready = False
        elif pending_approvals:
            # 还有待审批节点:plan_ready 取决于其他 pending 任务是否已就绪
            # 简化策略: 只要有 pending approval 就视为 plan_ready=True (等待审批)
            plan_ready = True
            overall = "pending"
        elif rejected_count > 0:
            overall = "rejected"
            plan_ready = False
        else:
            overall = "approved"
            plan_ready = False

        return {
            "dag_id": dag_id,
            "plan_ready": plan_ready,
            "overall_status": overall,
            "pending_approvals": pending_approvals,
            "approved_count": approved_count,
            "pending_count": len(pending_approvals),
            "rejected_count": rejected_count,
            "non_approval_pending_count": len(non_approval_pending),
        }

    async def reject_dag(
        self, session: AsyncSession, dag_id: str, reason: str
    ) -> dict:
        """审批拒绝:将所有 pending 节点标记为 skipped"""
        result_set = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id)
        )
        nodes = result_set.scalars().all()
        if not nodes:
            return None
        skipped = 0
        for node in nodes:
            if node.status == "pending":
                node.status = "skipped"
                node.result = f"rejected: {reason}"
                skipped += 1
        await session.commit()
        return {
            "dag_id": dag_id,
            "action": "rejected",
            "reason": reason,
            "skipped_nodes": skipped,
        }

    async def reset_to_planning(
        self, session: AsyncSession, dag_id: str
    ) -> dict | None:
        """reject 后回退到规划状态 (T2.3)

        将 skipped 节点重置为 pending, 清空 result, 以便重新规划。
        """
        result_set = await session.execute(
            select(DAGNode).where(DAGNode.dag_id == dag_id)
        )
        nodes = result_set.scalars().all()
        if not nodes:
            return None
        reset = 0
        for node in nodes:
            if node.status == "skipped":
                node.status = "pending"
                node.result = None
                reset += 1
        await session.commit()
        return {
            "dag_id": dag_id,
            "action": "reset_to_planning",
            "reset_nodes": reset,
        }

    async def precheck_node(
        self,
        session: AsyncSession,
        dag_id: str,
        node_id: str,
        model: str | None = None,
        brief: str | None = None,
    ) -> dict | None:
        """节点级预检 (T2.4)

        - 应用 model/brief override 到节点
        - 验证 model 非空(若提供)
        - 验证 brief 长度合理(若提供)
        - 返回 precheck 结果(passed/issues)
        - 通过后将节点 config 标记 precheck_passed=True
        """
        result_set = await session.execute(
            select(DAGNode).where(
                DAGNode.dag_id == dag_id, DAGNode.node_id == node_id
            )
        )
        node = result_set.scalar_one_or_none()
        if not node:
            return None

        issues: list[str] = []
        # 应用 override
        if model is not None:
            model_stripped = model.strip()
            if not model_stripped:
                issues.append("model 不能为空字符串")
            else:
                node.model = model_stripped
        if brief is not None:
            brief_stripped = brief.strip()
            if len(brief_stripped) > 2000:
                issues.append("brief 长度超过 2000 字符")
            else:
                node.brief = brief_stripped

        # 检查节点状态是否允许预检
        if node.status not in ("pending",):
            issues.append(f"节点状态 {node.status} 不允许预检(需 pending)")

        # 检查 model 必须存在(节点级预检要求)
        if not node.model:
            issues.append("节点未指定 model,无法执行")

        passed = len(issues) == 0
        # 更新 config 标记预检结果
        cfg = dict(node.config or {})
        cfg["precheck_passed"] = passed
        cfg["precheck_at"] = datetime.utcnow().isoformat()
        node.config = cfg

        await session.commit()
        await session.refresh(node)
        return {
            "dag_id": dag_id,
            "node_id": node_id,
            "passed": passed,
            "issues": issues,
            "node": _node_to_dict(node),
        }

    async def list_dags(self, session: AsyncSession) -> list[dict]:
        """列出所有 DAG (按 dag_id 去重,返回每个 DAG 的摘要)"""
        result = await session.execute(
            select(DAGNode.dag_id).distinct().order_by(DAGNode.dag_id)
        )
        dag_ids = [row[0] for row in result.all()]
        dags = []
        for dag_id in dag_ids:
            dag = await self.get_dag(session, dag_id)
            if dag:
                nodes = dag["nodes"]
                dags.append({
                    "dag_id": dag_id,
                    "node_count": len(nodes),
                    "edge_count": len(dag["edges"]),
                    "statuses": {
                        s: sum(1 for n in nodes if n["status"] == s)
                        for s in ("pending", "running", "completed", "failed", "skipped")
                    },
                })
        return dags
