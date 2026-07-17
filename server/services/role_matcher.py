from __future__ import annotations
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.orm import Persona, PersonaRelation

class RoleMatcher:
    """角色匹配器 — 按三元组相似度/互补度匹配候选关联角色

    借鉴 CrewAI 三元组 + OpenAkita AgentInstancePool。
    """

    async def find_candidates(
        self, session: AsyncSession, persona_id: int, limit: int = 5
    ) -> list[dict]:
        """为指定角色找候选关联角色

        返回 [{"persona": {...}, "score": 0.85, "relation_type": "complement"}]
        """
        persona = await session.get(Persona, persona_id)
        if not persona:
            return []
        # 查所有其他角色
        result = await session.execute(
            select(Persona).where(Persona.id != persona_id)
        )
        others = list(result.scalars().all())
        candidates = []
        for other in others:
            score = self._compute_similarity(persona, other)
            relation_type = self._infer_relation_type(persona, other)
            candidates.append({
                "persona": self._persona_to_dict(other),
                "score": score,
                "relation_type": relation_type,
            })
        # 按分数降序, 取 top limit
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

    def _compute_similarity(self, a: Persona, b: Persona) -> float:
        """计算两个角色的三元组相似度 (0.0-1.0)"""
        # 分别计算 role/goal/backstory 的文本相似度, 加权平均
        role_sim = SequenceMatcher(None, (a.role or ""), (b.role or "")).ratio()
        goal_sim = SequenceMatcher(None, (a.goal or ""), (b.goal or "")).ratio()
        backstory_sim = SequenceMatcher(None, (a.backstory or ""), (b.backstory or "")).ratio()
        # role 权重最高
        return role_sim * 0.5 + goal_sim * 0.3 + backstory_sim * 0.2

    def _infer_relation_type(self, a: Persona, b: Persona) -> str:
        """推断关系类型: complement(互补)/assist(协助)/delegate(委派)"""
        # 简易规则: role 相似度高 → assist; role 不同但 goal 相似 → complement
        role_sim = SequenceMatcher(None, (a.role or ""), (b.role or "")).ratio()
        goal_sim = SequenceMatcher(None, (a.goal or ""), (b.goal or "")).ratio()
        if role_sim > 0.6:
            return "assist"
        if goal_sim > 0.5:
            return "complement"
        return "delegate"

    def _persona_to_dict(self, p: Persona) -> dict:
        return {
            "id": p.id, "name": p.name, "role": p.role, "goal": p.goal,
            "backstory": p.backstory, "avatar": p.avatar,
        }

# 单例
_role_matcher = RoleMatcher()
def get_role_matcher() -> RoleMatcher:
    return _role_matcher
