# tests/test_safety_quartet.py
"""Task S3: CU 安全四件套加固测试"""
import pytest
import tempfile
from pathlib import Path

from server.cu.safety.emergency_stop import EmergencyStop, EmergencyStopError
from server.cu.safety.audit_log import AuditLogger
from server.cu.sandbox.fs_sandbox import FsSandbox, SandboxViolation


def test_emergency_stop_threading_event():
    es = EmergencyStop()
    assert not es.is_triggered()
    es.trigger("test")
    assert es.is_triggered()
    with pytest.raises(EmergencyStopError):
        es.check()
    es.reset()
    assert not es.is_triggered()
    es.check()  # Should not raise


def test_emergency_stop_reason_preserved():
    es = EmergencyStop()
    es.trigger("disk full")
    assert es.reason == "disk full"
    es.reset()
    assert es.reason is None


def test_audit_log_append_only():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp))
        logger.log_step("cutask-20260101-abc12345", 0, "test_action", {"key": "val"}, "success")
        logger.log_step("cutask-20260101-abc12345", 1, "test_action2", {}, "failed")
        logs = logger.get_task_logs("cutask-20260101-abc12345")
        assert len(logs) == 2
        assert logs[0]["step_index"] == 0
        assert logs[1]["step_index"] == 1
        # Verify hash chain
        assert logs[0]["prev_hash"] == ""
        assert logs[1]["prev_hash"] == logs[0]["hash"]


def test_audit_log_hash_chain_integrity():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp))
        entry0 = logger.log_step("cutask-20260101-deadbeef", 0, "nav", {"url": "a"}, "success")
        entry1 = logger.log_step("cutask-20260101-deadbeef", 1, "click", {"x": 1}, "success")
        assert "hash" in entry0
        assert "hash" in entry1
        assert entry1["prev_hash"] == entry0["hash"]


def test_audit_log_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp))
        with pytest.raises(ValueError):
            logger.log_step("../escape", 0, "x", {}, "success")


def test_fs_sandbox_rejects_symlink():
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "sandbox"
        sandbox.mkdir()
        fs = FsSandbox(sandbox_root=sandbox)
        # This should pass
        fs.validate_write(sandbox / "test.txt")
        # Create a symlink pointing outside
        symlink_path = sandbox / "evil"
        try:
            symlink_path.symlink_to("/etc/passwd")
            with pytest.raises((PermissionError, SandboxViolation)):
                fs.validate_write(symlink_path)
        except OSError:
            pass  # Symlink creation may fail on some systems


def test_fs_sandbox_write_allowed_in_sandbox(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox")
    target = tmp_path / "_sandbox" / "sub" / "file.txt"
    assert sandbox.validate_write(target) is True


def test_fs_sandbox_read_whitelist(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[docs])
    assert sandbox.validate_read(docs / "a.md") is True
