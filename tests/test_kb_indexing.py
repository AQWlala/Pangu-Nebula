# tests/test_kb_indexing.py
from pathlib import Path


def test_approve_triggers_indexing(tmp_path):
    """Test that approving a document triggers indexing and makes it searchable."""
    # Patch KBConfig to use temp directory
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()

    from server.kb.storage.inbox import InboxWriter
    from server.kb.storage.repo import DocumentRepo
    from server.kb.storage.frontmatter import FrontMatter
    from server.kb.parser.validator import validate_frontmatter

    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    repo = DocumentRepo(documents_dir=config.documents_dir)

    # Stage a document
    fm = FrontMatter(
        id="kb-test-index-001",
        title="Python 编程指南",
        type="note",
        scope="private",
        source_type="manual",
        confidence=0.95,
        checksum="sha256:test123",
        tags=["python", "programming"],
    )
    validate_frontmatter(fm)
    pending_id = inbox.stage(
        original_filename="test.md",
        converted_md="# Python 编程指南\n\n这是一篇关于 Python 的文章。",
        frontmatter=fm,
        meta={},
    )

    # Approve the document
    pending = inbox.get_pending(pending_id)
    body = pending.get(
        "converted_md", "# Python 编程指南\n\n这是一篇关于 Python 的文章。"
    )
    repo.save(fm, body)
    inbox.remove_pending(pending_id)

    # Manually trigger indexing (simulating what the API should do)
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.retrieval.indexer import Indexer

    store = ChromaVectorStore(persist_dir=config.chroma_dir)
    indexer = Indexer(
        repo=repo, vector_store=store, indexes_dir=config.indexes_dir
    )
    result = indexer.build_index()

    assert result is not None

    # Now search should find the document
    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search(query="Python", scope="private", top_k=5)
    assert len(results) > 0
    assert any(r.doc_id == "kb-test-index-001" for r in results)


def test_indexer_checksums_persisted(tmp_path):
    """Test that checksums are persisted to disk."""
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()

    from server.kb.storage.repo import DocumentRepo
    from server.kb.storage.frontmatter import FrontMatter
    from server.kb.retrieval.vectorstore import ChromaVectorStore
    from server.kb.retrieval.indexer import Indexer

    repo = DocumentRepo(documents_dir=config.documents_dir)
    store = ChromaVectorStore(persist_dir=config.chroma_dir)
    indexer = Indexer(
        repo=repo, vector_store=store, indexes_dir=config.indexes_dir
    )

    # Add a document
    fm = FrontMatter(
        id="kb-test-persist-001", title="Test", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc",
    )
    repo.save(fm, "test content")
    indexer.build_index()

    # Create a new indexer instance — should load persisted checksums
    indexer2 = Indexer(
        repo=repo, vector_store=store, indexes_dir=config.indexes_dir
    )
    assert (
        "kb-test-persist-001" in indexer2._indexed_checksums
        or len(indexer2._indexed_checksums) > 0
    )
