# server/cu/executor/runner.py
"""CU 任务执行器 — 接入安全四件套 + 结果验证 + 知识桥接"""
from __future__ import annotations
import logging
import time
from dataclasses import asdict

from server.config_kb_cu import CUConfig, KBConfig
from server.cu.planner import CUTaskStep
from server.cu.safety.emergency_stop import EmergencyStop, EmergencyStopError
from server.cu.safety.audit_log import AuditLogger
from server.cu.safety.rollback import RollbackManager
from server.cu.verifier import CUResultVerifier
from server.cu.knowledge_bridge import CUKnowledgeBridge
from server.kb.storage.inbox import InboxWriter

logger = logging.getLogger(__name__)


class CUExecutor:
    """执行 CU 任务，集成安全四件套。"""

    def __init__(
        self,
        config: CUConfig | None = None,
        emergency_stop: EmergencyStop | None = None,
    ):
        self.config = config or CUConfig()
        self.config.ensure_dirs()
        self.emergency_stop = emergency_stop or EmergencyStop()
        self.audit_logger = AuditLogger(log_dir=self.config.audit_log_dir)
        self.verifier = CUResultVerifier()
        self._rollback_managers: dict[str, RollbackManager] = {}

    def run_task(self, task_id: str, plan_steps: list[dict]) -> dict:
        """执行任务的所有步骤。

        Args:
            task_id: 任务 ID
            plan_steps: 步骤列表，每个步骤是 dict 包含 step_index, action_type,
                       action_payload, success_criteria, timeout_ms, rollback_strategy

        Returns:
            {"task_id": ..., "status": "completed"|"failed"|"stopped",
             "executed_steps": int, "results": [...]}
        """
        rollback_manager = RollbackManager()
        self._rollback_managers[task_id] = rollback_manager

        results: list[dict] = []
        executed_count = 0
        status = "executing"

        try:
            for step in plan_steps:
                # Check emergency stop before each step
                self.emergency_stop.check()

                step_result = self._execute_step(task_id, step, rollback_manager)
                results.append(step_result)

                if step_result["result_status"] == "failed":
                    status = "failed"
                    # Trigger rollback for all previously successful steps
                    logger.info(f"Step {step['step_index']} failed, triggering rollback")
                    rollback_result = rollback_manager.rollback_task_sync(task_id)
                    results.append({"type": "rollback", "result": asdict(rollback_result)})
                    break

                executed_count += 1
            else:
                status = "completed"

        except EmergencyStopError:
            logger.info(f"Task {task_id} stopped by emergency stop")
            status = "stopped"
            rollback_result = rollback_manager.rollback_task_sync(task_id)
            results.append({"type": "rollback", "result": asdict(rollback_result)})

        except Exception as e:
            logger.error(f"Task {task_id} failed with exception: {e}")
            status = "failed"
            try:
                rollback_result = rollback_manager.rollback_task_sync(task_id)
                results.append({"type": "rollback", "result": asdict(rollback_result)})
            except Exception as rb_err:
                logger.error(f"Rollback also failed: {rb_err}")

        # Generate knowledge candidates from results
        try:
            self._generate_knowledge(task_id, plan_steps, results, status)
        except Exception as e:
            logger.warning(f"Knowledge generation failed: {e}")

        return {
            "task_id": task_id,
            "status": status,
            "executed_steps": executed_count,
            "results": results,
        }

    def _execute_step(
        self, task_id: str, step: dict, rollback_manager: RollbackManager
    ) -> dict:
        """执行单个步骤。"""
        step_index = step["step_index"]
        action_type = step["action_type"]
        action_payload = step.get("action_payload", {})
        success_criteria = step.get("success_criteria", {})
        timeout_ms = step.get("timeout_ms", 3000)
        rollback_strategy = step.get("rollback_strategy")

        start_time = time.time()
        result_status = "success"
        result_data: dict | None = None

        try:
            # Execute the action (mock for now — actual browser/fs actions
            # would be dispatched here based on action_type)
            result_data = self._dispatch_action(action_type, action_payload, timeout_ms)

            # Build a CUTaskStep for the verifier (it expects a dataclass, not dict)
            step_obj = CUTaskStep(
                step_index=step_index,
                action_type=action_type,
                action_payload=action_payload,
                success_criteria=success_criteria,
                timeout_ms=timeout_ms,
                rollback_strategy=rollback_strategy,
            )
            actual_url = ""
            if isinstance(result_data, dict):
                actual_url = result_data.get("url", "")

            # Verify result — mock high confidence so criteria-met steps pass
            verification = self.verifier.verify_step_sync(
                step=step_obj,
                actual_url=actual_url,
                confidence=0.9,
            )
            if not verification.passed:
                result_status = "failed"
                result_data = {"verification": asdict(verification)}

        except EmergencyStopError:
            raise  # Re-raise for outer handler
        except Exception as e:
            result_status = "failed"
            result_data = {"error": str(e)}
            logger.warning(f"Step {step_index} action {action_type} failed: {e}")

        duration_ms = int((time.time() - start_time) * 1000)

        # Log to audit
        self.audit_logger.log_step(
            task_id=task_id,
            step_index=step_index,
            action_type=action_type,
            action_payload=action_payload,
            result_status=result_status,
            result_data=result_data,
            duration_ms=duration_ms,
        )

        # Record for rollback (only successful reversible steps)
        if rollback_strategy and result_status == "success":
            rollback_manager.record_step({
                "step_index": step_index,
                "action_type": action_type,
                "reversible": rollback_strategy.get("reversible", False),
                "rollback_action": rollback_strategy.get("rollback_action"),
                "rollback_payload": rollback_strategy.get("rollback_payload", {}),
            })

        return {
            "step_index": step_index,
            "action_type": action_type,
            "result_status": result_status,
            "result_data": result_data,
            "duration_ms": duration_ms,
        }

    def _dispatch_action(
        self, action_type: str, action_payload: dict, timeout_ms: int
    ) -> dict:
        """分发动作到具体执行器。当前为 mock，后续接入 Browser-Use / FsSandbox。"""
        # Check emergency stop
        self.emergency_stop.check()

        # Mock execution — simulate different action types
        if action_type == "browser_navigate":
            url = action_payload.get("url", "")
            return {"url": url, "title": f"Page: {url}", "status": "loaded"}
        elif action_type == "browser_click":
            return {"clicked": True, "selector": action_payload.get("selector", "")}
        elif action_type == "fs_write":
            # In production, would use FsSandbox here
            return {"written": True, "path": action_payload.get("path", "")}
        elif action_type == "fs_read":
            return {"content": "mock content", "path": action_payload.get("path", "")}
        else:
            return {"action": action_type, "status": "mocked"}

    def _generate_knowledge(
        self, task_id: str, steps: list[dict], results: list[dict], status: str
    ) -> None:
        """从执行结果生成知识候选项并写入 _inbox。"""
        kb_config = KBConfig()
        kb_config.ensure_dirs()

        # Filter out rollback entries so zip stays aligned with steps
        step_results_only = [
            r for r in results
            if not (isinstance(r, dict) and r.get("type") == "rollback")
        ]

        step_results = []
        for step, result in zip(steps, step_results_only):
            step_results.append({
                "step_index": step["step_index"],
                "action_type": step["action_type"],
                "action_payload": step.get("action_payload", {}),
                "result_status": result.get("result_status", "unknown"),
                "result_data": result.get("result_data"),
            })

        bridge = CUKnowledgeBridge(inbox_writer=InboxWriter(inbox_dir=kb_config.inbox_dir))
        candidates = bridge.action_to_knowledge_sync(
            task_id=task_id,
            step_results=step_results,
            instruction="",
        )

        if candidates:
            logger.info(f"Generated {len(candidates)} knowledge candidates for task {task_id}")

    def rollback_task(self, task_id: str, to_step: int | None = None) -> dict:
        """回滚指定任务。"""
        manager = self._rollback_managers.get(task_id)
        if not manager:
            return {"success": False, "error": "Task not found or no rollback data"}
        result = manager.rollback_task_sync(
            task_id, to_step=to_step if to_step is not None else 0
        )
        return {
            "success": result.success,
            "rolled_back_count": result.rolled_back_count,
            "skipped_count": result.skipped_count,
            "errors": result.errors,
        }
