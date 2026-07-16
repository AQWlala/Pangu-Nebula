# server/kb/graph/relation_extractor.py
"""文档关系抽取与推荐"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RelationRecommendation:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    reason: str


class RelationExtractor:
    def recommend_relations(self, doc_id: str, similar_docs: list[dict]) -> list[RelationRecommendation]:
        recommendations = []
        for doc in similar_docs:
            score = doc.get("score", 0.0)
            if score < 0.5:
                continue
            if score >= 0.85:
                rel_type, reason = "references", "向量相似度极高，可能存在引用关系"
            elif score >= 0.7:
                rel_type, reason = "extends", "内容相关，可能是扩展或延伸"
            else:
                rel_type, reason = "derived_from", "存在一定相似度，可能同源"
            recommendations.append(RelationRecommendation(
                source_id=doc_id, target_id=doc["doc_id"],
                relation_type=rel_type, confidence=score, reason=reason,
            ))
        return recommendations
