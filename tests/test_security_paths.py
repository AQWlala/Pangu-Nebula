# tests/test_security_paths.py
"""Security tests: path traversal protection for inbox, audit_log, and repo."""
import pytest
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.repo import DocumentRepo
from server.cu.safety.audit_log import AuditLogger


def test_inbox_rejects_path_traversal(tmp_path):
    inbox = InboxWriter(inbox_dir=tmp_path / "_inbox")
    with pytest.raises(ValueError):
        inbox.get_pending("../../../etc/passwd")


def test_inbox_rejects_dotdot(tmp_path):
    inbox = InboxWriter(inbox_dir=tmp_path / "_inbox")
    with pytest.raises(ValueError):
        inbox.remove_pending("..")


def test_repo_rejects_dotdot(tmp_path):
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    with pytest.raises(ValueError):
        repo.read("../../../etc/passwd")


def test_repo_rejects_null_byte(tmp_path):
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    with pytest.raises(ValueError):
        repo.read("doc\x00malicious")


def test_audit_log_rejects_path_traversal(tmp_path):
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    with pytest.raises(ValueError):
        logger.get_task_logs("../../../etc/passwd")
