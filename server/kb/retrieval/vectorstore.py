# server/kb/retrieval/vectorstore.py
"""ChromaDB 嵌入式向量存储"""
from __future__ import annotations
import hashlib
import json
import re
from functools import lru_cache
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

    @staticmethod
    @lru_cache(maxsize=1024)
    def _embed_cached(text: str, dim: int) -> tuple[float, ...]:
        """v2.2.1 P2: LRU 缓存 embedding — 相同文本不重复计算 MD5/向量

        返回 tuple 而非 np.ndarray/list 因为 tuple 不可变,避免调用方误修改
        缓存内容。lru_cache 要求参数可哈希 (str/int 可哈希)。
        tokenization 逻辑与 _tokenize 一致,内联以避免静态方法访问 self。
        """
        vec = np.zeros(dim, dtype=np.float32)
        for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower()):
            h = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if (h[4] & 1) == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return tuple(vec.tolist())

    def _embed_one(self, text: str) -> np.ndarray:
        # v2.2.1 P2: 走 LRU 缓存,相同文本不重复计算 MD5/向量
        return np.array(_LocalHashEmbedding._embed_cached(text, self.dim), dtype=np.float32)

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


# ---- v2.2.1 P2-6: tags JSON 序列化辅助函数 ----
# 旧格式: 逗号分隔字符串 "a,b,c" — 含逗号的 tag 会被错误切分
# 新格式: JSON 数组 '["a,b","c"]' — 完整保留每个 tag
# 读侧 _deserialize_tags 自动兼容两种格式,保证平滑升级

def _serialize_tags(tags) -> str:
    """将 tags 列表序列化为 JSON 字符串写入存储

    None / 空列表统一序列化为 "[]",保证列内非空,便于 where 过滤。
    """
    if not tags:
        return "[]"
    if not isinstance(tags, (list, tuple)):
        # 防御性: 上游误传字符串时不要抛异常, 转成单元素列表
        tags = [tags]
    return json.dumps(list(tags), ensure_ascii=False)


def _deserialize_tags(raw) -> list:
    """从存储读出 tags 字符串,反序列化为列表

    向后兼容:
    - 新格式 JSON 数组 -> json.loads
    - 旧格式逗号分隔 -> split(",")
    - None/空 -> []
    解析失败时降级为 split(","),避免单条坏数据阻塞整个查询。
    """
    if not raw:
        return []
    if not isinstance(raw, str):
        # Chroma metadata 可能返回非字符串类型,直接转 list
        if isinstance(raw, (list, tuple)):
            return list(raw)
        return []
    s = raw.strip()
    if not s:
        return []
    # 优先尝试 JSON(新格式)
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass  # 降级到旧格式
    # 旧格式兼容: 逗号分隔
    return [t for t in s.split(",") if t]


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
            "tags": _serialize_tags(c.get("tags", [])),
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
            "tags": _deserialize_tags(results["metadatas"][0][i].get("tags")),
            "score": 1 - results["distances"][0][i] if "distances" in results else 0.0,
        } for i in range(len(results["ids"][0]))]

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._ensure_client()
        self._collection.delete(where={"doc_id": doc_id})
