from dataclasses import dataclass, field
import asyncio
import json
import logging

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import Memory
from ..providers.base import Message
from ..providers.registry import get_provider

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    success: bool
    source_layer: str
    target_layer: str
    source_count: int
    new_memory: dict | None
    compressed_ids: list[int] = field(default_factory=list)
    error: str = ""


class BlackHoleEngine:
    """黑洞引擎：低层记忆压缩汇总"""

    LAYER_HIERARCHY = ["L0", "L1", "L2", "L3", "L4", "L5"]

    COMPACTION_THRESHOLDS = {
        "L0": 20,
        "L1": 15,
        "L2": 10,
        "L3": 8,
        "L4": 5,
    }

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-4o-mini"):
        self.model_provider = model_provider
        self.model_name = model_name

    def _next_layer(self, layer: str) -> str | None:
        idx = self.LAYER_HIERARCHY.index(layer)
        if idx + 1 < len(self.LAYER_HIERARCHY):
            return self.LAYER_HIERARCHY[idx + 1]
        return None

    async def check_and_compact(self, persona_id: int) -> list[CompressionResult]:
        results: list[CompressionResult] = []
        # v2.2.1 P2-4: 合并 5 次 layer 查询为 1 次单查询,消除 N+1
        # 原逻辑按 layer 逐个开 session 查询并统计未压缩记忆数。
        # 改为一次查询拉取 (layer, tags) 投影,在 Python 内按 layer 分组计数,
        # 既保留 "compressed not in tags" 的过滤语义(跨 DB 兼容),又将 5 次
        # 数据库往返压缩为 1 次。
        async with async_session() as session:
            stmt = select(Memory.layer, Memory.tags).where(
                Memory.persona_id == persona_id,
                Memory.layer.in_(["L0", "L1", "L2", "L3", "L4"]),
            )
            rows = (await session.execute(stmt)).all()
            layer_counts: dict[str, int] = {l: 0 for l in ["L0", "L1", "L2", "L3", "L4"]}
            for layer, tags in rows:
                if "compressed" not in (tags or []):
                    layer_counts[layer] = layer_counts.get(layer, 0) + 1
        for layer in ["L0", "L1", "L2", "L3", "L4"]:
            threshold = self.COMPACTION_THRESHOLDS[layer]
            count = layer_counts.get(layer, 0)
            if count > threshold:
                result = await self.compact_layer(persona_id, layer)
                results.append(result)
        return results

    async def compact_layer(
        self,
        persona_id: int,
        source_layer: str,
        target_layer: str | None = None,
    ) -> CompressionResult:
        if target_layer is None:
            target_layer = self._next_layer(source_layer)
        if target_layer is None:
            return CompressionResult(
                success=False,
                source_layer=source_layer,
                target_layer="",
                source_count=0,
                new_memory=None,
                error=f"Layer {source_layer} has no target layer for compaction",
            )

        async with async_session() as session:
            stmt = select(Memory).where(
                Memory.persona_id == persona_id,
                Memory.layer == source_layer,
            )
            rows = (await session.execute(stmt)).scalars().all()
            memories = [
                {
                    "id": m.id,
                    "content": m.content,
                    "html_content": m.html_content,
                    "importance": m.importance,
                    "tags": list(m.tags) if m.tags else [],
                    "layer": m.layer,
                }
                for m in rows
                if "compressed" not in (m.tags or [])
            ]

        if not memories:
            return CompressionResult(
                success=True,
                source_layer=source_layer,
                target_layer=target_layer,
                source_count=0,
                new_memory=None,
                error="No memories to compact",
            )

        groups = self._group_memories_by_tag(memories)
        created: list[tuple[dict, list[int]]] = []
        compressed_ids: list[int] = []

        # v2.2.1 P2-5: 并发执行 _compact_group — K 个分组不再串行等待 LLM
        # _compact_group 仅读取入参(memories/source_layer/target_layer/persona_id),
        # 不修改共享状态;返回值由下方顺序遍历写入 created/compressed_ids,无竞争。
        # return_exceptions=True: 单组失败不阻塞其他组,异常在此处隔离记录。
        group_keys = list(groups.keys())
        group_items = list(groups.values())
        tasks = [
            self._compact_group(gm, source_layer, target_layer, persona_id)
            for gm in group_items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for group_key, group_memories, result in zip(group_keys, group_items, results):
            if isinstance(result, Exception):
                logger.warning(f"compact group {group_key} failed: {result}")
                continue
            if result is None:
                continue
            ids = [m["id"] for m in group_memories]
            created.append((result, ids))
            compressed_ids.extend(ids)

        if not created:
            return CompressionResult(
                success=False,
                source_layer=source_layer,
                target_layer=target_layer,
                source_count=0,
                new_memory=None,
                compressed_ids=[],
                error="All groups failed to compact",
            )

        async with async_session() as session:
            for new_mem, _ in created:
                session.add(
                    Memory(
                        persona_id=persona_id,
                        layer=target_layer,
                        content=new_mem.get("title", "compressed memory"),
                        html_content=new_mem.get("html_content"),
                        importance=new_mem.get("importance", 0.8),
                        tags=new_mem.get("tags", []),
                    )
                )

            if compressed_ids:
                orig_stmt = select(Memory).where(Memory.id.in_(compressed_ids))
                originals = (await session.execute(orig_stmt)).scalars().all()
                for mem in originals:
                    mem.importance = 0.1
                    tags = list(mem.tags) if mem.tags else []
                    if "compressed" not in tags:
                        tags.append("compressed")
                    mem.tags = tags

            await session.commit()

        return CompressionResult(
            success=True,
            source_layer=source_layer,
            target_layer=target_layer,
            source_count=len(compressed_ids),
            new_memory=created[0][0],
            compressed_ids=compressed_ids,
        )

    async def _compact_group(
        self,
        memories: list[dict],
        source_layer: str,
        target_layer: str,
        persona_id: int,
    ) -> dict | None:
        prompt = self._build_compact_prompt(memories, source_layer, target_layer)
        messages = [
            Message(
                role="system",
                content=(
                    "你是记忆压缩引擎，负责将多条低层记忆压缩为一条精炼的高层记忆。"
                    "只返回 JSON，不要输出其他内容。"
                ),
            ),
            Message(role="user", content=prompt),
        ]
        try:
            provider = get_provider(self.model_provider)
            chunks: list[str] = []
            async for chunk in provider.generate(messages, model=self.model_name):
                chunks.append(chunk)
            raw = "".join(chunks).strip()
            return self._parse_llm_response(raw)
        except Exception:
            return None

    def _group_memories_by_tag(self, memories: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for m in memories:
            tags = m.get("tags") or []
            key = tags[0] if tags else "general"
            groups.setdefault(key, []).append(m)

        result: dict[str, list[dict]] = {}
        for key, items in groups.items():
            if len(items) <= 10:
                result[key] = items
                continue
            items_sorted = sorted(
                items, key=lambda x: x.get("importance", 0), reverse=True
            )
            for i in range(0, len(items_sorted), 10):
                result[f"{key}_{i // 10}"] = items_sorted[i : i + 10]
        return result

    def _build_compact_prompt(
        self, memories: list[dict], source_layer: str, target_layer: str
    ) -> str:
        lines = [
            f"以下是 {source_layer} 层的 {len(memories)} 条记忆，请压缩为一条 {target_layer} 层记忆。",
            '返回 JSON 格式：{"title": "...", "html_content": "...", "importance": 0.8, "tags": [...]}',
            "html_content 要求：保留关键信息，使用 <details> 折叠细节，<strong> 标记重点。",
            "",
        ]
        for i, m in enumerate(memories, 1):
            lines.append(
                f"[{i}] (importance={m.get('importance', 0.5)}, tags={m.get('tags', [])})"
            )
            lines.append(m.get("content", ""))
            if m.get("html_content"):
                lines.append(m["html_content"])
            lines.append("")
        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> dict:
        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
        data = json.loads(raw)
        return {
            "title": data.get("title", "compressed memory"),
            "html_content": data.get("html_content", ""),
            "importance": float(data.get("importance", 0.8)),
            "tags": list(data.get("tags", [])),
        }
