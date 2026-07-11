"""Wiki 编译引擎 (Phase 6A)。

将对话内容编译为结构化 Wiki 笔记,支持:
- 从对话调用 LLM 自动编译为 HTML 笔记
- 双向链接 (backlinks) 自动同步
- 手动创建 / 更新 / 删除 / 搜索 Wiki 页面
"""

import re

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import async_session
from ..db.orm import WikiPage, Conversation, Message, Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider, is_registered

_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _wiki_to_dict(w: WikiPage) -> dict:
    """ORM 对象转 dict"""
    return {
        "id": w.id,
        "persona_id": w.persona_id,
        "title": w.title,
        "content": w.content,
        "html_content": w.html_content,
        "plain_text": w.plain_text,
        "tags": w.tags or [],
        "links": w.links or [],
        "backlinks": w.backlinks or [],
        "status": w.status,
        "source_conversation_id": w.source_conversation_id,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


def _persona_scope(wiki: WikiPage):
    """限定同一 persona 作用域 (None 与 None 匹配)"""
    if wiki.persona_id is None:
        return WikiPage.persona_id.is_(None)
    return WikiPage.persona_id == wiki.persona_id


class WikiService:
    # 编译 Wiki 的 LLM 系统提示
    _COMPILE_SYSTEM_PROMPT = (
        "你是一个 Wiki 笔记编译器。请将以下对话编译为结构化的 Wiki 笔记,"
        "使用 HTML 格式输出,包含标题(<h1>-<h3>)、要点列表(<ul>)、"
        "代码块(<pre><code>)等。使用 [[标题]] 语法链接到相关概念。"
        "只输出 HTML 内容,不要额外解释。"
    )
    _COMPILE_USER_PROMPT_TEMPLATE = (
        "请将以下对话编译为结构化的 Wiki 笔记,使用 HTML 格式,"
        "包含标题、要点、代码块等。使用 [[标题]] 语法链接到相关概念。\n\n"
        "对话内容:\n{dialogue}"
    )

    def _extract_plain_text(self, html: str) -> str:
        """去除 HTML 标签与 [[链接]] 语法,返回纯文本"""
        if not html:
            return ""
        text = _TAG_RE.sub(" ", html)
        text = _LINK_RE.sub(r"\1", text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_links(self, html: str) -> list[str]:
        """从 HTML 中提取 [[标题]] 链接列表 (去重保序)"""
        if not html:
            return []
        seen: list[str] = []
        for t in _LINK_RE.findall(html):
            if t not in seen:
                seen.append(t)
        return seen

    async def _sync_backlinks(self, session: AsyncSession, wiki_page: WikiPage):
        """同步双向链接 (新建时使用):
        - 当其他 Wiki.links 包含 wiki_page.title 时,wiki_page.backlinks 收集其 id
        - 当 wiki_page.links 包含其他 Wiki.title 时,在该 Wiki.backlinks 中加入 wiki_page.id
        """
        result = await session.execute(
            select(WikiPage).where(_persona_scope(wiki_page), WikiPage.id != wiki_page.id)
        )
        others = result.scalars().all()
        new_backlinks: list[int] = []
        target_titles = set(wiki_page.links or [])
        for m in others:
            # 别人链接到我 → 我收集 backlink
            if wiki_page.title in (m.links or []):
                new_backlinks.append(m.id)
            # 我链接到别人 → 别人收集 backlink
            if m.title in target_titles:
                bl = list(m.backlinks or [])
                if wiki_page.id not in bl:
                    bl.append(wiki_page.id)
                    m.backlinks = bl
        wiki_page.backlinks = new_backlinks
        await session.commit()

    async def _recompute_backlinks(
        self, session: AsyncSession, wiki_page: WikiPage, old_title: str, old_links: list[str]
    ):
        """重新计算双向链接 (更新时使用):
        - 依据新 title 重建 wiki_page.backlinks
        - 依据新/旧 links 增删其他 Wiki.backlinks 中对 wiki_page.id 的引用
        """
        result = await session.execute(
            select(WikiPage).where(_persona_scope(wiki_page), WikiPage.id != wiki_page.id)
        )
        others = result.scalars().all()
        new_links = set(wiki_page.links or [])
        old_links_set = set(old_links)
        new_backlinks: list[int] = []
        for m in others:
            # 别人链接到我 (新 title)
            if wiki_page.title in (m.links or []):
                new_backlinks.append(m.id)
            # 我链接到别人 → 添加 backlink
            if m.title in new_links:
                bl = list(m.backlinks or [])
                if wiki_page.id not in bl:
                    bl.append(wiki_page.id)
                    m.backlinks = bl
            # 我不再链接到别人 (旧 links 中有,新 links 中没有) → 移除 backlink
            elif m.title in old_links_set:
                bl = list(m.backlinks or [])
                if wiki_page.id in bl:
                    bl.remove(wiki_page.id)
                    m.backlinks = bl
        wiki_page.backlinks = new_backlinks

    async def compile_from_conversation(
        self,
        conversation_id: int,
        persona_id: int | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """从对话编译 Wiki 笔记:
        读取对话所有 Message → 调用 LLM 编译为 HTML → 提取 plain_text/links → 同步 backlinks
        返回 {"ok": bool, "data": dict|None, "error": str|None}
        """
        # 1. 读取对话、消息、persona
        async with async_session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return {"ok": False, "data": None, "error": f"Conversation {conversation_id} not found"}

            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            messages = list(result.scalars().all())

            # persona 优先用入参,否则用对话的 persona_id
            effective_persona_id = persona_id if persona_id is not None else conversation.persona_id
            persona: Persona | None = None
            if effective_persona_id is not None:
                persona = await session.get(Persona, effective_persona_id)

        if not messages:
            return {"ok": False, "data": None, "error": "Conversation has no messages to compile"}

        # 2. 校验 Provider
        model_provider = persona.model_provider if persona else None
        model_name = persona.model_name if persona else "gpt-4"
        if not model_provider:
            return {"ok": False, "data": None, "error": "No model provider configured for this persona"}
        if not is_registered(model_provider):
            return {"ok": False, "data": None, "error": f"Provider '{model_provider}' not registered"}

        # 3. 构造对话文本并调用 LLM
        dialogue_lines = [f"[{m.role}] {m.content}" for m in messages]
        dialogue = "\n\n".join(dialogue_lines)
        user_prompt = self._COMPILE_USER_PROMPT_TEMPLATE.format(dialogue=dialogue)

        provider_messages = [
            ProviderMessage(role="system", content=self._COMPILE_SYSTEM_PROMPT),
            ProviderMessage(role="user", content=user_prompt),
        ]

        try:
            provider = get_provider(model_provider)
        except ValueError as exc:
            return {"ok": False, "data": None, "error": str(exc)}

        html_content = ""
        try:
            async for chunk in provider.generate(
                provider_messages, model_name, temperature=0.7, max_tokens=4096
            ):
                html_content += chunk
        except Exception as exc:
            return {"ok": False, "data": None, "error": f"LLM generate failed: {exc}"}

        html_content = html_content.strip()
        if not html_content:
            return {"ok": False, "data": None, "error": "LLM returned empty content"}

        # 4. 生成标题 (若未提供则用对话标题或回退默认)
        wiki_title = title or (conversation.title or f"Wiki from conversation #{conversation_id}")

        # 5. 提取 plain_text 与 links
        plain_text = self._extract_plain_text(html_content)
        links = self._extract_links(html_content)

        # 6. 持久化 WikiPage
        async with async_session() as session:
            wiki_page = WikiPage(
                persona_id=effective_persona_id,
                title=wiki_title,
                content=plain_text,
                html_content=html_content,
                plain_text=plain_text,
                tags=tags or [],
                links=links,
                backlinks=[],
                status="compiled",
                source_conversation_id=conversation_id,
            )
            session.add(wiki_page)
            await session.commit()
            await session.refresh(wiki_page)

            # 7. 同步双向链接
            await self._sync_backlinks(session, wiki_page)
            await session.refresh(wiki_page)
            return {"ok": True, "data": _wiki_to_dict(wiki_page), "error": None}

    async def create_wiki(
        self,
        title: str,
        content: str = "",
        html_content: str = "",
        persona_id: int | None = None,
        tags: list[str] | None = None,
        source_conversation_id: int | None = None,
        status: str = "draft",
    ) -> dict:
        """手动创建 Wiki 页面,自动提取 plain_text/links 并同步 backlinks"""
        html = html_content or ""
        plain_text = self._extract_plain_text(html) if html else (content or "")
        links = self._extract_links(html)

        async with async_session() as session:
            wiki_page = WikiPage(
                persona_id=persona_id,
                title=title,
                content=content or plain_text,
                html_content=html,
                plain_text=plain_text,
                tags=tags or [],
                links=links,
                backlinks=[],
                status=status,
                source_conversation_id=source_conversation_id,
            )
            session.add(wiki_page)
            await session.commit()
            await session.refresh(wiki_page)

            await self._sync_backlinks(session, wiki_page)
            await session.refresh(wiki_page)
            return _wiki_to_dict(wiki_page)

    async def get_wiki(self, wiki_id: int) -> dict | None:
        """获取单个 Wiki 页面"""
        async with async_session() as session:
            wiki_page = await session.get(WikiPage, wiki_id)
            return _wiki_to_dict(wiki_page) if wiki_page else None

    async def list_wikis(
        self,
        persona_id: int | None = None,
        tag: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        """列出 Wiki 页面 (支持 persona_id/tag/status 过滤 + 分页)"""
        async with async_session() as session:
            stmt = select(WikiPage)
            if persona_id is not None:
                stmt = stmt.where(WikiPage.persona_id == persona_id)
            if tag is not None:
                stmt = stmt.where(WikiPage.tags.like(f'%"{tag}"%'))
            if status is not None:
                stmt = stmt.where(WikiPage.status == status)
            stmt = stmt.order_by(WikiPage.created_at.desc())
            stmt = stmt.offset(max(page - 1, 0) * page_size).limit(page_size)
            result = await session.execute(stmt)
            return [_wiki_to_dict(w) for w in result.scalars().all()]

    async def update_wiki(self, wiki_id: int, **kwargs) -> dict | None:
        """更新 Wiki 页面:
        - html_content 变更 → 重新提取 plain_text 和 links
        - title 变更 → 重新同步 backlinks
        """
        async with async_session() as session:
            wiki_page = await session.get(WikiPage, wiki_id)
            if not wiki_page:
                return None

            old_title = wiki_page.title
            old_links = list(wiki_page.links or [])
            html_changed = False
            title_changed = False

            for key, value in kwargs.items():
                if value is None:
                    continue
                setattr(wiki_page, key, value)
                if key == "html_content":
                    html_changed = True
                if key == "title":
                    title_changed = True

            if html_changed:
                wiki_page.plain_text = self._extract_plain_text(wiki_page.html_content or "")
                wiki_page.content = wiki_page.plain_text
                wiki_page.links = self._extract_links(wiki_page.html_content or "")

            if html_changed or title_changed:
                await self._recompute_backlinks(session, wiki_page, old_title, old_links)

            await session.commit()
            await session.refresh(wiki_page)
            return _wiki_to_dict(wiki_page)

    async def delete_wiki(self, wiki_id: int) -> bool:
        """删除 Wiki 页面,并清理其他 WikiPage 的 backlinks 引用"""
        async with async_session() as session:
            wiki_page = await session.get(WikiPage, wiki_id)
            if not wiki_page:
                return False

            # 清理其他 WikiPage.backlinks 中对 wiki_id 的引用
            result = await session.execute(
                select(WikiPage).where(_persona_scope(wiki_page), WikiPage.id != wiki_id)
            )
            for m in result.scalars().all():
                bl = list(m.backlinks or [])
                if wiki_id in bl:
                    bl.remove(wiki_id)
                    m.backlinks = bl

            await session.delete(wiki_page)
            await session.commit()
            return True

    async def search_wikis(
        self,
        query: str,
        persona_id: int | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """LIKE 模糊搜索 (plain_text + title)"""
        pattern = f"%{query.lower()}%"
        cond = or_(
            func.lower(WikiPage.plain_text).like(pattern),
            func.lower(WikiPage.title).like(pattern),
        )
        async with async_session() as session:
            stmt = select(WikiPage).where(cond)
            if persona_id is not None:
                stmt = stmt.where(WikiPage.persona_id == persona_id)
            stmt = stmt.order_by(WikiPage.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return [_wiki_to_dict(w) for w in result.scalars().all()]


wiki_service = WikiService()
