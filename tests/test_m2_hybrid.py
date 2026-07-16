# tests/test_m2_hybrid.py
import pytest
from pathlib import Path
from server.kb.retrieval.hybrid import HybridSearcher, SearchResult
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.frontmatter import FrontMatter


@pytest.fixture
def setup_kb(tmp_path):
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    docs = [
        ("kb-001", "Python 编程入门", "private", "Python 是一门易学的编程语言，适合初学者"),
        ("kb-002", "FastAPI Web 开发", "private", "FastAPI 是现代的 Python Web 框架"),
        ("kb-003", "数据库设计原则", "public", "数据库设计需要考虑范式化和性能优化"),
    ]
    for doc_id, title, scope, content in docs:
        fm = FrontMatter(
            id=doc_id, title=title, type="note", scope=scope,
            source_type="manual", confidence=0.9, checksum=f"sha256:{doc_id}",
            tags=[title.split()[0].lower()],
        )
        repo.save(fm, f"# {title}\n\n{content}")
    chunks = [{
        "id": f"{doc_id}-chunk-000", "doc_id": doc_id, "text": content,
        "scope": scope, "tags": [title.split()[0].lower()],
    } for doc_id, title, scope, content in docs]
    store.upsert(chunks)
    return repo, store


def test_hybrid_search_basic(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("Python 编程", scope="private", top_k=2)
    assert len(results) > 0
    assert any(r.doc_id == "kb-001" for r in results)

def test_hybrid_search_scope_filter(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("数据库", scope="private", top_k=10)
    assert all(r.scope == "private" for r in results)

def test_hybrid_search_source_method(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("Python", scope="private", top_k=5)
    assert all(hasattr(r, "source_method") for r in results)

def test_search_result_dataclass():
    r = SearchResult(doc_id="kb-001", chunk_text="test", score=0.9,
                     source_method="vector", scope="private", title="测试")
    assert r.doc_id == "kb-001"
    assert r.source_method == "vector"
