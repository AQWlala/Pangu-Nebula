"""Pangu Memory SDK — 黑洞引擎压缩策略

可插拔的压缩策略:
- SummaryCompression: 摘要压缩 (拼接 + 截断)
- KeywordCompression: 关键词压缩 (提取关键词集合)
- SemanticCompression: 语义压缩 (按 tag 分组 + 重要性加权)
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .types import Memory, MemoryLayer, MemoryMetadata
from .sponge import _extract_keywords


class CompressionStrategy(ABC):
    """黑洞压缩策略 — 可插拔"""

    @abstractmethod
    async def compress(self, memories: list[Memory]) -> Memory:
        """压缩多个记忆为一个摘要记忆"""
        ...

    @staticmethod
    def _make_compressed(
        content: str,
        layer: MemoryLayer,
        tags: list[str],
        importance: float,
        source_ids: list[str],
    ) -> Memory:
        now = datetime.utcnow()
        return Memory(
            id=str(uuid4()),
            content=content,
            metadata=MemoryMetadata(
                layer=layer,
                tags=tags,
                importance=importance,
                created_at=now,
                updated_at=now,
                source="blackhole",
                backlinks=list(source_ids),
                metadata={"compressed_from": source_ids, "compressed_at": now.isoformat()},
            ),
        )

    @staticmethod
    def _target_layer(source_layer: MemoryLayer) -> MemoryLayer:
        """压缩目标层 = 源层 + 1 (L5 保持 L5)"""
        order = [
            MemoryLayer.L0_WORKING,
            MemoryLayer.L1_EPISODIC,
            MemoryLayer.L2_NARRATIVE,
            MemoryLayer.L3_SEMANTIC,
            MemoryLayer.L4_PROCEDURAL,
            MemoryLayer.L5_METACOGNITION,
        ]
        try:
            idx = order.index(source_layer)
        except ValueError:
            return MemoryLayer.L3_SEMANTIC
        return order[min(idx + 1, len(order) - 1)]


class SummaryCompression(CompressionStrategy):
    """摘要压缩策略

    将多条记忆的内容拼接成摘要,保留关键信息,目标层 = 源层 + 1
    """

    MAX_SUMMARY_LEN = 500

    async def compress(self, memories: list[Memory]) -> Memory:
        if not memories:
            raise ValueError("不能压缩空记忆列表")
        source_layer = memories[0].metadata.layer
        target_layer = self._target_layer(source_layer)

        parts: list[str] = []
        for m in memories:
            parts.append(f"- {m.content}")
        summary = "\n".join(parts)
        if len(summary) > self.MAX_SUMMARY_LEN:
            summary = summary[: self.MAX_SUMMARY_LEN - 3] + "..."

        all_tags: list[str] = []
        for m in memories:
            for t in m.metadata.tags:
                if t not in all_tags:
                    all_tags.append(t)

        avg_importance = (
            sum(m.metadata.importance for m in memories) / len(memories)
            if memories
            else 0.5
        )
        importance = min(avg_importance + 0.1, 1.0)
        source_ids = [m.id for m in memories if m.id]

        return self._make_compressed(
            content=summary,
            layer=target_layer,
            tags=all_tags[:10],
            importance=importance,
            source_ids=source_ids,
        )


class KeywordCompression(CompressionStrategy):
    """关键词压缩策略

    从多条记忆中提取关键词集合,生成关键词索引记忆
    """

    async def compress(self, memories: list[Memory]) -> Memory:
        if not memories:
            raise ValueError("不能压缩空记忆列表")
        source_layer = memories[0].metadata.layer
        target_layer = self._target_layer(source_layer)

        combined_text = " ".join(m.content for m in memories)
        keywords = _extract_keywords(combined_text, top_k=15)

        existing_tags: list[str] = []
        for m in memories:
            for t in m.metadata.tags:
                if t not in existing_tags:
                    existing_tags.append(t)

        merged_tags = list({*keywords, *existing_tags})
        content = f"[Keyword Index] {', '.join(merged_tags[:20])}"
        importance = max(
            (m.metadata.importance for m in memories),
            default=0.5,
        )
        source_ids = [m.id for m in memories if m.id]

        return self._make_compressed(
            content=content,
            layer=target_layer,
            tags=merged_tags[:20],
            importance=importance,
            source_ids=source_ids,
        )


class SemanticCompression(CompressionStrategy):
    """语义压缩策略

    按 tag 分组,对每组生成加权重要性摘要,合并为高层语义记忆
    """

    async def compress(self, memories: list[Memory]) -> Memory:
        if not memories:
            raise ValueError("不能压缩空记忆列表")
        source_layer = memories[0].metadata.layer
        target_layer = self._target_layer(source_layer)

        # 按 tag 分组 (无 tag 归入 "general")
        groups: dict[str, list[Memory]] = {}
        for m in memories:
            tags = m.metadata.tags or ["general"]
            key = tags[0] if tags else "general"
            groups.setdefault(key, []).append(m)

        sections: list[str] = []
        all_tags: list[str] = []
        total_weighted_importance = 0.0
        total_weight = 0

        for group_key, group_memories in groups.items():
            all_tags.append(group_key)
            weighted = sum(m.metadata.importance for m in group_memories)
            total_weighted_importance += weighted
            total_weight += len(group_memories)
            # 每组取重要性最高的记忆内容为代表
            top_mem = max(group_memories, key=lambda x: x.metadata.importance)
            sections.append(f"[{group_key}] {top_mem.content}")

        content = "\n".join(sections)
        if len(content) > 600:
            content = content[:597] + "..."

        importance = (
            total_weighted_importance / total_weight if total_weight > 0 else 0.5
        )
        importance = min(importance + 0.15, 1.0)
        source_ids = [m.id for m in memories if m.id]

        return self._make_compressed(
            content=content,
            layer=target_layer,
            tags=all_tags[:15],
            importance=importance,
            source_ids=source_ids,
        )
