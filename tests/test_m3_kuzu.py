# tests/test_m3_kuzu.py
import pytest
from pathlib import Path
from server.kb.graph.kuzu_store import KuzuGraphStore


@pytest.fixture
def temp_store(tmp_path):
    return KuzuGraphStore(db_dir=tmp_path / "kuzu")


def test_kuzu_init_schema(temp_store):
    temp_store.init_schema()
    tables = temp_store.list_tables()
    assert "Document" in tables
    assert "Entity" in tables


def test_kuzu_add_document(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "测试文档", "note", "private", 0.9, "documents/kb-001.md")
    docs = temp_store.list_documents(scope="private")
    assert len(docs) == 1
    assert docs[0]["id"] == "kb-001"


def test_kuzu_add_relation(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "文档1", "note", "private", 0.9, "doc1.md")
    temp_store.add_document("kb-002", "文档2", "note", "private", 0.9, "doc2.md")
    temp_store.add_relation("kb-001", "kb-002", "References", 0.8)
    relations = temp_store.get_relations("kb-001")
    assert len(relations) == 1
    assert relations[0]["target_id"] == "kb-002"


def test_kuzu_get_neighbors(temp_store):
    temp_store.init_schema()
    for i in range(1, 4):
        temp_store.add_document(f"kb-00{i}", f"文档{i}", "note", "private", 0.9, f"doc{i}.md")
    temp_store.add_relation("kb-001", "kb-002", "References", 0.8)
    temp_store.add_relation("kb-002", "kb-003", "Extends", 0.7)
    neighbors = temp_store.get_neighbors("kb-001", depth=2, scope="private")
    neighbor_ids = [n["id"] for n in neighbors]
    assert "kb-002" in neighbor_ids


def test_kuzu_scope_filter(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "私有", "note", "private", 0.9, "doc1.md")
    temp_store.add_document("kb-002", "公开", "note", "public", 0.9, "doc2.md")
    private_docs = temp_store.list_documents(scope="private")
    assert len(private_docs) == 1
    assert private_docs[0]["id"] == "kb-001"
