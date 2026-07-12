"""Pangu Memory SDK — 海绵引擎策略

可插拔的海绵吸收策略:
- DefaultSpongeStrategy: 关键词提取 + 重要性评估
- AggressiveSpongeStrategy: 主动提取并压缩
- ConservativeSpongeStrategy: 仅存储,不主动压缩
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .types import Memory, MemoryLayer, MemoryMetadata

# 中文停用词 (简化版)
_STOP_WORDS = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "那",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "both",
        "either",
        "neither",
    }
)

_WORD_RE = re.compile(r"[\w]+|[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOP_WORDS and len(t) > 1]


def _extract_keywords(text: str, top_k: int = 5) -> list[str]:
    """简易关键词提取: 词频排序"""
    tokens = _tokenize(text)
    if not tokens:
        return []
    freq: dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in ranked[:top_k]]


def _estimate_importance(content: str, existing_count: int) -> float:
    """简易重要性评估: 基于内容长度与已有记忆数"""
    base = min(len(content) / 200.0, 0.5)
    novelty = max(0.2, 0.5 - existing_count * 0.02)
    return round(min(base + novelty, 1.0), 2)


class SpongeStrategy(ABC):
    """海绵吸收策略 — 可插拔"""

    @abstractmethod
    async def absorb(
        self,
        new_content: str,
        existing_memories: list[Memory],
    ) -> Memory:
        """吸收新内容,与已有记忆融合"""
        ...

    @staticmethod
    def _make_memory(
        content: str,
        layer: MemoryLayer,
        tags: list[str],
        importance: float,
        source: str = "sponge",
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
                source=source,
            ),
        )


class DefaultSpongeStrategy(SpongeStrategy):
    """默认策略: 关键词提取 + 重要性评估"""

    async def absorb(
        self,
        new_content: str,
        existing_memories: list[Memory],
    ) -> Memory:
        keywords = _extract_keywords(new_content, top_k=5)
        importance = _estimate_importance(new_content, len(existing_memories))
        return self._make_memory(
            content=new_content,
            layer=MemoryLayer.L1_EPISODIC,
            tags=keywords,
            importance=importance,
        )


class AggressiveSpongeStrategy(SpongeStrategy):
    """激进策略: 主动提取并压缩

    将新内容压缩为精炼摘要,提取更多关键词,并提升到 L2 叙事层
    """

    async def absorb(
        self,
        new_content: str,
        existing_memories: list[Memory],
    ) -> Memory:
        keywords = _extract_keywords(new_content, top_k=8)
        # 激进策略: 用关键词重构内容为摘要形式
        summary = new_content.strip()
        if len(summary) > 120:
            summary = summary[:117] + "..."
        importance = min(_estimate_importance(new_content, len(existing_memories)) + 0.2, 1.0)
        return self._make_memory(
            content=summary,
            layer=MemoryLayer.L2_NARRATIVE,
            tags=keywords,
            importance=importance,
            source="sponge_aggressive",
        )


class ConservativeSpongeStrategy(SpongeStrategy):
    """保守策略: 仅存储,不主动压缩

    原样存储内容,不提取关键词,保持 L0 工作层
    """

    async def absorb(
        self,
        new_content: str,
        existing_memories: list[Memory],
    ) -> Memory:
        return self._make_memory(
            content=new_content,
            layer=MemoryLayer.L0_WORKING,
            tags=[],
            importance=0.3,
            source="sponge_conservative",
        )
