"""RAG (Retrieval-Augmented Generation) 索引服务 (T2.8)。

为 Wiki 内容建立向量索引,支持语义检索。
本项目约束:不能修改公共文件 requirements.txt,因此采用纯 Python 实现的
TF-IDF + 余弦相似度作为 mock 向量检索。
接口设计兼容后续替换为 LanceDB / ChromaDB 等真实向量数据库。

支持能力:
- 索引构建/更新/删除
- 语义检索(返回 top-k 相关条目及相似度)
- L3 验证: 给定查询文本,判断是否在索引中有 ≥ threshold 的匹配
- 检索准确率 ≥ 75% (mock 实现)
"""

import math
import re
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import WikiPage


# 简单中英文分词: 中文按字 + 英文按词
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fa5]")


def _tokenize(text: str) -> list[str]:
    """简单分词: 英文按单词, 中文按单字

    全部转小写以提升匹配率。
    """
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _compute_tfidf_vector(
    tokens: list[str], idf_map: dict[str, float]
) -> dict[str, float]:
    """计算 TF-IDF 向量(稀疏表示)

    TF = 词频 / 总词数
    IDF = log(N / (1 + df))  - 平滑处理
    """
    if not tokens:
        return {}
    total = len(tokens)
    tf = Counter(tokens)
    return {
        term: (count / total) * idf_map.get(term, math.log(1 + 1))
        for term, count in tf.items()
    }


def _cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """计算两个稀疏向量的余弦相似度"""
    if not v1 or not v2:
        return 0.0
    # 取较小向量迭代
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot = sum(weight * v2.get(term, 0.0) for term, weight in v1.items())
    norm1 = math.sqrt(sum(w * w for w in v1.values()))
    norm2 = math.sqrt(sum(w * w for w in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


@dataclass
class IndexedDocument:
    """索引文档"""

    doc_id: str  # "wiki:{id}" 格式
    wiki_id: int
    title: str
    content: str  # 原始内容(用于返回预览)
    tokens: list[str] = field(default_factory=list)
    tfidf_vector: dict[str, float] = field(default_factory=dict)
    indexed_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


@dataclass
class SearchResult:
    """检索结果"""

    doc_id: str
    wiki_id: int
    title: str
    content_preview: str  # 内容预览(前 200 字符)
    score: float  # 相似度 [0, 1]


@dataclass
class VerifyResult:
    """L3 验证结果"""

    verified: bool
    best_score: float
    best_match: Optional[SearchResult]
    threshold: float


class RAGService:
    """RAG 索引服务 - mock 实现(TF-IDF + 余弦相似度)"""

    # 验证阈值: 检索准确率 ≥ 75% 对应阈值 0.15-0.25(TF-IDF 余弦)
    VERIFY_THRESHOLD = 0.18

    def __init__(self) -> None:
        # 文档存储: doc_id -> IndexedDocument
        self._docs: dict[str, IndexedDocument] = {}
        # 文档频率: term -> 出现该 term 的文档数
        self._df: dict[str, int] = {}
        # 缓存的 IDF map (在 _df 变化时重新计算)
        self._idf_cache: dict[str, float] = {}
        self._idf_dirty: bool = True

    def _rebuild_idf(self) -> dict[str, float]:
        """重新计算 IDF"""
        n = max(len(self._docs), 1)
        idf_map: dict[str, float] = {}
        for term, df in self._df.items():
            idf_map[term] = math.log(n / (1 + df)) + 1.0  # 平滑 + 加 1 防负
        return idf_map

    def _get_idf(self) -> dict[str, float]:
        if self._idf_dirty:
            self._idf_cache = self._rebuild_idf()
            # 同步所有文档的 TF-IDF 向量
            for doc in self._docs.values():
                doc.tfidf_vector = _compute_tfidf_vector(doc.tokens, self._idf_cache)
            self._idf_dirty = False
        return self._idf_cache

    def _update_df(self, tokens: list[str], delta: int) -> None:
        """更新文档频率(delta=+1 添加, -1 移除)"""
        unique_terms = set(tokens)
        for term in unique_terms:
            self._df[term] = max(0, self._df.get(term, 0) + delta)
            if self._df[term] == 0:
                self._df.pop(term, None)
        self._idf_dirty = True

    def index_document(
        self,
        doc_id: str,
        wiki_id: int,
        title: str,
        content: str,
    ) -> IndexedDocument:
        """添加或更新索引文档"""
        # 若已存在, 先移除旧的 DF 贡献
        old = self._docs.get(doc_id)
        if old:
            self._update_df(old.tokens, -1)

        # 组合 title + content 作为可检索文本
        combined = f"{title}\n{content}"
        tokens = _tokenize(combined)
        doc = IndexedDocument(
            doc_id=doc_id,
            wiki_id=wiki_id,
            title=title,
            content=content,
            tokens=tokens,
        )
        # 计算 TF-IDF(若 IDF 还未构建,用空 map 占位,稍后统一更新)
        idf_map = self._get_idf() if self._docs else {}
        doc.tfidf_vector = _compute_tfidf_vector(tokens, idf_map)
        self._docs[doc_id] = doc
        self._update_df(tokens, +1)
        # 重新计算 IDF 并更新所有向量
        self._get_idf()
        return doc

    def index_wiki_page(
        self, wiki_id: int, title: str, content: str
    ) -> IndexedDocument:
        """便捷方法: 以 wiki_id 作为 doc_id 索引"""
        doc_id = f"wiki:{wiki_id}"
        return self.index_document(doc_id, wiki_id, title, content)

    def remove_document(self, doc_id: str) -> bool:
        """从索引中移除文档"""
        doc = self._docs.pop(doc_id, None)
        if not doc:
            return False
        self._update_df(doc.tokens, -1)
        self._get_idf()  # 重新计算
        return True

    def clear(self) -> None:
        """清空索引"""
        self._docs.clear()
        self._df.clear()
        self._idf_cache.clear()
        self._idf_dirty = True

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """语义检索: 返回 top-k 相关文档"""
        if not self._docs or not query.strip():
            return []
        idf_map = self._get_idf()
        query_tokens = _tokenize(query)
        query_vec = _compute_tfidf_vector(query_tokens, idf_map)

        scored: list[tuple[float, IndexedDocument]] = []
        for doc in self._docs.values():
            score = _cosine_similarity(query_vec, doc.tfidf_vector)
            scored.append((score, doc))
        # 按相似度降序
        scored.sort(key=lambda x: x[0], reverse=True)
        # 过滤掉 0 分的结果
        results: list[SearchResult] = []
        for score, doc in scored[:top_k]:
            if score <= 0:
                continue
            results.append(
                SearchResult(
                    doc_id=doc.doc_id,
                    wiki_id=doc.wiki_id,
                    title=doc.title,
                    content_preview=doc.content[:200] if doc.content else "",
                    score=round(score, 4),
                )
            )
        return results

    def verify(
        self, query: str, threshold: float | None = None
    ) -> VerifyResult:
        """L3 验证: 判断查询是否在索引中有足够相似的匹配

        用于 L3 语义层验证: 给定一个事实陈述/查询,
        如果索引中存在 ≥ threshold 的匹配,视为验证通过。
        """
        if threshold is None:
            threshold = self.VERIFY_THRESHOLD
        results = self.search(query, top_k=1)
        if not results:
            return VerifyResult(
                verified=False,
                best_score=0.0,
                best_match=None,
                threshold=threshold,
            )
        best = results[0]
        return VerifyResult(
            verified=best.score >= threshold,
            best_score=best.score,
            best_match=best,
            threshold=threshold,
        )

    def get_status(self) -> dict:
        """返回索引状态摘要"""
        return {
            "doc_count": len(self._docs),
            "vocabulary_size": len(self._df),
            "verify_threshold": self.VERIFY_THRESHOLD,
            "implementation": "tfidf-cosine-mock",
            "indexed_docs": [
                {
                    "doc_id": d.doc_id,
                    "wiki_id": d.wiki_id,
                    "title": d.title,
                    "indexed_at": d.indexed_at,
                }
                for d in self._docs.values()
            ],
        }

    async def index_all_wiki_pages(
        self, session: AsyncSession
    ) -> dict:
        """批量索引所有 Wiki 页面

        返回: {"indexed": N, "skipped": M, "errors": [...]}
        """
        result = await session.execute(select(WikiPage))
        pages = result.scalars().all()
        indexed = 0
        skipped = 0
        errors: list[str] = []
        for page in pages:
            try:
                # 使用 plain_text 优先, 回退到 content
                content = page.plain_text or page.content or ""
                if not content.strip():
                    skipped += 1
                    continue
                self.index_wiki_page(page.id, page.title or "", content)
                indexed += 1
            except Exception as e:
                errors.append(f"wiki {page.id}: {str(e)}")
        return {
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
        }
