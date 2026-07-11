"""进化引擎(Phase 6B)。

实现 Nebula 设计的 4 阶段进化管道:
- extract: L1→L2,从原始对话记忆提取关键信息
- compile: L2→L3,将零散信息结构化为知识网络
- reflect: L2+L3→L5,深度反思生成元认知
- soul: L5→SOUL.md,生成新的角色灵魂文件(需用户确认)
"""

import difflib
import re

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import async_session
from ..db.orm import EvolutionLog, Memory, Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider, is_registered

# 解析 <memory title="...">内容</memory> 标签
_MEMORY_TAG_RE = re.compile(r'<memory\s+title="([^"]*)">(.*?)</memory>', re.DOTALL)
# 解析 [[标题]] 链接
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class EvolutionEngine:
    """进化引擎:编排 4 阶段进化管道"""

    # 各层 Memory 的默认重要度
    _IMPORTANCE_MAP = {
        "L2": 0.6,
        "L3": 0.7,
        "L5": 0.9,
    }

    # ===== 4 阶段实现 =====

    async def extract_phase(
        self, session: AsyncSession, persona_id: int, trigger: str = "manual"
    ) -> dict:
        """Extract 阶段 (L1→L2):从原始对话记忆提取关键信息"""
        persona = await session.get(Persona, persona_id)

        # 读取 L1 层记忆
        result = await session.execute(
            select(Memory)
            .where(Memory.persona_id == persona_id, Memory.layer == "L1")
            .order_by(Memory.created_at.asc())
        )
        l1_memories = list(result.scalars().all())
        before_state = {"L1_count": len(l1_memories)}

        log = await self._create_log(session, persona_id, "extract", trigger, before_state)

        try:
            if not persona:
                raise ValueError(f"Persona {persona_id} 不存在")

            if not l1_memories:
                after_state = {"L2_count": 0, "extracted_items": 0}
                await self._complete_log(
                    session, log, after_state, details={"reason": "无 L1 记忆可提取"}
                )
                return self._log_to_dict(log)

            # 构建 LLM 提示
            l1_text = self._format_memories(l1_memories)
            system_prompt = "你是一个知识提取引擎。从用户的原始对话记忆中提取关键信息。"
            user_prompt = (
                f"以下是与 {persona.name} 的原始对话记忆(L1层)。请提取关键信息，"
                f"每个要点用 <memory> 标签包裹，包含 title 和 content。\n"
                f"返回格式:\n"
                f'<memory title="...">内容</memory>\n'
                f'<memory title="...">内容</memory>\n\n'
                f"L1 记忆内容:\n{l1_text}"
            )

            response = await self._call_llm(persona, system_prompt, user_prompt)
            extracted = self._parse_memory_tags(response)

            # 写入 L2 层
            for title, content in extracted:
                self._add_memory(session, persona_id, "L2", title, content, tags=["extracted"])
            await session.commit()

            after_state = {"L2_count": len(extracted), "extracted_items": len(extracted)}
            details = {"sample_titles": [t for t, _ in extracted[:5]]}
            await self._complete_log(session, log, after_state, details)
            return self._log_to_dict(log)
        except Exception as e:
            await self._fail_log(session, log, str(e))
            return self._log_to_dict(log)

    async def compile_phase(
        self, session: AsyncSession, persona_id: int, trigger: str = "manual"
    ) -> dict:
        """Compile 阶段 (L2→L3):将零散信息结构化为知识网络"""
        persona = await session.get(Persona, persona_id)

        # 读取 L2 层记忆
        result = await session.execute(
            select(Memory)
            .where(Memory.persona_id == persona_id, Memory.layer == "L2")
            .order_by(Memory.created_at.asc())
        )
        l2_memories = list(result.scalars().all())
        before_state = {"L2_count": len(l2_memories)}

        log = await self._create_log(session, persona_id, "compile", trigger, before_state)

        try:
            if not persona:
                raise ValueError(f"Persona {persona_id} 不存在")

            if not l2_memories:
                after_state = {"L3_count": 0, "compiled_units": 0}
                await self._complete_log(
                    session, log, after_state, details={"reason": "无 L2 记忆可编译"}
                )
                return self._log_to_dict(log)

            # 构建 LLM 提示
            l2_text = self._format_memories(l2_memories)
            system_prompt = "你是一个知识编译引擎。将零散的提取信息结构化为知识网络。"
            user_prompt = (
                f"以下是从 L2 层提取的零散信息。请将相关信息分组、整合，"
                f"生成结构化的知识单元。\n"
                f"每个知识单元用 <memory> 标签包裹，包含 title 和 content，"
                f"并用 [[标题]] 链接到相关概念。\n\n"
                f"L2 记忆内容:\n{l2_text}"
            )

            response = await self._call_llm(persona, system_prompt, user_prompt)
            compiled = self._parse_memory_tags(response)

            # 写入 L3 层
            for title, content in compiled:
                self._add_memory(session, persona_id, "L3", title, content, tags=["compiled"])
            await session.commit()

            after_state = {"L3_count": len(compiled), "compiled_units": len(compiled)}
            details = {"sample_titles": [t for t, _ in compiled[:5]]}
            await self._complete_log(session, log, after_state, details)
            return self._log_to_dict(log)
        except Exception as e:
            await self._fail_log(session, log, str(e))
            return self._log_to_dict(log)

    async def reflect_phase(
        self, session: AsyncSession, persona_id: int, trigger: str = "manual"
    ) -> dict:
        """Reflect 阶段 (L2+L3→L5):深度反思生成元认知"""
        persona = await session.get(Persona, persona_id)

        # 读取 L2 和 L3 层记忆
        result = await session.execute(
            select(Memory)
            .where(Memory.persona_id == persona_id, Memory.layer.in_(["L2", "L3"]))
            .order_by(Memory.created_at.asc())
        )
        memories = list(result.scalars().all())
        before_state = {"L2_count": sum(1 for m in memories if m.layer == "L2"),
                        "L3_count": sum(1 for m in memories if m.layer == "L3")}

        log = await self._create_log(session, persona_id, "reflect", trigger, before_state)

        try:
            if not persona:
                raise ValueError(f"Persona {persona_id} 不存在")

            if not memories:
                after_state = {"L5_count": 0, "reflections": 0}
                await self._complete_log(
                    session, log, after_state, details={"reason": "无 L2/L3 记忆可反思"}
                )
                return self._log_to_dict(log)

            # 构建 LLM 提示
            memories_text = self._format_memories(memories)
            system_prompt = "你是一个深度反思引擎。对已结构化的知识进行元认知反思。"
            user_prompt = (
                f"以下是 L2 和 L3 层的知识。请进行深度反思，生成元认知洞察。\n"
                f"反思应包含：模式发现、知识缺口、改进建议。\n"
                f"每个反思用 <memory> 标签包裹，包含 title 和 content。\n\n"
                f"L2+L3 记忆内容:\n{memories_text}"
            )

            response = await self._call_llm(persona, system_prompt, user_prompt)
            reflections = self._parse_memory_tags(response)

            # 写入 L5 层
            for title, content in reflections:
                self._add_memory(session, persona_id, "L5", title, content, tags=["reflected"])
            await session.commit()

            after_state = {"L5_count": len(reflections), "reflections": len(reflections)}
            details = {"sample_titles": [t for t, _ in reflections[:5]]}
            await self._complete_log(session, log, after_state, details)
            return self._log_to_dict(log)
        except Exception as e:
            await self._fail_log(session, log, str(e))
            return self._log_to_dict(log)

    async def soul_phase(
        self, session: AsyncSession, persona_id: int, trigger: str = "manual"
    ) -> dict:
        """Soul 阶段 (L5→SOUL.md):生成新的角色灵魂文件(需用户确认)"""
        persona = await session.get(Persona, persona_id)

        # 读取 L5 层记忆
        result = await session.execute(
            select(Memory)
            .where(Memory.persona_id == persona_id, Memory.layer == "L5")
            .order_by(Memory.created_at.asc())
        )
        l5_memories = list(result.scalars().all())
        old_soul = persona.system_prompt if persona else ""
        before_state = {"L5_count": len(l5_memories), "old_soul": old_soul}

        log = await self._create_log(session, persona_id, "soul", trigger, before_state)

        try:
            if not persona:
                raise ValueError(f"Persona {persona_id} 不存在")

            if not l5_memories:
                after_state = {"new_soul": old_soul, "diff": [], "changed": False}
                await self._complete_log(
                    session, log, after_state, details={"reason": "无 L5 记忆可生成 SOUL.md"}
                )
                return self._log_to_dict(log)

            # 构建 LLM 提示
            l5_text = self._format_memories(l5_memories)
            system_prompt = "你是一个灵魂工程师。根据反思结果生成角色的 SOUL.md。"
            user_prompt = (
                f"以下是 L5 层的反思记忆。请基于这些反思，为角色生成新的 SOUL.md（system_prompt）。\n"
                f"当前 SOUL.md:\n{old_soul}\n\n"
                f"L5 反思内容:\n{l5_text}\n\n"
                f"请生成更新后的 SOUL.md:"
            )

            new_soul = await self._call_llm(persona, system_prompt, user_prompt)
            new_soul = new_soul.strip()

            if not new_soul:
                raise ValueError("LLM 返回空的 SOUL.md 内容")

            # 差异检测(difflib)
            diff = list(
                difflib.unified_diff(
                    old_soul.splitlines(),
                    new_soul.splitlines(),
                    fromfile="current_SOUL.md",
                    tofile="new_SOUL.md",
                    lineterm="",
                )
            )
            changed = len(diff) > 0

            after_state = {"new_soul": new_soul, "diff": diff, "changed": changed}
            details = {
                "diff_lines": len(diff),
                "awaiting_confirm": True,
                "message": "SOUL.md 已生成，等待用户确认后更新",
            }
            await self._complete_log(session, log, after_state, details)
            return self._log_to_dict(log)
        except Exception as e:
            await self._fail_log(session, log, str(e))
            return self._log_to_dict(log)

    # ===== 管道编排 =====

    async def run_pipeline(
        self, persona_id: int, phases: list[str], trigger: str = "manual"
    ) -> list[dict]:
        """进化管道编排:按 phases 顺序执行各阶段"""
        phase_map = {
            "extract": self.extract_phase,
            "compile": self.compile_phase,
            "reflect": self.reflect_phase,
            "soul": self.soul_phase,
        }

        logs: list[dict] = []
        async with async_session() as session:
            for phase in phases:
                handler = phase_map.get(phase)
                if handler is None:
                    # 未知阶段,记录失败日志并停止管道
                    log = await self._create_log(session, persona_id, phase, trigger, {})
                    await self._fail_log(session, log, f"未知阶段: {phase}")
                    logs.append(self._log_to_dict(log))
                    break

                try:
                    log_dict = await handler(session, persona_id, trigger)
                    logs.append(log_dict)
                    # 阶段失败则停止管道(避免级联错误)
                    if log_dict.get("status") == "failed":
                        break
                except Exception as e:
                    # 未预期的异常(阶段方法内部未能捕获)
                    log = await self._create_log(session, persona_id, phase, trigger, {})
                    await self._fail_log(session, log, str(e))
                    logs.append(self._log_to_dict(log))
                    break

        return logs

    # ===== 查询与确认 =====

    async def list_logs(
        self,
        session: AsyncSession,
        persona_id: int | None = None,
        phase: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """查询进化日志"""
        stmt = select(EvolutionLog)
        if persona_id is not None:
            stmt = stmt.where(EvolutionLog.persona_id == persona_id)
        if phase:
            stmt = stmt.where(EvolutionLog.phase == phase)
        stmt = stmt.order_by(desc(EvolutionLog.created_at)).limit(limit)
        result = await session.execute(stmt)
        return [self._log_to_dict(log) for log in result.scalars().all()]

    async def get_log(self, session: AsyncSession, log_id: int) -> dict | None:
        """获取单个进化日志"""
        log = await session.get(EvolutionLog, log_id)
        return self._log_to_dict(log) if log else None

    async def confirm_soul(
        self, session: AsyncSession, persona_id: int, log_id: int
    ) -> dict | None:
        """用户确认 SOUL.md 更新:从 EvolutionLog.after_state 提取 new_soul 并更新 Persona"""
        log = await session.get(EvolutionLog, log_id)
        if not log:
            return None
        if log.phase != "soul":
            return None

        after_state = log.after_state or {}
        new_soul = after_state.get("new_soul")
        if not new_soul:
            return None

        persona = await session.get(Persona, persona_id)
        if not persona:
            return None

        persona.system_prompt = new_soul
        await session.commit()
        await session.refresh(persona)

        return self._persona_to_dict(persona)

    # ===== 辅助方法 =====

    async def _create_log(
        self,
        session: AsyncSession,
        persona_id: int,
        phase: str,
        trigger: str,
        before_state: dict,
    ) -> EvolutionLog:
        """创建运行中的 EvolutionLog"""
        log = EvolutionLog(
            persona_id=persona_id,
            phase=phase,
            status="running",
            trigger=trigger,
            before_state=before_state,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    async def _complete_log(
        self,
        session: AsyncSession,
        log: EvolutionLog,
        after_state: dict,
        details: dict | None = None,
    ) -> EvolutionLog:
        """标记 EvolutionLog 为已完成"""
        log.status = "completed"
        log.after_state = after_state
        if details is not None:
            log.details = details
        await session.commit()
        await session.refresh(log)
        return log

    async def _fail_log(
        self, session: AsyncSession, log: EvolutionLog, error: str
    ) -> EvolutionLog | None:
        """标记 EvolutionLog 为失败(回滚未提交的变更后更新日志)"""
        log_id = log.id
        # 回滚未提交的 Memory 等变更(日志本身已提交,不受影响)
        await session.rollback()
        # 重新获取日志对象(rollback 后原对象已过期)
        log = await session.get(EvolutionLog, log_id)
        if log:
            log.status = "failed"
            log.details = {"error": error}
            await session.commit()
            await session.refresh(log)
        return log

    async def _call_llm(
        self, persona: Persona, system_prompt: str, user_prompt: str
    ) -> str:
        """调用 LLM 辅助方法"""
        if not persona.model_provider:
            raise ValueError("Persona 未配置 model_provider")
        if not is_registered(persona.model_provider):
            raise ValueError(f"Provider '{persona.model_provider}' 未注册")

        provider = get_provider(persona.model_provider)
        messages = [
            ProviderMessage(role="system", content=system_prompt),
            ProviderMessage(role="user", content=user_prompt),
        ]

        full_response = ""
        async for chunk in provider.generate(
            messages,
            persona.model_name,
            temperature=persona.temperature,
            max_tokens=persona.max_tokens,
        ):
            full_response += chunk
        return full_response

    def _format_memories(self, memories: list[Memory]) -> str:
        """格式化 Memory 列表为可读文本"""
        lines = []
        for i, m in enumerate(memories, 1):
            content = m.content or m.plain_text or ""
            lines.append(
                f"--- 记忆 {i} ---\n"
                f"标题: {m.title}\n"
                f"层级: {m.layer}\n"
                f"内容: {content}"
            )
        return "\n\n".join(lines)

    def _parse_memory_tags(self, text: str) -> list[tuple[str, str]]:
        """解析 <memory title="...">内容</memory> 标签,返回 (title, content) 列表"""
        matches = _MEMORY_TAG_RE.findall(text)
        return [(title.strip(), content.strip()) for title, content in matches]

    def _add_memory(
        self,
        session: AsyncSession,
        persona_id: int,
        layer: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Memory:
        """创建 Memory 并添加到 session(调用方负责 commit)"""
        links = _LINK_RE.findall(content)
        importance = self._IMPORTANCE_MAP.get(layer, 0.5)
        memory = Memory(
            persona_id=persona_id,
            layer=layer,
            title=title,
            content=content,
            html_content=content,
            plain_text=content,
            importance=importance,
            tags=tags or [],
            links=list(dict.fromkeys(links)),  # 去重保序
            backlinks=[],
        )
        session.add(memory)
        return memory

    def _log_to_dict(self, log: EvolutionLog) -> dict:
        """ORM 转 dict"""
        return {
            "id": log.id,
            "persona_id": log.persona_id,
            "phase": log.phase,
            "status": log.status,
            "trigger": log.trigger,
            "before_state": log.before_state,
            "after_state": log.after_state,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    def _persona_to_dict(self, p: Persona) -> dict:
        """Persona ORM 转 dict"""
        return {
            "id": p.id,
            "name": p.name,
            "avatar": p.avatar,
            "system_prompt": p.system_prompt,
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "model_provider": p.model_provider,
            "model_name": p.model_name,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
