# tests/test_graph_relations.py
import pytest
import tempfile
from pathlib import Path

# kuzu 是可选依赖，未安装时跳过而非报错
pytest.importorskip("kuzu")


def test_rebuild_graph_creates_relations():
    """Test that rebuild_graph creates both nodes and edges."""
    with tempfile.TemporaryDirectory() as tmp:
        from server.config_kb_cu import KBConfig
        config = KBConfig(kb_root=Path(tmp) / "kb")
        config.ensure_dirs()

        from server.kb.storage.repo import DocumentRepo
        from server.kb.storage.frontmatter import FrontMatter

        repo = DocumentRepo(documents_dir=config.documents_dir)

        # Create two documents with shared tags (overlap >= 0.5 to produce a relation)
        fm1 = FrontMatter(
            id="kb-graph-001", title="Python Basics", type="note",
            scope="private", source_type="manual", confidence=0.9,
            checksum="sha256:abc1", tags=["python", "programming", "tutorial"],
        )
        fm2 = FrontMatter(
            id="kb-graph-002", title="Advanced Python", type="note",
            scope="private", source_type="manual", confidence=0.9,
            checksum="sha256:abc2", tags=["python", "programming", "advanced"],
        )
        repo.save(fm1, "Python basics content")
        repo.save(fm2, "Advanced Python content")

        # Rebuild graph
        from server.kb.graph.kuzu_store import KuzuGraphStore
        store = KuzuGraphStore(db_dir=config.kuzu_dir)
        store.init_schema()

        from server.kb.graph.relation_extractor import RelationExtractor
        extractor = RelationExtractor()

        documents = [fm1, fm2]
        for doc in documents:
            store.add_document(doc.id, doc.title, doc.type, doc.scope, doc.confidence, doc.id)

        relation_count = 0
        for i, doc in enumerate(documents):
            candidates = extractor.recommend_relations(doc, documents[i + 1:])
            for rel in candidates:
                store.add_relation(rel.source_id, rel.target_id, rel.relation_type, rel.confidence)
                relation_count += 1

        assert relation_count > 0, "Should have created at least one relation"

        # Verify relations exist
        relations = store.get_relations("kb-graph-001")
        assert len(relations) > 0


def test_relation_extractor_tag_similarity():
    """Test that RelationExtractor recommends relations based on shared tags."""
    from server.kb.graph.relation_extractor import RelationExtractor
    from server.kb.storage.frontmatter import FrontMatter

    extractor = RelationExtractor()

    source = FrontMatter(
        id="kb-rel-001", title="Source", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:abc", tags=["python", "ai", "ml"],
    )
    candidate = FrontMatter(
        id="kb-rel-002", title="Candidate", type="note",
        scope="private", source_type="manual", confidence=0.9,
        checksum="sha256:def", tags=["python", "ai", "data"],
    )

    recommendations = extractor.recommend_relations(source, [candidate])
    assert len(recommendations) > 0
    assert recommendations[0].source_id == "kb-rel-001"
    assert recommendations[0].target_id == "kb-rel-002"
