"""Tests for DAGService - DAG 编排数据模型。"""

import pytest

from server.services.dag_service import DAGService

_service = DAGService()


def _sample_dag():
    return {
        "dag_id": "dag-test-1",
        "nodes": [
            {"node_id": "n1", "title": "Start", "node_type": "task"},
            {"node_id": "n2", "title": "Approve", "node_type": "approval"},
            {"node_id": "n3", "title": "End", "node_type": "task"},
        ],
        "edges": [
            {"source_node_id": "n1", "target_node_id": "n2"},
            {"source_node_id": "n2", "target_node_id": "n3"},
        ],
    }


class TestDAGCreate:
    @pytest.mark.asyncio
    async def test_create_dag(self, db_session):
        spec = _sample_dag()
        result = await _service.create_dag(
            db_session, spec["dag_id"], spec["nodes"], spec["edges"]
        )
        assert result["dag_id"] == "dag-test-1"
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2
        assert result["nodes"][0]["node_id"] == "n1"
        assert result["nodes"][0]["status"] == "pending"
        assert result["edges"][0]["edge_type"] == "sequence"


class TestDAGGet:
    @pytest.mark.asyncio
    async def test_get_dag_detail(self, db_session):
        spec = _sample_dag()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.get_dag(db_session, "dag-test-1")
        assert result is not None
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2

    @pytest.mark.asyncio
    async def test_get_dag_not_found(self, db_session):
        result = await _service.get_dag(db_session, "nonexistent")
        assert result is None


class TestDAGUpdateNode:
    @pytest.mark.asyncio
    async def test_update_node_status(self, db_session):
        spec = _sample_dag()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.update_node_status(
            db_session, "dag-test-1", "n1", "completed", result="step done"
        )
        assert result["status"] == "completed"
        assert result["result"] == "step done"


class TestDAGApprove:
    @pytest.mark.asyncio
    async def test_approve_dag(self, db_session):
        spec = _sample_dag()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        result = await _service.approve_dag(db_session, "dag-test-1")
        assert result["action"] == "approved"
        assert result["approved_nodes"] == 1  # n2 is approval type

        # 验证 approval 节点已变为 completed
        dag = await _service.get_dag(db_session, "dag-test-1")
        approval_node = next(n for n in dag["nodes"] if n["node_id"] == "n2")
        assert approval_node["status"] == "completed"


class TestDAGPendingNodes:
    @pytest.mark.asyncio
    async def test_get_pending_nodes(self, db_session):
        spec = _sample_dag()
        await _service.create_dag(db_session, spec["dag_id"], spec["nodes"], spec["edges"])
        # 初始:n1 无前驱,可执行;n2 前驱 n1 未完成,不可执行
        pending = await _service.get_pending_nodes(db_session, "dag-test-1")
        assert len(pending) == 1
        assert pending[0]["node_id"] == "n1"

        # 完成 n1 后,n2 的前驱已完成
        await _service.update_node_status(db_session, "dag-test-1", "n1", "completed")
        pending = await _service.get_pending_nodes(db_session, "dag-test-1")
        pending_ids = [p["node_id"] for p in pending]
        assert "n2" in pending_ids
