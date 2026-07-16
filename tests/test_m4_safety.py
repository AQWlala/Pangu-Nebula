# tests/test_m4_safety.py
import pytest
from pathlib import Path
from server.cu.sandbox.fs_sandbox import FsSandbox, SandboxViolation
from server.cu.safety.emergency_stop import EmergencyStop, EmergencyStopError
from server.cu.safety.audit_log import AuditLogger


def test_fs_sandbox_write_allowed(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox")
    target = tmp_path / "_sandbox" / "test.txt"
    assert sandbox.validate_write(target) is True

def test_fs_sandbox_write_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[tmp_path / "documents"])
    target = tmp_path / "evil.txt"
    with pytest.raises(SandboxViolation, match="写操作越界"):
        sandbox.validate_write(target)

def test_fs_sandbox_read_allowed(tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[docs_dir])
    assert sandbox.validate_read(docs_dir / "doc.md") is True

def test_fs_sandbox_read_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[tmp_path / "documents"])
    with pytest.raises(SandboxViolation, match="读操作越界"):
        sandbox.validate_read(Path("/etc/passwd"))

def test_fs_sandbox_path_traversal_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox")
    evil_path = tmp_path / "_sandbox" / ".." / ".." / "etc" / "passwd"
    with pytest.raises(SandboxViolation):
        sandbox.validate_write(evil_path)


@pytest.mark.asyncio
async def test_emergency_stop_trigger():
    stop = EmergencyStop()
    assert not stop.is_triggered()
    stop.trigger(reason="test")
    assert stop.is_triggered()
    with pytest.raises(EmergencyStopError):
        stop.check()

def test_emergency_stop_reset():
    stop = EmergencyStop()
    stop._stop_flag.set()
    stop._reason = "test"
    stop.reset()
    assert not stop.is_triggered()
    stop.check()


def test_audit_log_write(tmp_path):
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    logger.log_step("cutask-001", 1, "browser_navigate", {"url": "https://example.com"},
                    "success", {"nav_url": "https://example.com"}, "logs/step01.png", 800)
    logs = logger.get_task_logs("cutask-001")
    assert len(logs) == 1
    assert logs[0]["action_type"] == "browser_navigate"

def test_audit_log_append_only(tmp_path):
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    logger.log_step("task-001", 1, "test", {}, "success", {}, None, 100)
    logger.log_step("task-001", 2, "test2", {}, "success", {}, None, 100)
    logs = logger.get_task_logs("task-001")
    assert len(logs) == 2
    assert logs[0]["step_index"] == 1
