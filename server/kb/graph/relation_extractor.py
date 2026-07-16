# server/kb/graph/relation_extractor.py
"""文档关系抽取与推荐"""
from __future__ import annotations
from dataclasses import dataclass

from server.kb.storage.frontmatter import FrontMatter


@dataclass
class RelationRecommendation:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    reason: str


class RelationExtractor:
    def recommend_relations(
        self, source: FrontMatter, candidates: list[FrontMatter]
    ) -> list[RelationRecommendation]:
        """基于共享 tags/categories 推荐文档间关系。

        相似度采用 Jaccard 系数（对 tags 与 categories 的并集计算），
        按阈值映射到 KuzuGraphStore 支持的关系类型：
          >=0.85 -> References
          >=0.7  -> Extends
          >=0.5  -> DerivedFrom
          <0.5   -> 跳过（避免低质量边）
        """
        recommendations: list[RelationRecommendation] = []
        source_tags = set(source.tags or [])
        source_categories = set(source.categories or [])
        source_features = source_tags | source_categories
        if not source_features:
            return recommendations

        for candidate in candidates:
            if candidate.id == source.id:
                continue

            cand_tags = set(candidate.tags or [])
            cand_categories = set(candidate.categories or [])
            cand_features = cand_tags | cand_categories
            if not cand_features:
                continue

            shared = source_features & cand_features
            total_shared = len(shared)
            if total_shared == 0:
                continue

            union_size = len(source_features | cand_features)
            score = min(1.0, total_shared / max(1, union_size))

            if score >= 0.85:
                rel_type, reason = "References", "标签/分类高度重合，可能存在引用关系"
            elif score >= 0.7:
                rel_type, reason = "Extends", "标签/分类相关，可能是扩展或延伸"
            elif score >= 0.5:
                rel_type, reason = "DerivedFrom", "标签/分类存在重叠，可能同源"
            else:
                continue  # 跳过低相似度关系

            recommendations.append(RelationRecommendation(
                source_id=source.id,
                target_id=candidate.id,
                relation_type=rel_type,
                confidence=score,
                reason=reason,
            ))

        return recommendations
