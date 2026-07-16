# server/kb/retrieval/lance_store.py
"""LanceDB 向量存储适配器 — v2.2.0 Phase 4

接口与 ``ChromaVectorStore`` 完全一致(upsert/query/delete_by_doc_id/close),
可作为 ChromaDB 的替代实现。优势:
- 嵌入式存储,单进程零配置
- 列式存储(Arrow),查询性能优于 ChromaDB
- PyInstaller 打包友好(无重型 ML 依赖)

降级策略:
- 无 ``lancedb`` 包时,导入失败由 ``KnowledgeService`` 捕获并降级到 ChromaVectorStore
- 嵌入函数复用 ``ChromaVectorStore._LocalHashEmbedding``,保证两端向量空间一致,
  可无缝切换存储后端
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

# 复用 ChromaVectorStore 的本地哈希嵌入,保证两个存储后端向量空间一致
from .vectorstore import _LocalHashEmbedding


class LanceVectorStore:
    """LanceDB 向量存储封装 — 接口与 ChromaVectorStore 一致"""

    def __init__(self, persist_dir: Path, dim: int = 384):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._dim = dim
        self._db = None
        self._table = None
        self._embedding_function = _LocalHashEmbedding(dim=dim)

    def _ensure_db(self):
        """惰性初始化 LanceDB 连接。

        在首次 upsert/query 时才 import lancedb,避免模块加载期就因缺包失败。
        """
        if self._db is not None:
            return
        import lancedb  # type: ignore

        self._db = lancedb.connect(str(self.persist_dir / "knowledge.lance"))
        # LanceDB 表结构: id/text/doc_id/scope/tags/chunk_idx/section/vector
        # create_table 如果表已存在则打开,否则新建
        try:
            self._table = self._db.open_table("kb_chunks")
        except Exception:
            # 表不存在,创建空表(首次 upsert 时会推断 schema)
            self._table = None

    def _ensure_table_with_data(self, chunks: list[dict] | None = None):
        """确保表存在。首次 upsert 时根据数据推断 schema 创建表。"""
        self._ensure_db()
        if self._table is not None:
            return
        if not chunks:
            return
        import pyarrow as pa  # type: ignore

        # 计算向量
        texts = [c["text"] for c in chunks]
        vectors = self._embedding_function(texts)
        rows = []
        for c, vec in zip(chunks, vectors):
            rows.append({
                "id": c["id"],
                "text": c["text"],
                "doc_id": c["doc_id"],
                "scope": c.get("scope", "private"),
                "tags": ",".join(c.get("tags", [])),
                "chunk_idx": c.get("chunk_idx", 0),
                "section": c.get("section", ""),
                "vector": vec.tolist(),
            })
        table_data = pa.Table.from_pylist(rows)
        self._table = self._db.create_table("kb_chunks", data=table_data)

    def close(self):
        """释放 LanceDB 连接引用。多次调用安全。"""
        try:
            self._table = None
            self._db = None
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def upsert(self, chunks: list[dict]) -> None:
        """upsert 文档块。

        LanceDB 不支持单条 upsert,采用 delete-then-add 策略:
        按 doc_id 删除旧记录,再添加新记录。
        """
        if not chunks:
            return
        self._ensure_table_with_data(chunks)

        # 收集所有 doc_id,先删除旧记录
        doc_ids = list({c["doc_id"] for c in chunks})
        for doc_id in doc_ids:
            try:
                # LanceDB delete 接受 SQL 过滤字符串
                self._table.delete(f'doc_id = \'{doc_id}\'')
            except Exception:
                pass

        # 添加新记录
        import pyarrow as pa  # type: ignore

        texts = [c["text"] for c in chunks]
        vectors = self._embedding_function(texts)
        rows = []
        for c, vec in zip(chunks, vectors):
            rows.append({
                "id": c["id"],
                "text": c["text"],
                "doc_id": c["doc_id"],
                "scope": c.get("scope", "private"),
                "tags": ",".join(c.get("tags", [])),
                "chunk_idx": c.get("chunk_idx", 0),
                "section": c.get("section", ""),
                "vector": vec.tolist(),
            })
        table_data = pa.Table.from_pylist(rows)
        self._table.add(table_data)

    def query(self, query_text: str, scope: str, top_k: int = 10) -> list[dict]:
        """向量检索 + scope 过滤。返回格式与 ChromaVectorStore.query 一致。"""
        self._ensure_db()
        if self._table is None:
            return []

        query_vec = self._embedding_function([query_text])[0]
        # LanceDB search 链式调用: vector → filter → limit → to_list
        try:
            results = (
                self._table.search(query_vec.tolist())
                .where(f"scope = '{scope}'")
                .limit(top_k)
                .to_list()
            )
        except Exception:
            return []

        return [{
            "id": r.get("id", ""),
            "doc_id": r.get("doc_id", ""),
            "text": r.get("text", ""),
            "scope": r.get("scope", ""),
            "tags": r.get("tags", "").split(",") if r.get("tags") else [],
            "score": float(r.get("_distance", 0.0)),  # LanceDB 返回 _distance(越小越相似)
        } for r in results]

    def delete_by_doc_id(self, doc_id: str) -> None:
        """按 doc_id 删除所有相关记录。"""
        self._ensure_db()
        if self._table is None:
            return
        try:
            self._table.delete(f"doc_id = '{doc_id}'")
        except Exception:
            pass

    def count(self) -> int:
        """返回表中记录数。用于状态展示。"""
        self._ensure_db()
        if self._table is None:
            return 0
        try:
            return self._table.count_rows()
        except Exception:
            return 0
