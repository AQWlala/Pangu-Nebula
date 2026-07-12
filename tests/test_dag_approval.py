"""Tests for DAG 审批与节点级预检 (T2.3 + T2.4)。"""

import pytest

from server.services.dag_service import DAGService

_service = DAGService()


def _sample_dag_with_approval():
    """带 approval 节点的示例 DAG"""
    return {
        "dag_id": "dag-approval-test",
        "nodes": [
            {"node_id": "n1", "title": "Start", "node_type": "task"},
            {"node_id": "n2", "title": "ApprovalGate", "node_type": "approval"},
            {"node_id": "n3", "title": "End", "node_type": "task"},
        ],
        "edges": [
            {"source_node_id": "n1", "target_node_id": "n2"},
            {"source_node_id": "n2", "target_node_id": "n3"},
        ],
    }


def _sample_dag_no_approval():
    """不带 approval 节点的示例 DAG"""
    return {
        "dag_id": "dag-no-approval",
        "nodes": [
            {"node_id": "n1", "title": "A", "node_type": "task"},
            {"node_id": "n2", "title": "B", "node_type": "task"},
        ],
        "edges": [{"source_node_id": "n1", "target_node_id": "n2"}],
    }


class TestApprovalStatus:
    """T2.3: 审批状态查询"""

    @pytest.mark.asyncio
    async def test_approval_status_pending(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.get_approval_status(db_session, "dag-approval-test")
        assert result is not None
        # 初始有 1 个 pending approval 节点
        assert result["pending_count"] == 1
        assert result["approved_count"] == 0
        assert result["rejected_count"] == 0
        assert result["overall_status"] == "pending"
        assert result["plan_ready"] is True
        assert len(result["pending_approvals"]) == 1
        assert result["pending_approvals"][0]["node_id"] == "n2"

    @pytest.mark.asyncio
    async def test_approval_status_after_approve(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        await _service.approve_dag(db_session, "dag-approval-test")
        result = await _service.get_approval_status(db_session, "dag-approval-test")
        assert result["overall_status"] == "approved"
        assert result["pending_count"] == 0
        assert result["approved_count"] == 1
        assert result["plan_ready"] is False

    @pytest.mark.asyncio
    async def test_approval_status_after_reject(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        await _service.reject_dag(db_session, "dag-approval-test", "不符合预期")
        result = await _service.get_approval_status(db_session, "dag-approval-test")
        assert result["overall_status"] == "rejected"
        assert result["rejected_count"] == 1
        assert result["plan_ready"] is False

    @pytest.mark.asyncio
    async def test_approval_status_no_approval_needed(self, db_session):
        spec = _sample_dag_no_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.get_approval_status(db_session, "dag-no-approval")
        assert result["overall_status"] == "no_approval_needed"
        assert result["plan_ready"] is False
        assert result["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_approval_status_not_found(self, db_session):
        result = await _service.get_approval_status(db_session, "nonexistent")
        assert result is None


class TestResetToPlanning:
    """T2.3: reject 后回退到规划状态"""

    @pytest.mark.asyncio
    async def test_reset_to_planning_after_reject(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        # 驳回
        await _service.reject_dag(db_session, "dag-approval-test", "需要修改")
        # 验证节点被 skipped
        dag = await _service.get_dag(db_session, "dag-approval-test")
        skipped_count = sum(1 for n in dag["nodes"] if n["status"] == "skipped")
        assert skipped_count == 3

        # 回退到规划
        result = await _service.reset_to_planning(db_session, "dag-approval-test")
        assert result["action"] == "reset_to_planning"
        assert result["reset_nodes"] == 3

        # 验证节点都回到 pending
        dag = await _service.get_dag(db_session, "dag-approval-test")
        for n in dag["nodes"]:
            assert n["status"] == "pending"
            assert n["result"] is None

    @pytest.mark.asyncio
    async def test_reset_to_planning_not_found(self, db_session):
        result = await _service.reset_to_planning(db_session, "nonexistent")
        assert result is None


class TestPrecheckNode:
    """T2.4: 节点级预检 (model/brief override)"""

    @pytest.mark.asyncio
    async def test_precheck_pass_with_model_and_brief(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.precheck_node(
            db_session,
            "dag-approval-test",
            "n1",
            model="gpt-4",
            brief="执行数据清洗",
        )
        assert result["passed"] is True
        assert result["issues"] == []
        assert result["node"]["model"] == "gpt-4"
        assert result["node"]["brief"] == "执行数据清洗"
        # 预检通过的 config 标记
        assert result["node"]["config"]["precheck_passed"] is True

    @pytest.mark.asyncio
    async def test_precheck_fail_no_model(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        # 不传 model,且节点初始 model=None
        result = await _service.precheck_node(
            db_session, "dag-approval-test", "n1", brief="只有 brief"
        )
        assert result["passed"] is False
        assert any("model" in i for i in result["issues"])
        assert result["node"]["config"]["precheck_passed"] is False

    @pytest.mark.asyncio
    async def test_precheck_fail_empty_model(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.precheck_node(
            db_session, "dag-approval-test", "n1", model="   "
        )
        assert result["passed"] is False
        assert any("model" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_precheck_fail_brief_too_long(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        long_brief = "x" * 2500
        result = await _service.precheck_node(
            db_session,
            "dag-approval-test",
            "n1",
            model="gpt-4",
            brief=long_brief,
        )
        assert result["passed"] is False
        assert any("brief" in i for i in result["issues"])

    @pytest.mark.asyncio
    async def test_precheck_node_not_found(self, db_session):
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.precheck_node(
            db_session, "dag-approval-test", "nonexistent", model="gpt-4"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_precheck_fail_wrong_status(self, db_session):
        """已 completed 节点不允许预检"""
        spec = _sample_dag_with_approval()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        # 把 n1 状态改为 completed
        await _service.update_node_status(db_session, "dag-approval-test", "n1", "completed")
        result = await _service.precheck_node(
            db_session, "dag-approval-test", "n1", model="gpt-4"
        )
        assert result["passed"] is False
        assert any("状态" in i for i in result["issues"])
