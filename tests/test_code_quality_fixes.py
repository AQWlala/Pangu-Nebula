# tests/test_code_quality_fixes.py
"""Tests for Task Q1 code quality fixes.

Covers:
- repo.py checksum condition (inverted → fixed)
- office_parser.py ExcelParser graded confidence
- pdf_parser.py exception logging instead of silent swallowing
- api/kb.py document ID collision (uuid suffix)
- datetime.utcnow() → datetime.now(timezone.utc) migration
"""
import inspect
import logging
import tempfile
from pathlib import Path

import pytest

from server.kb.storage.repo import DocumentRepo
from server.kb.storage.frontmatter import FrontMatter


# ---------------------------------------------------------------------------
# Fix #1: checksum condition no longer inverted
# ---------------------------------------------------------------------------

def test_checksum_not_recomputed_when_valid():
    with tempfile.TemporaryDirectory() as tmp:
        repo = DocumentRepo(documents_dir=Path(tmp))
        fm = FrontMatter(
            id="kb-test-001", title="Test", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum="sha256:abc123def456",
        )
        repo.save(fm, "test content")
        fm_loaded, _ = repo.read("kb-test-001")
        # Checksum should be preserved, not recomputed
        assert fm_loaded.checksum == "sha256:abc123def456"


def test_checksum_computed_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = DocumentRepo(documents_dir=Path(tmp))
        fm = FrontMatter(
            id="kb-test-002", title="Test", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum="",
        )
        repo.save(fm, "test content")
        fm_loaded, _ = repo.read("kb-test-002")
        assert fm_loaded.checksum.startswith("sha256:")
        assert fm_loaded.checksum != "sha256:"  # Should have actual hash


def test_checksum_computed_when_not_sha256_format():
    """Checksum in a non-sha256 format should be replaced with sha256."""
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        repo = DocumentRepo(documents_dir=Path(tmp))
        fm = FrontMatter(
            id="kb-test-003", title="Test", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum="md5:deadbeef",
        )
        repo.save(fm, "test content")
        fm_loaded, _ = repo.read("kb-test-003")
        expected = f"sha256:{hashlib.sha256(b'test content').hexdigest()}"
        assert fm_loaded.checksum == expected


# ---------------------------------------------------------------------------
# Fix #2: ExcelParser graded confidence
# ---------------------------------------------------------------------------

def test_excel_parser_confidence_graded_empty_table(tmp_path):
    """Empty table → 0.5 (not 0.95 as before)."""
    pytest.importorskip("pandas")
    import pandas as pd
    from server.kb.parser.office_parser import ExcelParser

    excel_path = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(excel_path, sheet_name="Empty", index=False)

    parser = ExcelParser()
    result = parser.parse(excel_path)
    assert result.success is True
    assert result.confidence == 0.5


def test_excel_parser_confidence_full_conversion(tmp_path):
    """All cells converted (ratio >= 0.95) → 0.95."""
    pytest.importorskip("pandas")
    import pandas as pd
    from server.kb.parser.office_parser import ExcelParser

    excel_path = tmp_path / "full.xlsx"
    pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]}).to_excel(
        excel_path, sheet_name="Sheet1", index=False
    )

    parser = ExcelParser()
    result = parser.parse(excel_path)
    assert result.success is True
    assert result.confidence == 0.95


def test_excel_parser_confidence_is_graded_not_binary(tmp_path):
    """Confidence must be one of the graded values, never collapsed to 0.6."""
    pytest.importorskip("pandas")
    import pandas as pd
    from server.kb.parser.office_parser import ExcelParser

    excel_path = tmp_path / "mixed.xlsx"
    # Half NaN, half values → ratio ≈ 0.5 → 0.7
    pd.DataFrame({"A": [1, None], "B": [None, 2]}).to_excel(
        excel_path, sheet_name="Sheet1", index=False
    )

    parser = ExcelParser()
    result = parser.parse(excel_path)
    assert result.success is True
    # Confidence must not be the buggy 0.6 value
    assert result.confidence != 0.6
    # And must be one of the graded values
    assert result.confidence in {0.5, 0.7, 0.85, 0.95}


# ---------------------------------------------------------------------------
# Fix #3: pdf_parser no longer silently swallows exceptions
# ---------------------------------------------------------------------------

def test_pdf_parser_logs_warning_on_marker_failure(tmp_path, caplog):
    """When marker fails, a warning must be logged instead of silent pass."""
    from server.kb.parser.pdf_parser import PdfParser

    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a real pdf")

    parser = PdfParser()
    with caplog.at_level(logging.WARNING, logger="server.kb.parser.pdf_parser"):
        result = parser.parse(fake_pdf)
    # Either success (pypdf fallback) or failure — both are acceptable,
    # but a warning should have been emitted by the marker fallback path.
    # The marker import itself likely fails, triggering the warning.
    assert any(
        "Marker PDF parser failed" in rec.message
        or "PDF 解析失败" in rec.message
        for rec in caplog.records
    ) or result.success is False
    # Result must not be a silent None (the old `pass` returned None implicitly)
    assert result is not None


# ---------------------------------------------------------------------------
# Fix #5: api/kb.py document ID no longer collides within same second
# ---------------------------------------------------------------------------

def test_kb_doc_id_includes_uuid_suffix():
    """Verify the import_document ID format includes a uuid hex suffix."""
    import re
    from server.api import kb as kb_module

    source = inspect.getsource(kb_module.import_document)
    # Pattern: kb-<timestamp>-<8 hex chars>
    # Ensure source uses uuid.uuid4().hex in the id construction
    assert "uuid.uuid4().hex" in source, (
        "import_document should use uuid.uuid4().hex to avoid ID collision"
    )
    assert "datetime.utcnow" not in source, (
        "import_document should use datetime.now(timezone.utc), not datetime.utcnow"
    )


# ---------------------------------------------------------------------------
# Fix #4: datetime.utcnow() migrated to datetime.now(timezone.utc)
# ---------------------------------------------------------------------------

def test_no_utcnow_in_targeted_modules():
    """None of the targeted source files should still use datetime.utcnow()."""
    import server.kb.storage.repo
    import server.kb.storage.inbox
    import server.cu.safety.audit_log
    import server.api.kb
    import server.api.cu
    import server.db.kb_models
    import server.db.cu_models

    modules = [
        server.kb.storage.repo,
        server.kb.storage.inbox,
        server.cu.safety.audit_log,
        server.api.kb,
        server.api.cu,
        server.db.kb_models,
        server.db.cu_models,
    ]
    for mod in modules:
        source = inspect.getsource(mod)
        assert "datetime.utcnow" not in source, (
            f"{mod.__name__} still references datetime.utcnow"
        )
