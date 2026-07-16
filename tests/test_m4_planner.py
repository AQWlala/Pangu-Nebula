# tests/test_m4_planner.py
import pytest
from server.cu.planner import CUTaskPlanner, CUTaskStep
from server.cu.safety.rollback import RollbackManager
from server.cu.executor.action_types import ActionType


def test_planner_atomic_decomposition():
    planner = CUTaskPlanner()
    plan = planner.plan_manual("访问 example.com", [
        {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"},
         "success_criteria": {"url_contains": "example.com"}},
    ])
    assert len(plan.steps) == 1
    assert plan.steps[0].timeout_ms == 3000
    assert plan.steps[0].rollback_strategy is not None

def test_planner_step_must_have_success_criteria():
    planner = CUTaskPlanner()
    with pytest.raises(ValueError, match="success_criteria"):
        planner.plan_manual("test", [
            {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"}},
        ])

def test_planner_max_timeout_enforced():
    planner = CUTaskPlanner()
    with pytest.raises(ValueError, match="timeout"):
        planner.plan_manual("test", [
            {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"},
             "success_criteria": {"url_contains": "example"}, "timeout_ms": 30000},
        ])

def test_rollback_manager_reversible():
    manager = RollbackManager()
    manager.recorded_steps = [
        {"step_index": 1, "action_type": "browser_navigate",
         "rollback_action": "browser_navigate", "reversible": True},
    ]
    result = manager.rollback_task_sync("cutask-001", to_step=0)
    assert result.success is True
    assert result.rolled_back_count == 1

def test_action_type_reversibility():
    assert ActionType.is_reversible("browser_navigate") is True
    assert ActionType.is_reversible("fs_delete") is False
