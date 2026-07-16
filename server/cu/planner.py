# server/cu/planner.py
"""CU 任务规划器（原子化分解）"""
from __future__ import annotations
from dataclasses import dataclass, field
from server.cu.executor.action_types import ActionType
from server.config_kb_cu import CUConfig


@dataclass
class CUTaskStep:
    step_index: int
    action_type: str
    action_payload: dict
    success_criteria: dict
    timeout_ms: int = 3000
    rollback_strategy: dict | None = None
    requires_confirmation: bool = False
    allow_parallel: bool = False


@dataclass
class CUTaskPlan:
    instruction: str
    steps: list[CUTaskStep] = field(default_factory=list)
    created_at: str = ""


class CUTaskPlanner:
    # 保留为向后兼容回退值；实际运行时从 CUConfig 读取
    MAX_TIMEOUT_MS = 10000
    DEFAULT_TIMEOUT_MS = 3000

    def __init__(self, config: CUConfig | None = None):
        self._config = config if config is not None else CUConfig()

    def plan_manual(self, instruction: str, steps: list[dict]) -> CUTaskPlan:
        plan = CUTaskPlan(instruction=instruction)
        for i, step_def in enumerate(steps):
            plan.steps.append(self._validate_step(i, step_def))
        return plan

    def _validate_step(self, index, step_def):
        if "success_criteria" not in step_def or not step_def["success_criteria"]:
            raise ValueError(f"步骤 {index} 缺少 success_criteria")
        default_timeout_ms = self._config.default_step_timeout_ms
        max_timeout_ms = self._config.max_step_timeout_ms
        timeout_ms = step_def.get("timeout_ms", default_timeout_ms)
        if timeout_ms > max_timeout_ms:
            raise ValueError(f"步骤 {index} timeout_ms={timeout_ms} 超过最大值 {max_timeout_ms}")

        action_type = step_def["action_type"]
        rollback_action = ActionType.get_rollback_action(action_type)
        rollback_strategy = None
        if rollback_action:
            rollback_strategy = {"reversible": True, "rollback_action": rollback_action, "rollback_payload": {}}
        elif ActionType.is_irreversible(action_type):
            rollback_strategy = {"reversible": False, "note": "不可逆动作，仅记录"}

        return CUTaskStep(
            step_index=index, action_type=action_type,
            action_payload=step_def["action_payload"],
            success_criteria=step_def["success_criteria"],
            timeout_ms=timeout_ms, rollback_strategy=rollback_strategy,
            requires_confirmation=step_def.get("requires_confirmation", False),
            allow_parallel=step_def.get("allow_parallel", False),
        )
