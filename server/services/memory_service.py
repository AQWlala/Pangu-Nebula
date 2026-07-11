import re

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import Memory

_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _memory_to_dict(m: Memory) -> dict:
    return {
        "id": m.id,
        "persona_id": m.persona_id,
        "layer": m.layer,
        "title": m.title,
        "content": m.content,
        "html_content": m.html_content,
        "plain_text": m.plain_text,
        "importance": m.importance,
        "tags": m.tags or [],
        "links": m.links or [],
        "backlinks": m.backlinks or [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _persona_scope(memory: Memory):
    if memory.persona_id is None:
        return Memory.persona_id.is_(None)
    return Memory.persona_id == memory.persona_id


class MemoryService:
    def _extract_plain_text(self, html: str) -> str:
        if not html:
            return ""
        text = _TAG_RE.sub(" ", html)
        text = _LINK_RE.sub(r"\1", text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_links(self, html: str) -> list[str]:
        if not html:
            return []
        seen: list[str] = []
        for t in _LINK_RE.findall(html):
            if t not in seen:
                seen.append(t)
        return seen

    async def create_memory(
        self,
        session: AsyncSession,
        persona_id: int | None,
        layer: str,
        title: str,
        html_content: str,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> dict:
        plain_text = self._extract_plain_text(html_content)
        links = self._extract_links(html_content)
        memory = Memory(
            persona_id=persona_id,
            layer=layer,
            title=title,
            content=plain_text,
            html_content=html_content,
            plain_text=plain_text,
            importance=importance,
            tags=tags or [],
            links=links,
            backlinks=[],
        )
        session.add(memory)
        await session.commit()
        await session.refresh(memory)

        await self._sync_backlinks_for_new(session, memory)
        await session.refresh(memory)
        return _memory_to_dict(memory)

    async def _sync_backlinks_for_new(self, session: AsyncSession, memory: Memory):
        result = await session.execute(
            select(Memory).where(_persona_scope(memory), Memory.id != memory.id)
        )
        others = result.scalars().all()
        new_backlinks: list[int] = []
        target_titles = set(memory.links or [])
        for m in others:
            if memory.title in (m.links or []):
                new_backlinks.append(m.id)
            if m.title in target_titles:
                bl = list(m.backlinks or [])
                if memory.id not in bl:
                    bl.append(memory.id)
                    m.backlinks = bl
        memory.backlinks = new_backlinks
        await session.commit()

    async def get_memory(self, session: AsyncSession, memory_id: int) -> dict | None:
        memory = await session.get(Memory, memory_id)
        return _memory_to_dict(memory) if memory else None

    async def list_memories(
        self,
        session: AsyncSession,
        persona_id: int | None = None,
        layer: str | None = None,
        tag: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        stmt = select(Memory)
        if persona_id is not None:
            stmt = stmt.where(Memory.persona_id == persona_id)
        if layer is not None:
            stmt = stmt.where(Memory.layer == layer)
        if tag is not None:
            stmt = stmt.where(Memory.tags.like(f'%"{tag}"%'))
        stmt = stmt.order_by(Memory.created_at.desc())
        stmt = stmt.offset(max(page - 1, 0) * page_size).limit(page_size)
        result = await session.execute(stmt)
        return [_memory_to_dict(m) for m in result.scalars().all()]

    async def update_memory(self, session: AsyncSession, memory_id: int, **kwargs) -> dict | None:
        memory = await session.get(Memory, memory_id)
        if not memory:
            return None
        old_title = memory.title
        old_links = list(memory.links or [])
        html_changed = False
        title_changed = False
        for key, value in kwargs.items():
            if value is None:
                continue
            setattr(memory, key, value)
            if key == "html_content":
                html_changed = True
            if key == "title":
                title_changed = True
        if html_changed:
            memory.plain_text = self._extract_plain_text(memory.html_content or "")
            memory.content = memory.plain_text
            memory.links = self._extract_links(memory.html_content or "")
        if html_changed or title_changed:
            await self._recompute_backlinks(session, memory, old_title, old_links)
        await session.commit()
        await session.refresh(memory)
        return _memory_to_dict(memory)

    async def _recompute_backlinks(
        self, session: AsyncSession, memory: Memory, old_title: str, old_links: list[str]
    ):
        result = await session.execute(
            select(Memory).where(_persona_scope(memory), Memory.id != memory.id)
        )
        others = result.scalars().all()
        new_links = set(memory.links or [])
        old_links_set = set(old_links)
        new_backlinks: list[int] = []
        for m in others:
            if memory.title in (m.links or []):
                new_backlinks.append(m.id)
            if m.title in new_links:
                bl = list(m.backlinks or [])
                if memory.id not in bl:
                    bl.append(memory.id)
                    m.backlinks = bl
            elif m.title in old_links_set:
                bl = list(m.backlinks or [])
                if memory.id in bl:
                    bl.remove(memory.id)
                    m.backlinks = bl
        memory.backlinks = new_backlinks

    async def delete_memory(self, session: AsyncSession, memory_id: int) -> bool:
        memory = await session.get(Memory, memory_id)
        if not memory:
            return False
        result = await session.execute(
            select(Memory).where(_persona_scope(memory), Memory.id != memory_id)
        )
        for m in result.scalars().all():
            bl = list(m.backlinks or [])
            if memory_id in bl:
                bl.remove(memory_id)
                m.backlinks = bl
        await session.delete(memory)
        await session.commit()
        return True

    async def search_memories(
        self,
        session: AsyncSession,
        query: str,
        persona_id: int | None = None,
        layer: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        pattern = f"%{query.lower()}%"
        cond = or_(
            func.lower(Memory.plain_text).like(pattern),
            func.lower(Memory.title).like(pattern),
            func.lower(Memory.content).like(pattern),
        )
        stmt = select(Memory).where(cond)
        if persona_id is not None:
            stmt = stmt.where(Memory.persona_id == persona_id)
        if layer is not None:
            stmt = stmt.where(Memory.layer == layer)
        stmt = stmt.order_by(Memory.importance.desc()).limit(limit)
        result = await session.execute(stmt)
        return [_memory_to_dict(m) for m in result.scalars().all()]

    async def get_backlinks(self, session: AsyncSession, memory_id: int) -> list[dict]:
        memory = await session.get(Memory, memory_id)
        if not memory:
            return []
        ids = memory.backlinks or []
        if not ids:
            return []
        result = await session.execute(select(Memory).where(Memory.id.in_(ids)))
        return [_memory_to_dict(m) for m in result.scalars().all()]

    async def get_linked_graph(
        self,
        session: AsyncSession,
        persona_id: int | None = None,
        layer: str | None = None,
    ) -> dict:
        stmt = select(Memory)
        if persona_id is not None:
            stmt = stmt.where(Memory.persona_id == persona_id)
        if layer is not None:
            stmt = stmt.where(Memory.layer == layer)
        result = await session.execute(stmt)
        memories = result.scalars().all()
        nodes = [
            {
                "id": m.id,
                "title": m.title,
                "layer": m.layer,
                "importance": m.importance,
            }
            for m in memories
        ]
        title_to_id = {m.title: m.id for m in memories}
        edges: list[dict] = []
        for m in memories:
            for t in (m.links or []):
                target_id = title_to_id.get(t)
                if target_id is not None and target_id != m.id:
                    edges.append({"source": m.id, "target": target_id})
        return {"nodes": nodes, "edges": edges}


memory_service = MemoryService()
