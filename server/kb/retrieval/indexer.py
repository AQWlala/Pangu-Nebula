# server/kb/retrieval/indexer.py
"""索引构建器"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
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

    def __init__(
        self,
        repo: DocumentRepo,
        vector_store: ChromaVectorStore,
        indexes_dir: Path | None = None,
    ):
        self.repo = repo
        self.vector_store = vector_store
        self.indexes_dir = indexes_dir
        self._checksums_file = indexes_dir / "checksums.json" if indexes_dir else None
        self._indexed_checksums: dict[str, str] = self._load_checksums()

    def _load_checksums(self) -> dict[str, str]:
        """Load persisted checksums from disk."""
        if self._checksums_file and self._checksums_file.exists():
            try:
                with open(self._checksums_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_checksums(self) -> None:
        """Persist checksums to disk."""
        if not self._checksums_file or not self.indexes_dir:
            return
        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        with open(self._checksums_file, "w", encoding="utf-8") as f:
            json.dump(self._indexed_checksums, f, ensure_ascii=False)

    def build_index(self) -> IndexResult:
        doc_ids = self.repo.list_all()
        indexed = 0
        skipped = 0

        for doc_id in doc_ids:
            fm, body = self.repo.read(doc_id)
            if self._indexed_checksums.get(doc_id) == fm.checksum:
                skipped += 1
                continue
            chunks = self._chunk_document(doc_id, fm, body)
            self.vector_store.upsert(chunks)
            self._indexed_checksums[doc_id] = fm.checksum
            indexed += 1

        self._save_checksums()
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
