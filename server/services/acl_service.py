"""ACL 权限系统 (Phase 8A)

实现基于规则的访问控制:
- 规则匹配: persona_id 匹配 + resource 模式匹配(fnmatch) + action 匹配
- 优先级: deny 规则优先于 allow 规则
- 默认策略: 无匹配规则时返回 True (默认允许)

融合来源:
- Nebula 的安全模块设计
- 通用 ACL 模式
"""

from fnmatch import fnmatchcase
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import AclRule


def _rule_to_dict(rule: AclRule) -> dict:
    """ORM 转 dict"""
    return {
        "id": rule.id,
        "persona_id": rule.persona_id,
        "resource": rule.resource,
        "action": rule.action,
        "effect": rule.effect,
        "permission": rule.permission,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


class ACLService:
    """ACL 权限系统:规则管理 + 权限检查"""

    def _match_resource(self, pattern: str, resource: str) -> bool:
        """fnmatch 模式匹配

        - pattern 支持通配符: *, ?, [seq]
        - 大小写不敏感(资源路径通常不区分大小写)
        """
        if not pattern:
            return False
        return fnmatchcase(resource.lower(), pattern.lower())

    def _match_action(self, rule_action: str, requested_action: str) -> bool:
        """动作匹配: rule_action 为 * 时匹配所有,否则需精确相等"""
        if not rule_action:
            return False
        if rule_action == "*":
            return True
        return rule_action.lower() == (requested_action or "").lower()

    async def create_rule(
        self,
        session: AsyncSession,
        persona_id: int | None,
        resource: str,
        action: str = "*",
        effect: str = "allow",
    ) -> dict:
        """创建 ACL 规则"""
        rule = AclRule(
            persona_id=persona_id,
            resource=resource,
            action=action,
            effect=effect,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return _rule_to_dict(rule)

    async def list_rules(
        self, session: AsyncSession, persona_id: int | None = None
    ) -> list[dict]:
        """列出规则

        - persona_id 为 None: 返回所有规则
        - persona_id 有值: 返回该 persona 的规则 + 全局规则(persona_id IS NULL)
        """
        stmt = select(AclRule).order_by(AclRule.created_at.desc())
        if persona_id is not None:
            # 返回该 persona 的规则 + 全局规则
            stmt = stmt.where(
                (AclRule.persona_id == persona_id)
                | (AclRule.persona_id.is_(None))
            )
        result = await session.execute(stmt)
        return [_rule_to_dict(r) for r in result.scalars().all()]

    async def get_rule(self, session: AsyncSession, rule_id: int) -> dict | None:
        """获取单条规则"""
        rule = await session.get(AclRule, rule_id)
        return _rule_to_dict(rule) if rule else None

    async def update_rule(
        self, session: AsyncSession, rule_id: int, **kwargs: Any
    ) -> dict | None:
        """更新规则(仅更新提供的字段)"""
        rule = await session.get(AclRule, rule_id)
        if not rule:
            return None
        for key, value in kwargs.items():
            if value is None:
                continue
            if hasattr(rule, key):
                setattr(rule, key, value)
        await session.commit()
        await session.refresh(rule)
        return _rule_to_dict(rule)

    async def delete_rule(self, session: AsyncSession, rule_id: int) -> bool:
        """删除规则"""
        rule = await session.get(AclRule, rule_id)
        if not rule:
            return False
        await session.delete(rule)
        await session.commit()
        return True

    async def check_permission(
        self,
        session: AsyncSession,
        persona_id: int | None,
        resource: str,
        action: str,
    ) -> dict:
        """权限检查

        匹配逻辑:
        - persona_id 匹配: 规则的 persona_id 为 NULL(全局规则) 或 等于传入的 persona_id
        - resource 模式匹配: fnmatch
        - action 匹配: 规则 action 为 * 或 等于传入的 action

        优先级:
        - deny 规则优先于 allow 规则
        - 若有匹配的 deny 规则,直接拒绝
        - 若无 deny 但有 allow 规则,允许
        - 若无任何匹配规则,默认允许(返回 True)

        返回 {"allowed": bool, "matched_rule": {...} | None, "reason": "..."}
        """
        stmt = select(AclRule).order_by(AclRule.created_at.desc())
        result = await session.execute(stmt)
        all_rules = result.scalars().all()

        matched_deny: AclRule | None = None
        matched_allow: AclRule | None = None

        for rule in all_rules:
            # persona_id 匹配: 全局规则(persona_id IS NULL) 或精确匹配
            if rule.persona_id is not None and rule.persona_id != persona_id:
                continue
            # resource 模式匹配
            if not self._match_resource(rule.resource, resource):
                continue
            # action 匹配
            if not self._match_action(rule.action, action):
                continue
            # 命中规则,按 effect 分类
            if rule.effect == "deny":
                if matched_deny is None:
                    matched_deny = rule
            else:  # allow
                if matched_allow is None:
                    matched_allow = rule

        # deny 优先
        if matched_deny is not None:
            return {
                "allowed": False,
                "matched_rule": _rule_to_dict(matched_deny),
                "reason": f"匹配到 deny 规则(id={matched_deny.id}, resource={matched_deny.resource})",
            }

        if matched_allow is not None:
            return {
                "allowed": True,
                "matched_rule": _rule_to_dict(matched_allow),
                "reason": f"匹配到 allow 规则(id={matched_allow.id}, resource={matched_allow.resource})",
            }

        # 无匹配规则,默认允许
        return {
            "allowed": True,
            "matched_rule": None,
            "reason": "无匹配规则,默认允许",
        }


# 模块级单例
acl_service = ACLService()
