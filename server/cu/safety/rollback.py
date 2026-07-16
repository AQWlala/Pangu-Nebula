# server/cu/safety/rollback.py
"""回滚策略管理器"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RollbackResult:
    success: bool
    rolled_back_count: int
    skipped_count: int
    errors: list[str] = field(default_factory=list)


class RollbackManager:
    def __init__(self):
        self.recorded_steps: list[dict] = []

    def record_step(self, step: dict):
        self.recorded_steps.append(step)

    async def rollback_task(self, task_id: str, to_step: int = 0) -> RollbackResult:
        return self.rollback_task_sync(task_id, to_step)

    def rollback_task_sync(self, task_id: str, to_step: int = 0) -> RollbackResult:
        rolled_back = 0
        skipped = 0
        for step in reversed(self.recorded_steps):
            if step["step_index"] < to_step:
                break
            if not step.get("reversible", False):
                skipped += 1
                continue
            if step.get("rollback_action"):
                rolled_back += 1
        return RollbackResult(True, rolled_back, skipped)
