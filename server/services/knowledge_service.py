# server/services/knowledge_service.py
"""知识库服务 — v2.2.0 Phase 4

封装向量检索 + RAG 上下文格式化,作为 ``stream_reply`` 与 KB 模块之间的桥梁。

设计要点:
1. 自动降级: 优先 LanceDB,未安装时降级到 ChromaVectorStore
2. 单例模式: 模块级 ``knowledge_service`` 单例,避免每次请求重建连接
3. 文档切片: 简单固定长度切片(可扩展为语义切片)
4. RAG 上下文: 格式化为 system prompt 注入文本,带 source 引用

不负责:
- 文档解析(由 ``server/kb/parser/*`` 处理)
- 知识图谱构建(由 ``server/kb/graph/kuzu_store`` 处理)
- 文档持久化(由 ``server/kb/storage/repo`` 处理)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..config_kb_cu import KBConfig
from ..kb.retrieval.vectorstore import ChromaVectorStore

logger = logging.getLogger(__name__)


def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """固定长度切片 + 重叠。

    简单实现:按字符数切片,CJK 字符按单字计算。
    生产环境可替换为语义切片(基于句子/段落边界)。
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def format_rag_context(results: list[dict]) -> str:
    """将检索结果格式化为 system prompt 注入文本。

    格式:
        知识库参考:
        [1] (doc_id:xxx, score:0.85)
        <文档片段文本>
        [2] (doc_id:yyy, score:0.72)
        <文档片段文本>
    """
    if not results:
        return ""
    lines = ["知识库参考:"]
    for i, r in enumerate(results, 1):
        doc_id = r.get("doc_id", "")
        score = r.get("score", 0.0)
        text = r.get("text", "").strip()
        if not text:
            continue
        # 截断过长片段,避免上下文膨胀
        preview = text[:800] + "..." if len(text) > 800 else text
        lines.append(f"[{i}] (doc_id:{doc_id}, score:{score:.3f})")
        lines.append(preview)
    return "\n".join(lines)


class KnowledgeService:
    """知识库服务 — 向量检索 + RAG 上下文格式化"""

    def __init__(self, config: KBConfig | None = None):
        self._config = config or KBConfig()
        self._config.ensure_dirs()
        self._store: Any | None = None
        self._store_type: str = ""  # "lance" | "chroma"

    def _get_store(self):
        """获取向量存储后端,优先 LanceDB,降级 ChromaVectorStore。

        缓存 store 实例,避免每次请求重建连接。
        """
        if self._store is not None:
            return self._store

        # 尝试 LanceDB
        try:
            from ..kb.retrieval.lance_store import LanceVectorStore

            self._store = LanceVectorStore(persist_dir=self._config.indexes_dir)
            # 触发惰性初始化检查 lancedb 是否真的可用
            self._store._ensure_db()
            self._store_type = "lance"
            logger.info("KnowledgeService using LanceVectorStore")
            return self._store
        except ImportError:
            logger.info("lancedb not installed, falling back to ChromaVectorStore")
        except Exception as exc:
            logger.warning(f"LanceVectorStore init failed: {exc}, falling back to ChromaVectorStore")

        # 降级到 ChromaVectorStore
        self._store = ChromaVectorStore(persist_dir=self._config.chroma_dir)
        self._store_type = "chroma"
        logger.info("KnowledgeService using ChromaVectorStore")
        return self._store

    @property
    def store_type(self) -> str:
        """当前使用的存储后端类型('lance' | 'chroma')。"""
        if self._store is None:
            self._get_store()
        return self._store_type

    async def ingest(
        self,
        doc_id: str,
        content: str,
        scope: str = "private",
        tags: list[str] | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> dict:
        """文档摄入: 切片 + 向量化 + upsert。

        Args:
            doc_id: 文档唯一 ID
            content: 文档纯文本内容
            scope: 可见范围(private/project/public)
            tags: 标签列表
            chunk_size: 切片大小
            chunk_overlap: 切片重叠

        Returns:
            {"doc_id": str, "chunks": int, "store_type": str}
        """
        if not content or not content.strip():
            return {"doc_id": doc_id, "chunks": 0, "store_type": self._store_type}

        store = self._get_store()
        chunks_text = _chunk_text(content, chunk_size, chunk_overlap)
        chunks = []
        for idx, text in enumerate(chunks_text):
            chunk_id = f"{doc_id}__chunk_{idx}"
            chunks.append({
                "id": chunk_id,
                "doc_id": doc_id,
                "text": text,
                "scope": scope,
                "tags": tags or [],
                "chunk_idx": idx,
                "section": "",
            })
        if chunks:
            # v2.2.1 S1: 用 asyncio.to_thread 包装同步 store 操作,避免阻塞事件循环
            await asyncio.to_thread(store.upsert, chunks)
        return {
            "doc_id": doc_id,
            "chunks": len(chunks),
            "store_type": self._store_type,
        }

    async def search(
        self,
        query: str,
        top_k: int = 5,
        scope: str = "private",
    ) -> list[dict]:
        """向量检索。

        Args:
            query: 查询文本
            top_k: 返回结果数
            scope: 可见范围过滤

        Returns:
            [{"id","doc_id","text","scope","tags","score"}, ...]
        """
        if not query or not query.strip():
            return []
        store = self._get_store()
        try:
            # v2.2.1 S1: 用 asyncio.to_thread 包装同步 store 操作,避免阻塞事件循环
            return await asyncio.to_thread(
                store.query, query, scope=scope, top_k=top_k
            )
        except Exception as exc:
            logger.warning(f"knowledge search failed: {exc}")
            return []

    async def delete_doc(self, doc_id: str) -> bool:
        """删除文档的所有向量记录。"""
        store = self._get_store()
        try:
            # v2.2.1 S1: 用 asyncio.to_thread 包装同步 store 操作,避免阻塞事件循环
            await asyncio.to_thread(store.delete_by_doc_id, doc_id)
            return True
        except Exception as exc:
            logger.warning(f"knowledge delete failed: {exc}")
            return False

    def get_status(self) -> dict:
        """返回知识库状态摘要。

        v2.2.1 S1 说明: 本方法保持同步签名(被 kb.py/rag.py 等多处同步调用,
        且测试用 MagicMock mock)。store.count() 通常为本地内存/索引元数据查询,
        耗时极短,不构成事件循环阻塞风险;若未来 store.count() 变重,应新增
        async get_status_async() 而非破坏现有 sync 签名。
        """
        store = self._get_store()
        count = 0
        try:
            count = store.count() if hasattr(store, "count") else 0
        except Exception:
            pass
        return {
            "store_type": self._store_type,
            "chunk_count": count,
            "persist_dir": str(self._config.indexes_dir),
        }

    def close(self):
        """释放存储连接。"""
        if self._store is not None:
            try:
                self._store.close()
            except Exception:
                pass
            self._store = None


# 模块级单例 — 供 stream_reply 直接使用
knowledge_service = KnowledgeService()
