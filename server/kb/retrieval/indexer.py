# server/kb/retrieval/indexer.py
"""索引构建器"""
from __future__ import annotations
from dataclasses import dataclass
from server.kb.storage.repo import DocumentRepo
from server.kb.retrieval.vectorstore import ChromaVectorStore


@dataclass
class IndexResult:
    success: bool
    indexed_count: int
    skipped_count: int
    error: str = ""


class Indexer:
    """文档索引构建器（增量更新）"""

    def __init__(self, repo: DocumentRepo, vector_store: ChromaVectorStore):
        self.repo = repo
        self.vector_store = vector_store
        self._indexed_checksums: set[str] = set()

    def build_index(self) -> IndexResult:
        doc_ids = self.repo.list_all()
        indexed = 0
        skipped = 0

        for doc_id in doc_ids:
            fm, body = self.repo.read(doc_id)
            if fm.checksum in self._indexed_checksums:
                skipped += 1
                continue
            chunks = self._chunk_document(doc_id, fm, body)
            self.vector_store.upsert(chunks)
            self._indexed_checksums.add(fm.checksum)
            indexed += 1

        return IndexResult(True, indexed, skipped)

    def _chunk_document(self, doc_id: str, fm, body: str) -> list[dict]:
        chunks = []
        sections = body.split("\n## ")
        for idx, section in enumerate(sections):
            if not section.strip():
                continue
            chunk_text = section if idx == 0 else f"## {section}"
            chunks.append({
                "id": f"{doc_id}-chunk-{idx:03d}",
                "doc_id": doc_id, "text": chunk_text,
                "scope": fm.scope, "tags": fm.tags,
                "chunk_idx": idx, "section": chunk_text.split("\n")[0][:100],
            })
        return chunks
