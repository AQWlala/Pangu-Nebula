# tests/test_cu_executor.py
import tempfile
from pathlib import Path

import pytest

from server.cu.executor.runner import CUExecutor
from server.cu.safety.emergency_stop import EmergencyStop
from server.config_kb_cu import CUConfig


def test_executor_runs_steps():
    es = EmergencyStop()
    with tempfile.TemporaryDirectory() as tmp:
        config = CUConfig(audit_log_dir=Path(tmp) / "audit")
        executor = CUExecutor(config=config, emergency_stop=es)

        steps = [
            {"step_index": 0, "action_type": "browser_navigate",
             "action_payload": {"url": "https://example.com"},
             "success_criteria": {"url_contains": "example"},
             "timeout_ms": 3000,
             "rollback_strategy": {"action": "browser_navigate", "payload": {"url": "about:blank"}}},
        ]
        result = executor.run_task("cutask-test-001", steps)
        assert result["status"] == "completed"
        assert result["executed_steps"] == 1


def test_executor_emergency_stop():
    es = EmergencyStop()
    es.trigger("test")

    with tempfile.TemporaryDirectory() as tmp:
        config = CUConfig(audit_log_dir=Path(tmp) / "audit")
        executor = CUExecutor(config=config, emergency_stop=es)

        steps = [{"step_index": 0, "action_type": "browser_navigate",
                  "action_payload": {"url": "https://example.com"},
                  "success_criteria": {}, "timeout_ms": 3000}]
        result = executor.run_task("cutask-test-002", steps)
        assert result["status"] == "stopped"


def test_executor_failed_step_triggers_rollback():
    es = EmergencyStop()
    with tempfile.TemporaryDirectory() as tmp:
        config = CUConfig(audit_log_dir=Path(tmp) / "audit")
        executor = CUExecutor(config=config, emergency_stop=es)

        # Step with impossible success criteria
        steps = [{"step_index": 0, "action_type": "browser_navigate",
                  "action_payload": {"url": "https://example.com"},
                  "success_criteria": {"url_contains": "impossible_string_not_in_result"},
                  "timeout_ms": 3000}]
        result = executor.run_task("cutask-test-003", steps)
        assert result["status"] == "failed"


def test_executor_audit_log_written():
    es = EmergencyStop()
    with tempfile.TemporaryDirectory() as tmp:
        audit_dir = Path(tmp) / "audit"
        config = CUConfig(audit_log_dir=audit_dir)
        executor = CUExecutor(config=config, emergency_stop=es)

        steps = [{"step_index": 0, "action_type": "browser_navigate",
                  "action_payload": {"url": "https://example.com"},
                  "success_criteria": {}, "timeout_ms": 3000}]
        executor.run_task("cutask-test-004", steps)

        # Verify audit log was written
        from server.cu.safety.audit_log import AuditLogger
        logger = AuditLogger(log_dir=audit_dir)
        logs = logger.get_task_logs("cutask-test-004")
        assert len(logs) >= 1
        assert logs[0]["action_type"] == "browser_navigate"
