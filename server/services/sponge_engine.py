from dataclasses import dataclass
from typing import Optional
import json
import re
import difflib

from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider


@dataclass
class SpongeResult:
    extracted: bool
    memory: dict | None
    reason: str


class SpongeEngine:
    """海绵引擎：自动从对话中提取记忆"""

    LAYER_PROMPTS = {
        "L0": "瞬时记忆：当前对话的临时上下文，短期有效",
        "L1": "工作记忆：近期任务相关信息，中期有效",
        "L2": "情景记忆：具体事件、对话片段、用户偏好",
        "L3": "语义记忆：知识点、概念、事实",
        "L4": "程序记忆：技能、流程、经验教训",
        "L5": "核心记忆：用户身份、价值观、长期目标",
    }

    BATCH_SIZE = 10
    DEDUP_THRESHOLD = 0.8

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-4o-mini"):
        self.model_provider = model_provider
        self.model_name = model_name

    async def absorb(
        self,
        messages: list[dict],
        persona_id: int,
        existing_memories: list[dict] | None = None,
    ) -> SpongeResult:
        existing_memories = existing_memories or []

        if not messages:
            return SpongeResult(extracted=False, memory=None, reason="无消息可分析")

        user_prompt = self._build_absorb_prompt(messages, existing_memories)
        provider_messages = [
            ProviderMessage(
                role="system",
                content=(
                    "你是记忆管理助手，负责从对话中提取有价值的记忆。"
                    "请分析对话内容，判断是否有值得长期记忆的信息。"
                    "必须只返回 JSON，不要附加任何解释文字。"
                ),
            ),
            ProviderMessage(role="user", content=user_prompt),
        ]

        try:
            provider = get_provider(self.model_provider)
        except ValueError as exc:
            return SpongeResult(extracted=False, memory=None, reason=f"provider 不可用: {exc}")

        raw_response = ""
        try:
            async for chunk in provider.generate(provider_messages, model=self.model_name):
                raw_response += chunk
        except Exception as exc:
            return SpongeResult(extracted=False, memory=None, reason=f"LLM 调用失败: {exc}")

        parsed = self._parse_llm_response(raw_response)
        if parsed is None:
            return SpongeResult(
                extracted=False,
                memory=None,
                reason=f"无法解析 LLM 响应: {raw_response[:200]}",
            )

        if not parsed.get("should_extract", False):
            return SpongeResult(
                extracted=False,
                memory=None,
                reason=parsed.get("reason", "对话内容无需长期记忆"),
            )

        memory = {
            "persona_id": persona_id,
            "layer": parsed.get("layer", "L2"),
            "title": parsed.get("title", ""),
            "content": parsed.get("content", parsed.get("title", "")),
            "html_content": parsed.get("html_content", ""),
            "plain_text": self._strip_html(parsed.get("html_content", "")),
            "importance": float(parsed.get("importance", 0.5)),
            "tags": parsed.get("tags", []),
            "links": self._extract_links(parsed.get("html_content", "")),
            "backlinks": [],
        }

        if memory["layer"] not in self.LAYER_PROMPTS:
            memory["layer"] = "L2"

        if not memory["title"] or not memory["html_content"]:
            return SpongeResult(
                extracted=False,
                memory=None,
                reason="提取的记忆缺少必要字段（title 或 html_content）",
            )

        if self._should_deduplicate(memory, existing_memories):
            return SpongeResult(
                extracted=False,
                memory=None,
                reason=f"与已有记忆重复（标题相似度过高）: {memory['title']}",
            )

        return SpongeResult(
            extracted=True,
            memory=memory,
            reason=parsed.get("reason", "成功提取记忆"),
        )

    async def batch_absorb(
        self,
        messages: list[dict],
        persona_id: int,
        existing_memories: list[dict] | None = None,
    ) -> list[SpongeResult]:
        existing_memories = existing_memories or []
        results: list[SpongeResult] = []

        for i in range(0, len(messages), self.BATCH_SIZE):
            batch = messages[i : i + self.BATCH_SIZE]
            result = await self.absorb(batch, persona_id, existing_memories)
            results.append(result)
            if result.extracted and result.memory:
                existing_memories = existing_memories + [result.memory]

        return results

    def _build_absorb_prompt(
        self,
        messages: list[dict],
        existing_memories: list[dict] | None,
    ) -> str:
        lines: list[str] = []
        lines.append("以下是一段对话内容：\n")
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"[{role}]: {content}")
        lines.append("")

        lines.append("记忆层级说明：")
        for layer, desc in self.LAYER_PROMPTS.items():
            lines.append(f"- {layer}: {desc}")
        lines.append("")

        existing_titles = [
            m.get("title", "") for m in (existing_memories or []) if m.get("title")
        ]
        if existing_titles:
            lines.append("已有记忆标题列表（可使用 [[标题]] 引用）：")
            for title in existing_titles:
                lines.append(f"- {title}")
            lines.append("")

        lines.append("请判断这段对话中是否有值得长期记忆的信息。")
        lines.append("如果有，返回如下 JSON（只返回 JSON，不要 markdown 代码块）：")
        lines.append(
            '{"should_extract": true, "layer": "L2", "title": "记忆标题", '
            '"content": "纯文本摘要", "html_content": "<p>...</p>", '
            '"importance": 0.7, "tags": ["标签1"], "reason": "提取说明"}'
        )
        lines.append("如果没有，返回：")
        lines.append('{"should_extract": false, "reason": "对话内容无需长期记忆"}')
        lines.append("")
        lines.append("html_content 要求：")
        lines.append("- 使用 <p> 段落结构")
        lines.append("- 使用 <details><summary>...</summary>...</details> 折叠详细信息")
        lines.append("- 使用 <strong> 标记关键信息")
        lines.append("- 使用 [[相关记忆标题]] 格式引用已有记忆，建立双向链接")
        lines.append("- 内容应精炼、结构化、便于后续检索")
        lines.append("importance 取值 0.0-1.0，越高越重要。")
        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> dict | None:
        if not response or not response.strip():
            return None

        text = response.strip()

        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start == -1 or brace_end == -1 or brace_end <= brace_start:
            return None
        text = text[brace_start : brace_end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None
        if "should_extract" not in data:
            return None
        return data

    def _should_deduplicate(
        self, new_memory: dict, existing_memories: list[dict]
    ) -> bool:
        new_title = new_memory.get("title", "")
        if not new_title:
            return False
        new_title_lower = new_title.lower()
        for mem in existing_memories:
            existing_title = mem.get("title", "")
            if not existing_title:
                continue
            ratio = difflib.SequenceMatcher(
                None, new_title_lower, existing_title.lower()
            ).ratio()
            if ratio > self.DEDUP_THRESHOLD:
                return True
        return False

    def _extract_links(self, html_content: str) -> list[str]:
        return re.findall(r"\[\[([^\]]+)\]\]", html_content)

    def _strip_html(self, html_content: str) -> str:
        no_tags = re.sub(r"<[^>]+>", " ", html_content)
        no_links = re.sub(r"\[\[([^\]]+)\]\]", r"\1", no_tags)
        return re.sub(r"\s+", " ", no_links).strip()
