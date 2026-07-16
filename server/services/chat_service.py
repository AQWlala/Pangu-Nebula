import json
import logging
from typing import AsyncIterator

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from ..db.engine import async_session
from ..db.orm import Conversation, Message, Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider
from ..tools.registry import list_tools_schema
from .compact import CompactEngine
from .knowledge_service import format_rag_context, knowledge_service
from .tool_executor import tool_executor

logger = logging.getLogger(__name__)


# v2.2.0: 工具调用循环最大轮次,防止死循环
MAX_TOOL_ROUNDS = 10

# v2.2.1 S2: 工具结果截断 — 防止 token 爆炸
# 业务专家反: 截断可能丢失关键工具输出 → 应对方案: 截断长度可配置,保留首尾各 1000 字符
_MAX_TOOL_RESULT_CHARS = 2000  # 可配置: 工具结果回喂 LLM 的最大字符数


def _truncate_tool_result(content, max_chars: int = _MAX_TOOL_RESULT_CHARS):
    """截断工具结果,保留首尾各 max_chars//2 字符。

    - None / 非字符串 / 短内容: 原样返回,不抛异常
    - 长内容: 保留首尾,中间用 ``...[truncated N chars]...`` 标记
    """
    if not isinstance(content, str) or len(content) <= max_chars:
        return content
    keep = max_chars // 2
    return (
        f"{content[:keep]}"
        f"\n...[truncated {len(content) - max_chars} chars]...\n"
        f"{content[-keep:]}"
    )


# 系统默认 Persona (兜底用, 不入库)
# 当对话未关联 Persona 且数据库无任何 Persona 时使用, 避免直接报错阻断对话。
# model_provider 留空, 会走到 "No model provider configured" 友好引导分支。
_DEFAULT_PERSONA = Persona(
    id=0,
    name="Nebula 默认助手",
    avatar="🧸",
    system_prompt="你是一个友好的 AI 助手。请先在角色管理中创建并激活一个角色以获得更好的体验。",
    temperature=0.7,
    max_tokens=4096,
    model_provider=None,
    model_name="gpt-4",
    # v2.2.0 能力开关 (transient 对象不会在构造时应用 column default,需显式设置)
    tools_enabled=True,
    rag_enabled=True,
    sandbox_allow_network=False,
    terminal_allowed=False,
    browser_use_enabled=False,
)


class ChatService:
    def __init__(self):
        self.compact = CompactEngine()

    async def create_conversation(
        self, persona_id: int | None, title: str | None
    ) -> Conversation:
        async with async_session() as session:
            conv = Conversation(persona_id=persona_id, title=title)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return conv

    async def list_conversations(self) -> list[Conversation]:
        async with async_session() as session:
            result = await session.execute(
                select(Conversation).order_by(Conversation.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_conversation(self, conversation_id: int) -> Conversation | None:
        async with async_session() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .options(
                    selectinload(Conversation.persona),
                    selectinload(Conversation.messages),
                )
            )
            return result.scalar_one_or_none()

    async def delete_conversation(self, conversation_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                delete(Conversation).where(Conversation.id == conversation_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def list_messages(self, conversation_id: int) -> list[Message]:
        async with async_session() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            return list(result.scalars().all())

    async def stream_reply(
        self, conversation_id: int, user_content: str
    ) -> AsyncIterator[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .options(selectinload(Conversation.persona))
            )
            conv = result.scalar_one_or_none()
            if conv is None:
                yield {"type": "error", "error": "Conversation not found"}
                return

            persona = conv.persona
            if persona is None:
                # 回退 1: 尝试用数据库中第一个 Persona (应对 active_state 丢失或对话未关联)
                fallback_result = await session.execute(
                    select(Persona).order_by(Persona.created_at.asc()).limit(1)
                )
                persona = fallback_result.scalar_one_or_none()
                # 回退 2: 仍无 Persona, 用系统默认 (会走到下方 "No model provider" 友好引导)
                if persona is None:
                    persona = _DEFAULT_PERSONA

            system_prompt = persona.system_prompt
            model_provider = persona.model_provider
            model_name = persona.model_name
            temperature = persona.temperature
            max_tokens = persona.max_tokens

            user_msg = Message(
                conversation_id=conversation_id,
                role="user",
                content=user_content,
            )
            session.add(user_msg)
            await session.commit()

            # v2.2.0 Phase 4: RAG 检索 — 在构建 messages 前注入知识库上下文
            rag_context_text = ""
            rag_sources: list[dict] = []
            rag_error: str = ""  # v2.2.1 S9: RAG 异常不再静默
            if bool(getattr(persona, "rag_enabled", False)):
                try:
                    rag_results = await knowledge_service.search(
                        user_content, top_k=3, scope="private"
                    )
                    if rag_results:
                        rag_context_text = format_rag_context(rag_results)
                        # v2.2.1 S9: preview None 安全 (修复 text=None 时 TypeError)
                        rag_sources = []
                        for r in rag_results:
                            preview_text = r.get("text", "") or ""
                            preview = (
                                preview_text[:200] + "..."
                                if len(preview_text) > 200
                                else preview_text
                            )
                            rag_sources.append({
                                "doc_id": r.get("doc_id", ""),
                                "score": r.get("score", 0.0),
                                "preview": preview,
                            })
                except Exception as rag_exc:
                    # v2.2.1 S9: RAG 异常不再静默 — 通知用户 RAG 不可用
                    logger.warning(f"RAG retrieval failed: {rag_exc}")
                    rag_error = f"知识库检索暂不可用: {rag_exc}"

            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            history = list(result.scalars().all())

        msg_dicts = [{"role": "system", "content": system_prompt}]
        for msg in history:
            msg_dicts.append({"role": msg.role, "content": msg.content})

        compact_result = await self.compact.compact_if_needed(msg_dicts)
        provider_messages = [
            ProviderMessage(role=m["role"], content=m["content"])
            for m in compact_result.messages
        ]

        # v2.2.0 Phase 4: 注入 RAG 上下文到 system prompt
        # v2.2.1 S9: RAG 异常不再静默 — 通知用户 RAG 不可用,并继续对话
        if rag_error:
            yield {"type": "rag_context", "sources": [], "error": rag_error}
        elif rag_context_text:
            # 在 system message 后插入独立的 RAG 上下文 message,避免污染原 system prompt
            rag_msg = ProviderMessage(role="system", content=rag_context_text)
            # v2.2.1 S9: RAG 上下文插入到最后一个 system 消息之后,而非固定位置 1
            # (compact 可能产生多个 system 消息,固定 insert(1, ...) 会插错位置)
            insert_idx = 0
            for i, msg in enumerate(provider_messages):
                if msg.role == "system":
                    insert_idx = i + 1
            provider_messages.insert(insert_idx, rag_msg)
            # 通知前端展示了哪些 RAG 来源
            yield {"type": "rag_context", "sources": rag_sources}

        if not model_provider:
            yield {
                "type": "error",
                "error": "尚未配置模型 Provider，请在「设置」中添加 API Key 后，在「角色管理」创建并激活角色",
            }
            return

        try:
            provider = get_provider(model_provider)
        except ValueError as exc:
            yield {"type": "error", "error": str(exc)}
            return

        # v2.2.0: 工具调用开关与 schema
        tools_enabled = bool(getattr(persona, "tools_enabled", False))
        tools_schema = list_tools_schema() if tools_enabled else None

        full_response = ""
        last_tool_calls_json: str | None = None  # 最近一轮工具调用,用于持久化

        try:
            rounds = 0
            while True:
                rounds += 1
                if rounds > MAX_TOOL_ROUNDS:
                    yield {
                        "type": "error",
                        "error": f"工具调用超过最大轮次 ({MAX_TOOL_ROUNDS}),已中止以防死循环",
                    }
                    break

                round_text = ""
                # index -> {"id","name","arguments"} 累计流式 tool_calls 增量
                acc_tool_calls: dict[int, dict] = {}
                finish_reason = None

                stream_kwargs: dict = {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools_schema:
                    stream_kwargs["tools"] = tools_schema

                async for chunk in provider.stream(
                    provider_messages, model_name, **stream_kwargs
                ):
                    if chunk.text:
                        round_text += chunk.text
                        full_response += chunk.text
                        yield {"type": "token", "content": chunk.text}
                    if chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            idx = tc.get("index", 0)
                            acc = acc_tool_calls.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if tc.get("id"):
                                acc["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                acc["name"] = (acc["name"] or "") + fn["name"]
                            if fn.get("arguments"):
                                acc["arguments"] += fn["arguments"]
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason

                # 累计出本轮工具调用列表
                tool_calls_list = [
                    {
                        "id": acc_tool_calls[i]["id"] or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": acc_tool_calls[i]["name"],
                            "arguments": acc_tool_calls[i]["arguments"],
                        },
                    }
                    for i in sorted(acc_tool_calls)
                    if acc_tool_calls[i]["name"]
                ]

                # v2.2.1 S4: finish_reason 兼容判断
                # 部分 provider 返回 tool_calls 时 finish_reason 可能为 None,
                # 仅在 tool_calls 为空或 finish_reason 明确不是 "tool_calls" 时才 break。
                if not tool_calls_list:
                    break
                if finish_reason is not None and finish_reason != "tool_calls":
                    # 明确不是 tool_calls 时才 break
                    break
                # tool_calls_list 非空且 (finish_reason is None 或 finish_reason == "tool_calls") 时继续执行工具

                # 有工具调用 → 执行并回喂
                last_tool_calls_json = json.dumps(tool_calls_list, ensure_ascii=False)

                # 1. assistant 工具调用消息回填 history
                provider_messages.append(
                    ProviderMessage(
                        role="assistant",
                        content=round_text or None,
                        tool_calls=tool_calls_list,
                    )
                )

                # 2. 逐个执行工具 (ToolExecutor 接管权限检查/注入防护/审计记录)
                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    yield {
                        "type": "tool_call",
                        "id": tc["id"],
                        "name": tool_name,
                        "arguments": args,
                    }

                    exec_result = await tool_executor.execute(
                        tool_name, args, persona
                    )
                    # 回喂 LLM 的文本: 优先 output, 其次 error
                    result_text = exec_result["output"] or exec_result["error"]
                    success = exec_result["success"]

                    yield {
                        "type": "tool_result",
                        "id": tc["id"],
                        "name": tool_name,
                        "result": result_text,
                        "success": success,
                    }

                    # v2.2.1 S2: 回喂 LLM 前截断工具结果,防止 provider_messages 累积导致 token 爆炸
                    # 注意: 仅截断回喂 LLM 的 content,前端 yield 仍用原始 result_text
                    truncated_result = _truncate_tool_result(result_text)
                    provider_messages.append(
                        ProviderMessage(
                            role="tool",
                            content=truncated_result,
                            tool_call_id=tc["id"],
                        )
                    )
                # 继续下一轮,让 LLM 基于工具结果生成
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            # 仍保存已生成内容,避免丢失
            if full_response:
                await self._persist_assistant(
                    conversation_id, full_response, last_tool_calls_json
                )
            return

        # 持久化 assistant 消息
        msg_id = await self._persist_assistant(
            conversation_id, full_response, last_tool_calls_json
        )
        yield {"type": "done", "message_id": str(msg_id)}

    async def _persist_assistant(
        self, conversation_id: int, content: str, tool_calls_json: str | None
    ) -> int:
        """持久化 assistant 消息并返回其 id。"""
        async with async_session() as session:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                tool_calls=tool_calls_json,
            )
            session.add(assistant_msg)
            await session.commit()
            await session.refresh(assistant_msg)
            return assistant_msg.id
