import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_settings
from ..db.orm import Persona
from ..providers.base import Message
from ..providers.registry import get_provider, is_registered


def _persona_to_dict(p: Persona) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "avatar": p.avatar,
        "system_prompt": p.system_prompt,
        "temperature": p.temperature,
        "max_tokens": p.max_tokens,
        "model_provider": p.model_provider,
        "model_name": p.model_name,
        # v2.3.0 A3: 角色三元组 + allowed_paths
        "role": p.role,
        "goal": p.goal,
        "backstory": p.backstory,
        "allowed_paths": p.allowed_paths,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def list_personas(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(Persona).order_by(Persona.created_at.desc()))
    return [_persona_to_dict(p) for p in result.scalars().all()]


async def get_persona(session: AsyncSession, persona_id: int) -> dict | None:
    persona = await session.get(Persona, persona_id)
    return _persona_to_dict(persona) if persona else None


async def create_persona(session: AsyncSession, data: dict) -> dict:
    persona = Persona(**data)
    session.add(persona)
    await session.commit()
    await session.refresh(persona)
    return _persona_to_dict(persona)


async def update_persona(session: AsyncSession, persona_id: int, data: dict) -> dict | None:
    persona = await session.get(Persona, persona_id)
    if not persona:
        return None
    for key, value in data.items():
        setattr(persona, key, value)
    await session.commit()
    await session.refresh(persona)
    return _persona_to_dict(persona)


async def delete_persona(session: AsyncSession, persona_id: int) -> bool:
    persona = await session.get(Persona, persona_id)
    if not persona:
        return False
    await session.delete(persona)
    await session.commit()
    return True


async def generate_persona_with_ai(
    description: str,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict:
    settings = load_settings()
    provider_name = model_provider or settings.provider_default or "openai"
    if not is_registered(provider_name):
        raise ValueError(f"Provider '{provider_name}' not registered")

    provider = get_provider(provider_name)
    model = model_name or getattr(provider, "default_chat_model", "gpt-4o-mini")

    prompt = (
        "You are a persona design assistant. Based on the user's description, "
        "generate a persona configuration. Respond ONLY with a JSON object "
        "with keys: name, system_prompt, temperature, max_tokens. "
        "The system_prompt should be detailed and well-structured. "
        "temperature should be between 0.0 and 1.0. max_tokens between 256 and 8192.\n\n"
        f"User description: {description}"
    )
    messages = [Message(role="user", content=prompt)]

    chunks: list[str] = []
    async for chunk in provider.generate(messages, model):
        chunks.append(chunk)
    raw = "".join(chunks).strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    parsed = json.loads(raw)
    return {
        "name": parsed.get("name", ""),
        "system_prompt": parsed.get("system_prompt", ""),
        "temperature": float(parsed.get("temperature", 0.7)),
        "max_tokens": int(parsed.get("max_tokens", 4096)),
        "model_provider": provider_name,
        "model_name": model,
    }
