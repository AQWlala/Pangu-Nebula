# server/kb/retrieval/hybrid.py
"""混合检索（向量 + 关键词 + RRF 融合）"""
from __future__ import annotations
import sqlite3
import logging
from dataclasses import dataclass, field
from collections import defaultdict
from server.kb.storage.repo import DocumentRepo
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.retrieval.scope import ScopeFilter

logger = logging.getLogger(__name__)

FTS5_SCHEMA = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS kb_documents_fts USING fts5("
    "doc_id UNINDEXED, title, content, scope UNINDEXED, "
    "tokenize = 'unicode61')"
)


def ensure_fts_table(conn: sqlite3.Connection) -> None:
    """确保 FTS5 虚拟表存在（幂等）。"""
    conn.execute(FTS5_SCHEMA)
    conn.commit()


@dataclass
class SearchResult:
    doc_id: str
    chunk_text: str
    score: float
    source_method: str
    scope: str
    title: str = ""
    tags: list[str] = field(default_factory=list)


class HybridSearcher:
    VECTOR_WEIGHT = 0.5
    KEYWORD_WEIGHT = 0.3
    GRAPH_WEIGHT = 0.2
    RRF_K = 60

    def __init__(self, repo: DocumentRepo, vector_store: ChromaVectorStore):
        self.repo = repo
        self.vector_store = vector_store

    def _fts_db_path(self):
        """从 repo.documents_dir 派生 FTS5 所在的 meta.db 路径。"""
        return self.repo.documents_dir.parent / "meta.db"

    def search(self, query: str, scope: str, top_k: int = 5,
               methods: list[str] | None = None) -> list[SearchResult]:
        if methods is None:
            methods = ["vector", "keyword"]

        all_results: list[SearchResult] = []
        if "vector" in methods:
            all_results.extend(self._vector_search(query, scope, top_k * 4))
        if "keyword" in methods:
            all_results.extend(self._keyword_search(query, scope, top_k * 4))

        fused = self._rrf_fuse(all_results, top_k)
        return ScopeFilter.filter(fused, scope)

    def _vector_search(self, query: str, scope: str, top_k: int) -> list[SearchResult]:
        raw = self.vector_store.query(query, scope=scope, top_k=top_k)
        return [SearchResult(
            doc_id=r["doc_id"], chunk_text=r["text"], score=r["score"],
            source_method="vector", scope=r["scope"], tags=r.get("tags", []),
        ) for r in raw]

    def _keyword_search(self, query: str, scope: str, top_k: int) -> list[SearchResult]:
        # 空查询直接返回空列表
        if not query or not query.strip():
            return []

        # 优先使用 FTS5 全文检索
        try:
            fts_results = self._fts_search(query, scope, top_k)
            if fts_results is not None:
                return fts_results
        except Exception as e:
            logger.warning(f"FTS5 search failed, falling back to brute-force: {e}")

        # 降级：暴力扫描
        return self._brute_force_search(query, scope, top_k)

    def _build_fts_query(self, query: str) -> str:
        """将用户查询转为安全的 FTS5 MATCH 表达式。

        对每个空白分隔的词项加双引号，避免 FTS5 特殊语法（* : ( ) 等）报错，
        词项间用 OR 连接以扩大召回。
        """
        terms = [t for t in query.split() if t]
        if not terms:
            return ""
        quoted = []
        for t in terms:
            escaped = t.replace('"', '""')
            quoted.append(f'"{escaped}"')
        return " OR ".join(quoted)

    def _fts_search(self, query: str, scope: str, top_k: int):
        """FTS5 全文检索。返回 None 表示需降级到暴力扫描。"""
        db_path = self._fts_db_path()
        if not db_path.exists():
            return None  # meta.db 不存在，降级

        with sqlite3.connect(str(db_path)) as conn:
            ensure_fts_table(conn)
            # 若 FTS5 表为空，降级到暴力扫描
            count = conn.execute(
                "SELECT COUNT(*) FROM kb_documents_fts"
            ).fetchone()[0]
            if count == 0:
                return None

            fts_query = self._build_fts_query(query)
            if not fts_query:
                return []

            # MATCH 全文匹配 + scope 过滤，BM25 rank 排序
            rows = conn.execute(
                "SELECT doc_id, title, content, scope, rank "
                "FROM kb_documents_fts "
                "WHERE kb_documents_fts MATCH ? AND scope = ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, scope, top_k),
            ).fetchall()

        results = []
        # FTS5 rank 为负值（越小越相关），取 -rank 得到正值（越大越相关）
        # 归一化到 (0, 1]：最佳匹配 = 1.0
        max_raw = max((-r for _, _, _, _, r in rows), default=0.0)
        if max_raw <= 0:
            max_raw = 1.0
        for doc_id, title, content, doc_scope, rank in rows:
            score = (-rank) / max_raw
            chunk = self._extract_chunk(content, query)
            results.append(SearchResult(
                doc_id=doc_id, chunk_text=chunk, score=score,
                source_method="keyword", scope=doc_scope, title=title,
            ))
        return results

    @staticmethod
    def _extract_chunk(content: str, query: str, window: int = 200) -> str:
        """提取查询命中位置附近的文本片段。"""
        if not content:
            return ""
        idx = content.lower().find(query.lower())
        if idx < 0:
            for term in query.split():
                idx = content.lower().find(term.lower())
                if idx >= 0:
                    break
        if idx < 0:
            return content[:window]
        start = max(0, idx - 50)
        end = min(len(content), idx + len(query) + 100)
        return content[start:end]

    def _brute_force_search(self, query: str, scope: str, top_k: int) -> list[SearchResult]:
        """暴力线性扫描（FTS5 不可用时的降级方案）。"""
        results = []
        query_lower = query.lower()
        for doc_id in self.repo.list_all():
            fm, body = self.repo.read(doc_id)
            if fm.scope != scope:
                continue
            body_lower = body.lower()
            title_lower = fm.title.lower()
            score = 0.0
            if query_lower in title_lower:
                score += 0.5
            if query_lower in body_lower:
                score += 0.3
            for word in query_lower.split():
                score += body_lower.count(word) * 0.05
            if score > 0:
                idx = body_lower.find(query_lower)
                chunk = body[max(0, idx-50):min(len(body), idx+len(query)+100)] if idx >= 0 else body[:200]
                results.append(SearchResult(
                    doc_id=doc_id, chunk_text=chunk, score=min(score, 1.0),
                    source_method="keyword", scope=fm.scope, title=fm.title, tags=fm.tags,
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _rrf_fuse(self, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        doc_scores: dict[str, float] = defaultdict(float)
        doc_info: dict[str, SearchResult] = {}
        by_method: dict[str, list[SearchResult]] = defaultdict(list)
        for r in results:
            by_method[r.source_method].append(r)

        weights = {"vector": self.VECTOR_WEIGHT, "keyword": self.KEYWORD_WEIGHT, "graph": self.GRAPH_WEIGHT}
        for method, method_results in by_method.items():
            method_results.sort(key=lambda r: r.score, reverse=True)
            weight = weights.get(method, 0.1)
            for rank, r in enumerate(method_results):
                doc_scores[r.doc_id] += weight / (self.RRF_K + rank + 1)
                if r.doc_id not in doc_info:
                    doc_info[r.doc_id] = r

        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        return [SearchResult(
            doc_id=doc_id, chunk_text=doc_info[doc_id].chunk_text,
            score=score, source_method=doc_info[doc_id].source_method,
            scope=doc_info[doc_id].scope, title=doc_info[doc_id].title,
            tags=doc_info[doc_id].tags,
        ) for doc_id, score in sorted_docs[:top_k]]
