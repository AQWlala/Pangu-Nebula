# server/kb/retrieval/hybrid.py
"""混合检索（向量 + 关键词 + RRF 融合）"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from server.kb.storage.repo import DocumentRepo
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.retrieval.scope import ScopeFilter


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
