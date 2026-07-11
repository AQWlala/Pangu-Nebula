from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass
class CompactResult:
    messages: list[dict]
    compacted: bool
    tokens_before: int
    tokens_after: int
    strategy: str  # "none" | "auto" | "emergency"


class CompactEngine:
    def __init__(
        self,
        max_tokens: int = 128000,
        compact_threshold: float = 0.8,
        emergency_threshold: float = 0.95,
    ):
        self.max_tokens = max_tokens
        self.compact_threshold = compact_threshold  # 80% 触发自动压缩
        self.emergency_threshold = emergency_threshold  # 95% 触发紧急压缩

    def estimate_tokens(self, messages: list[dict]) -> int:
        """估算消息列表的 token 数量（1 token ≈ 4 字符英文 / 2 字符中文）"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            chinese_count = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
            other_count = len(content) - chinese_count
            total += chinese_count * 0.5 + other_count * 0.25 + 4  # +4 for role overhead
        return int(total)

    def should_compact(self, messages: list[dict]) -> str:
        """返回压缩策略：none/auto/emergency"""
        tokens = self.estimate_tokens(messages)
        ratio = tokens / self.max_tokens
        if ratio >= self.emergency_threshold:
            return "emergency"
        if ratio >= self.compact_threshold:
            return "auto"
        return "none"

    async def auto_compact(
        self,
        messages: list[dict],
        llm_call: Optional[Callable[[list[dict]], Awaitable[str]]] = None,
    ) -> list[dict]:
        """自动压缩：保留 system 消息 + 最近 N 条，中间用 LLM 摘要"""
        if llm_call is None:
            return await self.emergency_compact(messages)
        if len(messages) <= 7:
            return messages

        head = messages[:1]
        recent = messages[-6:]
        middle = messages[1:-6]
        if not middle:
            return messages

        summary = await llm_call(middle)
        summary_msg = {
            "role": "system",
            "content": f"[Summary of earlier conversation]\n{summary}",
        }
        return head + [summary_msg] + recent

    async def emergency_compact(self, messages: list[dict]) -> list[dict]:
        """紧急压缩：保留 system + 最后 3 条，其余截断"""
        if len(messages) <= 4:
            return messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        recent = messages[-3:]
        marker = {
            "role": "system",
            "content": "[Earlier messages compacted due to context limit]",
        }
        return system_msgs + [marker] + recent

    async def compact_if_needed(
        self,
        messages: list[dict],
        llm_call: Optional[Callable[[list[dict]], Awaitable[str]]] = None,
    ) -> CompactResult:
        """主入口：根据需要自动压缩"""
        strategy = self.should_compact(messages)
        tokens_before = self.estimate_tokens(messages)

        if strategy == "none":
            return CompactResult(
                messages=messages,
                compacted=False,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                strategy="none",
            )

        if strategy == "emergency":
            compacted = await self.emergency_compact(messages)
            return CompactResult(
                messages=compacted,
                compacted=True,
                tokens_before=tokens_before,
                tokens_after=self.estimate_tokens(compacted),
                strategy="emergency",
            )

        compacted = await self.auto_compact(messages, llm_call)
        return CompactResult(
            messages=compacted,
            compacted=True,
            tokens_before=tokens_before,
            tokens_after=self.estimate_tokens(compacted),
            strategy="auto",
        )
