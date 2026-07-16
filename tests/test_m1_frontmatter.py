# tests/test_m1_frontmatter.py
import pytest
from server.kb.storage.frontmatter import parse_frontmatter, dump_frontmatter, FrontMatter
from server.kb.parser.validator import validate_frontmatter, ValidationError

def test_parse_frontmatter_valid():
    content = """---
id: kb-20260716-001
title: "测试文档"
type: note
scope: private
confidence: 0.95
checksum: sha256:abc123
---

# 正文"""
    fm, body = parse_frontmatter(content)
    assert fm.id == "kb-20260716-001"
    assert fm.title == "测试文档"
    assert fm.type == "note"
    assert fm.scope == "private"
    assert fm.confidence == 0.95
    assert body.startswith("# 正文")

def test_parse_frontmatter_no_frontmatter():
    content = "# 纯正文无 front matter"
    fm, body = parse_frontmatter(content)
    assert fm is None
    assert body == content

def test_dump_frontmatter_roundtrip():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    dumped = dump_frontmatter(fm)
    fm2, _ = parse_frontmatter(dumped + "\n\n# body")
    assert fm2.id == fm.id
    assert fm2.title == fm.title

def test_validate_frontmatter_missing_id():
    fm = FrontMatter(
        id="", title="测试", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="id"):
        validate_frontmatter(fm)

def test_validate_frontmatter_invalid_scope():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="invalid_scope",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="scope"):
        validate_frontmatter(fm)

def test_validate_frontmatter_invalid_type():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="invalid_type", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="type"):
        validate_frontmatter(fm)

def test_validate_frontmatter_confidence_range():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="private",
        source_type="manual", confidence=1.5, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="confidence"):
        validate_frontmatter(fm)
