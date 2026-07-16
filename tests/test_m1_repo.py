# tests/test_m1_repo.py
import pytest
from pathlib import Path
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.frontmatter import FrontMatter
from server.kb.storage.inbox import InboxWriter


@pytest.fixture
def temp_repo(tmp_path):
    return DocumentRepo(documents_dir=tmp_path / "documents")


def test_repo_save_and_read(temp_repo):
    fm = FrontMatter(
        id="kb-test-001", title="测试文档", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:abc",
    )
    temp_repo.save(fm, "# 正文内容")
    read_fm, read_body = temp_repo.read("kb-test-001")
    assert read_fm.id == "kb-test-001"
    assert "# 正文内容" in read_body

def test_repo_delete(temp_repo):
    fm = FrontMatter(
        id="kb-test-002", title="待删除", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:def",
    )
    temp_repo.save(fm, "content")
    assert temp_repo.exists("kb-test-002")
    temp_repo.delete("kb-test-002")
    assert not temp_repo.exists("kb-test-002")

def test_repo_list(temp_repo):
    for i in range(3):
        fm = FrontMatter(
            id=f"kb-test-{i:03d}", title=f"文档{i}", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum=f"sha256:{i}",
        )
        temp_repo.save(fm, f"内容{i}")
    docs = temp_repo.list_all()
    assert len(docs) == 3


@pytest.fixture
def temp_inbox(tmp_path):
    return InboxWriter(inbox_dir=tmp_path / "_inbox")


def test_inbox_stage(temp_inbox):
    pending_id = temp_inbox.stage(
        original_filename="report.pdf",
        converted_md="# 导入的报表\n\n数据...",
        frontmatter=FrontMatter(
            id="kb-import-001", title="导入的报表", type="doc", scope="private",
            source_type="import", source_original_path="/path/to/report.pdf",
            confidence=0.85, checksum="sha256:import1",
        ),
        meta={"parser": "pdf_parser", "confidence": 0.85},
    )
    assert pending_id is not None
    pending = temp_inbox.get_pending(pending_id)
    assert pending is not None
    assert "导入的报表" in pending["converted_md"]

def test_inbox_list_pending(temp_inbox):
    for i in range(2):
        temp_inbox.stage(
            original_filename=f"file{i}.txt",
            converted_md=f"# 文件{i}",
            frontmatter=FrontMatter(
                id=f"kb-import-{i}", title=f"文件{i}", type="note", scope="private",
                source_type="import", confidence=0.8, checksum=f"sha256:{i}",
            ),
            meta={"parser": "markdown"},
        )
    pending_list = temp_inbox.list_pending()
    assert len(pending_list) == 2

def test_inbox_approve_and_remove(temp_inbox):
    pending_id = temp_inbox.stage(
        original_filename="test.md",
        converted_md="# test",
        frontmatter=FrontMatter(
            id="kb-approve-001", title="approve test", type="note", scope="private",
            source_type="import", confidence=0.9, checksum="sha256:approve",
        ),
        meta={},
    )
    temp_inbox.remove_pending(pending_id)
    assert temp_inbox.get_pending(pending_id) is None
