# tests/test_type_annotations.py
"""Q2.2-Q2.4 类型注解与 StrEnum 迁移的回归测试。"""
from pathlib import Path

import pytest

from server.cu.executor.action_types import ActionType
from server.cu.planner import CUTaskPlanner, CUTaskStep
from server.cu.safety.audit_log import AuditLogger


# 期望的字符串值映射，用于校验 StrEnum 迁移后向后兼容
_EXPECTED_VALUES = {
    ActionType.BROWSER_NAVIGATE: "browser_navigate",
    ActionType.BROWSER_CLICK: "browser_click",
    ActionType.BROWSER_INPUT: "browser_input",
    ActionType.BROWSER_WAIT: "browser_wait",
    ActionType.BROWSER_EXTRACT: "browser_extract",
    ActionType.BROWSER_DOWNLOAD: "browser_download",
    ActionType.FS_WRITE: "fs_write",
    ActionType.FS_READ: "fs_read",
    ActionType.FS_DELETE: "fs_delete",
}


def test_action_type_members_are_str_instances():
    """Test 1: ActionType 枚举成员是 str 实例（StrEnum 特性）。"""
    for member in ActionType:
        assert isinstance(member, str), f"{member!r} 应当是 str 实例"


def test_action_type_values_backward_compatible():
    """Test 2: ActionType 枚举值与历史字符串一致（向后兼容）。"""
    for member, expected in _EXPECTED_VALUES.items():
        assert member.value == expected
        # 作为 str，直接取值也应等于字符串
        assert str(member) == expected


def test_action_type_string_comparisons():
    """Test 3: ActionType 可用于字符串比较（含 == 与 in 集合）。"""
    assert ActionType.FS_WRITE == "fs_write"
    assert ActionType.BROWSER_NAVIGATE == "browser_navigate"
    # 反向比较同样成立
    assert "fs_delete" == ActionType.FS_DELETE
    # if 语句中的字符串比较
    action = ActionType.BROWSER_CLICK
    if action == ActionType.BROWSER_CLICK:
        matched = True
    else:
        matched = False
    assert matched is True
    # 与纯字符串字面量比较
    assert action == "browser_click"
    # 集合成员判断向后兼容：传入纯字符串也能命中
    assert "browser_navigate" in ActionType.REVERSIBLE
    assert "fs_write" in ActionType.REVERSIBLE
    assert "fs_delete" not in ActionType.REVERSIBLE
    assert "fs_delete" in ActionType.IRREVERSIBLE


def test_imports_and_instantiation_smoke(tmp_path):
    """Test 4: 导入与实例化冒烟测试（类型注解改动后无导入错误）。"""
    # ActionType 类方法仍可用
    assert ActionType.is_reversible("browser_navigate") is True
    assert ActionType.is_irreversible("fs_delete") is True
    assert ActionType.get_rollback_action("fs_write") == "fs_delete"
    assert ActionType.get_rollback_action("browser_click") is None

    # AuditLogger 实例化 + 基本调用
    logger = AuditLogger(log_dir=tmp_path)
    entry = logger.log_step(
        task_id="task-smoke",
        step_index=0,
        action_type=ActionType.BROWSER_NAVIGATE,
        action_payload={"url": "https://example.com"},
        result_status="success",
        duration_ms=12,
    )
    assert entry["hash"]
    assert entry["prev_hash"] == ""
    logs = logger.get_task_logs("task-smoke")
    assert len(logs) == 1
    assert logs[0]["hash"] == entry["hash"]

    # CUTaskPlanner 实例化 + plan_manual 调用
    planner = CUTaskPlanner()
    plan = planner.plan_manual("smoke", [
        {"action_type": "browser_navigate",
         "action_payload": {"url": "https://example.com"},
         "success_criteria": {"url_contains": "example.com"}},
    ])
    assert isinstance(plan.steps[0], CUTaskStep)
    assert plan.steps[0].action_type == "browser_navigate"
