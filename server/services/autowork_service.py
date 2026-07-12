"""AutoWork 无人值守框架服务层 (T1.1)。

提供任务会话的创建、认领、完成、暂停、恢复及看板视图能力。
所有外部通知为 mock 实现。
"""

from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.autowork_models import AutoWorkSession


def _session_to_dict(s: AutoWorkSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "status": s.status,
        "priority": s.priority,
        "assigned_to": s.assigned_to,
        "config": s.config or {},
        "result": s.result,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
    }


class AutoWorkService:
    """AutoWork 无人值守任务服务"""

    async def create_session(
        self,
        session: AsyncSession,
        title: str,
        description: str = "",
        config: dict | None = None,
    ) -> dict:
        record = AutoWorkSession(
            title=title,
            description=description,
            status="pending",
            config=config or {},
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def list_sessions(
        self, session: AsyncSession, status: str | None = None
    ) -> list[dict]:
        stmt = select(AutoWorkSession).order_by(
            AutoWorkSession.priority.desc(), AutoWorkSession.created_at.desc()
        )
        if status:
            stmt = stmt.where(AutoWorkSession.status == status)
        result = await session.execute(stmt)
        return [_session_to_dict(s) for s in result.scalars().all()]

    async def get_session(
        self, session: AsyncSession, session_id: int
    ) -> dict | None:
        record = await session.get(AutoWorkSession, session_id)
        return _session_to_dict(record) if record else None

    async def claim_session(
        self, session: AsyncSession, session_id: int, assigned_to: str
    ) -> dict:
        record = await session.get(AutoWorkSession, session_id)
        if not record:
            return None
        record.assigned_to = assigned_to
        record.status = "running"
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def complete_session(
        self, session: AsyncSession, session_id: int, result: str
    ) -> dict:
        record = await session.get(AutoWorkSession, session_id)
        if not record:
            return None
        record.status = "completed"
        record.result = result
        record.completed_at = datetime.utcnow()
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def fail_session(
        self, session: AsyncSession, session_id: int, error: str
    ) -> dict:
        record = await session.get(AutoWorkSession, session_id)
        if not record:
            return None
        record.status = "failed"
        record.result = error
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def pause_session(
        self, session: AsyncSession, session_id: int
    ) -> dict:
        record = await session.get(AutoWorkSession, session_id)
        if not record:
            return None
        record.status = "paused"
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def resume_session(
        self, session: AsyncSession, session_id: int
    ) -> dict:
        record = await session.get(AutoWorkSession, session_id)
        if not record:
            return None
        record.status = "running"
        await session.commit()
        await session.refresh(record)
        return _session_to_dict(record)

    async def get_kanban(self, session: AsyncSession) -> dict:
        """按状态分组统计,返回看板视图数据"""
        stmt = select(AutoWorkSession).order_by(
            AutoWorkSession.priority.desc(), AutoWorkSession.created_at.desc()
        )
        result = await session.execute(stmt)
        all_sessions = [_session_to_dict(s) for s in result.scalars().all()]

        groups: dict[str, list[dict]] = {
            "pending": [],
            "running": [],
            "paused": [],
            "completed": [],
            "failed": [],
        }
        for s in all_sessions:
            groups.setdefault(s["status"], []).append(s)

        return {
            "groups": {
                "pending": groups["pending"],
                "running": groups["running"],
                "completed": groups["completed"],
            },
            "counts": {
                status: len(items) for status, items in groups.items()
            },
            "total": len(all_sessions),
        }

    async def send_notification(
        self, channel: str, message: str
    ) -> dict:
        """mock 通知发送,不实际调用外部服务"""
        return {
            "ok": True,
            "mock": True,
            "channel": channel,
            "message": message,
        }
