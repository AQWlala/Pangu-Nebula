"""v2.3.1 P0-7: 技能持久化共享模块

抽取自 server/api/skills.py 和 server/api/skill_market.py 中重复实现的:
- load_enabled_map:        从 DB 读取 {name: enabled} 映射
- persist_skill_enabled:   持久化 enabled 到 DB (upsert)
- publish_skill_toggled:   发布 skill.enabled.toggled 事件

同时提供共享 SkillLoader 单例 (替代两个 API 各自实例化的独立 _loader),
统一内存缓存, 避免 enabled 状态在两个 API 间不一致。

设计要点:
- 三个函数均 best-effort, DB/事件总线失败仅记录日志, 不阻断主流程
- source 参数保留两处 API 原有差异 (custom vs builtin / skills_api vs skill_market_api)
  以维持事件溯源的可观察性, 不影响 DB upsert 语义 (已存在的行不修改 source)
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..core.event_bus import get_event_bus
from ..db.engine import async_session
from ..db.orm import Skill as SkillRow
from ..services.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


# 共享 SkillLoader 单例 — 替代 skills.py / skill_market.py 各自的 _loader
# 统一内存缓存, 避免 enabled 状态在两个 API 间不一致 (P0-7 修复点)
loader = SkillLoader()


async def load_enabled_map() -> dict[str, bool]:
    """从 DB 读取所有 Skill 行的 {name: enabled} 映射

    DB 失败时返回空 dict (best-effort, 不阻塞技能列表加载)。
    """
    try:
        async with async_session() as session:
            rows = (await session.execute(select(SkillRow))).scalars().all()
            return {row.name: bool(row.enabled) for row in rows}
    except Exception:
        logger.debug("加载 Skill.enabled 映射失败 (DB 不可用?)", exc_info=True)
        return {}


async def persist_skill_enabled(
    name: str, enabled: bool, source: str = "custom"
) -> None:
    """持久化单个技能的 enabled 状态到 DB

    策略: upsert — 按 name 查询, 存在则更新 enabled, 不存在则插入新行。
    DB 失败仅记录日志, 不抛异常 (CRUD 主流程不被阻断)。

    Args:
        name: 技能名
        enabled: 目标启用状态
        source: 新建行时的来源标签 (custom/builtin); 已存在的行不修改 source
    """
    try:
        async with async_session() as session:
            row = (
                await session.execute(select(SkillRow).where(SkillRow.name == name))
            ).scalar_one_or_none()
            if row is None:
                # 插入新行 (source 仅作占位, 实际由 loader 管理)
                row = SkillRow(name=name, enabled=enabled, source=source)
                session.add(row)
            else:
                row.enabled = enabled
            await session.commit()
    except Exception:
        logger.warning("持久化 Skill.enabled 失败 name=%s", name, exc_info=True)


async def publish_skill_toggled(
    name: str, enabled: bool, source: str = "skills_api"
) -> None:
    """发布 skill.enabled.toggled 事件

    异常不阻断主流程 (事件丢失可由下次全量加载修正)。

    Args:
        name: 技能名
        enabled: 目标启用状态
        source: 事件来源标签 (skills_api/skill_market_api), 用于事件溯源
    """
    try:
        bus = get_event_bus()
        await bus.publish(
            "skill.enabled.toggled",
            {"skill_id": name, "enabled": enabled},
            source=source,
        )
    except Exception:
        logger.debug("publish skill.enabled.toggled 失败 name=%s", name, exc_info=True)
