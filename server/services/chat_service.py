from typing import AsyncIterator

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from ..db.engine import async_session
from ..db.orm import Conversation, Message, Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider
from .compact import CompactEngine


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

        full_response = ""
        try:
            async for chunk in provider.generate(
                provider_messages,
                model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                full_response += chunk
                yield {"type": "token", "content": chunk}
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return

        async with async_session() as session:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
            )
            session.add(assistant_msg)
            await session.commit()
            await session.refresh(assistant_msg)
            msg_id = assistant_msg.id

        yield {"type": "done", "message_id": str(msg_id)}
