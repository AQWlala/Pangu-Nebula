# server/kb/retrieval/vectorstore.py
"""ChromaDB 嵌入式向量存储"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
import numpy as np


class _LocalHashEmbedding:
    """轻量级本地哈希嵌入函数（无需下载模型）。

    通过对文本 token 进行确定性哈希生成固定维度的向量，
    适用于测试与离线场景。语义质量不及 MiniLM-L6-v2，
    但足以支撑 ChromaDB 的存储/检索/过滤/删除等流程。
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _tokenize(self, text: str) -> list[str]:
        # 按非字母数字字符切分，保留 CJK 字符为单字
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        return tokens

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in self._tokenize(text):
            h = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if (h[4] & 1) == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def __call__(self, input):
        return [self._embed_one(t) for t in input]

    def embed_query(self, input):
        return self.__call__(input)

    @staticmethod
    def name() -> str:
        return "local_hash"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict):
        return _LocalHashEmbedding(dim=config.get("dim", 384))

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine", "l2", "ip"]


class ChromaVectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._embedding_function = _LocalHashEmbedding()

    def _ensure_client(self):
        if self._client is not None:
            return
        import chromadb
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="kb_chunks",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self._embedding_function,
        )

    def close(self):
        """Release the ChromaDB client and collection references.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        try:
            self._collection = None
            self._client = None
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def upsert(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        self._ensure_client()
        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [{
            "doc_id": c["doc_id"],
            "scope": c.get("scope", "private"),
            "tags": ",".join(c.get("tags", [])),
            "chunk_idx": c.get("chunk_idx", 0),
            "section": c.get("section", ""),
        } for c in chunks]
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, query_text: str, scope: str, top_k: int = 10) -> list[dict]:
        self._ensure_client()
        results = self._collection.query(
            query_texts=[query_text], n_results=top_k,
            where={"scope": scope},
        )
        if not results["ids"] or not results["ids"][0]:
            return []
        return [{
            "id": results["ids"][0][i],
            "doc_id": results["metadatas"][0][i].get("doc_id", ""),
            "text": results["documents"][0][i],
            "scope": results["metadatas"][0][i].get("scope", ""),
            "tags": results["metadatas"][0][i].get("tags", "").split(",") if results["metadatas"][0][i].get("tags") else [],
            "score": 1 - results["distances"][0][i] if "distances" in results else 0.0,
        } for i in range(len(results["ids"][0]))]

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._ensure_client()
        self._collection.delete(where={"doc_id": doc_id})
