# tests/test_m2_vectorstore.py
import pytest
from pathlib import Path

# chromadb 是可选依赖，未安装时跳过而非报错
pytest.importorskip("chromadb")

from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.retrieval.indexer import Indexer


@pytest.fixture
def temp_store(tmp_path):
    return ChromaVectorStore(persist_dir=tmp_path / "chroma")


def test_vectorstore_add_and_query(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "Python 是一门编程语言", "scope": "private", "tags": ["python"]},
        {"id": "chunk-002", "doc_id": "doc-002", "text": "FastAPI 是 Web 框架", "scope": "private", "tags": ["fastapi"]},
    ]
    temp_store.upsert(chunks)
    results = temp_store.query("编程语言", scope="private", top_k=2)
    assert len(results) > 0
    assert results[0]["doc_id"] in ["doc-001", "doc-002"]

def test_vectorstore_scope_filter(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "私有内容", "scope": "private", "tags": []},
        {"id": "chunk-002", "doc_id": "doc-002", "text": "公开内容", "scope": "public", "tags": []},
    ]
    temp_store.upsert(chunks)
    results = temp_store.query("内容", scope="private", top_k=10)
    assert all(r["scope"] == "private" for r in results)

def test_vectorstore_delete_by_doc(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "test", "scope": "private", "tags": []},
    ]
    temp_store.upsert(chunks)
    temp_store.delete_by_doc_id("doc-001")
    results = temp_store.query("test", scope="private", top_k=10)
    assert len(results) == 0


@pytest.fixture
def temp_indexer(tmp_path):
    from server.kb.storage.repo import DocumentRepo
    from server.kb.storage.frontmatter import FrontMatter
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    for i in range(3):
        fm = FrontMatter(
            id=f"kb-test-{i:03d}", title=f"测试文档{i}", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum=f"sha256:{i}",
        )
        repo.save(fm, f"# 文档{i}\n\n这是测试内容{i}，关于Python编程")
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    return Indexer(repo=repo, vector_store=store)


def test_indexer_build_index(temp_indexer):
    result = temp_indexer.build_index()
    assert result.success is True
    assert result.indexed_count == 3

def test_indexer_incremental_update(temp_indexer):
    temp_indexer.build_index()
    result = temp_indexer.build_index()
    assert result.indexed_count == 0
