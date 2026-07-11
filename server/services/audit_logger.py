"""审计日志服务(Phase 6D)

记录所有 LLM 调用 / 工具调用 / 技能执行 / 进化 / 循环等动作,
用于预算控制数据源、合规审计与运营分析。

融合来源:
- awesome-llm-apps 的审计日志模式
- Nebula 的审计日志设计
"""

from datetime import datetime

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import AuditLog


# 简单定价表(美元 / 1k tokens),仅用于估算
_PRICING_TABLE = {
    ("openai", "gpt-4o"): 0.03,
    ("openai", "gpt-4o-mini"): 0.005,
    ("openai", "gpt-4"): 0.06,
    ("openai", "gpt-3.5-turbo"): 0.002,
    ("anthropic", "claude-3-opus"): 0.015,
    ("anthropic", "claude-3-sonnet"): 0.003,
    ("anthropic", "claude-3-haiku"): 0.00025,
    ("anthropic", "claude-3"): 0.02,
    ("google", "gemini-1.5-pro"): 0.0035,
    ("google", "gemini-1.5-flash"): 0.000075,
}
_DEFAULT_PRICE = 0.01  # 未知模型默认 $0.01 / 1k tokens


def _log_to_dict(log: AuditLog) -> dict:
    """ORM 转 dict"""
    return {
        "id": log.id,
        "persona_id": log.persona_id,
        "action": log.action,
        "resource": log.resource,
        "input_summary": log.input_summary,
        "output_summary": log.output_summary,
        "token_count": log.token_count,
        "cost": log.cost,
        "duration_ms": log.duration_ms,
        "success": bool(log.success),
        "details": log.details,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _parse_date(s: str | None) -> datetime | None:
    """解析 ISO 格式日期字符串,失败返回 None"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


class AuditLogger:
    """审计日志记录器"""

    def _estimate_cost(self, provider: str | None, model: str | None, token_count: int) -> float:
        """根据定价表估算成本(美元)

        - 命中精确 (provider, model): 使用对应价格
        - 否则: 使用 _DEFAULT_PRICE
        """
        if not token_count or token_count <= 0:
            return 0.0
        provider = (provider or "").lower()
        model = (model or "").lower()
        price = _PRICING_TABLE.get((provider, model), _DEFAULT_PRICE)
        return round(token_count / 1000.0 * price, 6)

    async def log(
        self,
        session: AsyncSession,
        action: str,
        persona_id: int | None = None,
        resource: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        token_count: int = 0,
        cost: float = 0.0,
        duration_ms: int = 0,
        success: bool = True,
        details: dict | None = None,
    ) -> dict:
        """记录一条审计日志"""
        log = AuditLog(
            persona_id=persona_id,
            action=action,
            resource=resource,
            input_summary=input_summary,
            output_summary=output_summary,
            token_count=token_count,
            cost=cost,
            duration_ms=duration_ms,
            success=success,
            details=details or {},
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return _log_to_dict(log)

    async def log_llm_call(
        self,
        session: AsyncSession,
        persona_id: int | None,
        provider: str,
        model: str,
        input_text: str,
        output_text: str,
        token_count: int,
        duration_ms: int,
        success: bool = True,
    ) -> dict:
        """便捷方法: 记录 LLM 调用

        - action="llm_call"
        - resource=f"{provider}/{model}"
        - cost 通过 _estimate_cost 估算
        - input/output summary 截断到 500 字符
        """
        cost = self._estimate_cost(provider, model, token_count)
        input_summary = (input_text or "")[:500]
        output_summary = (output_text or "")[:500]
        details = {"provider": provider, "model": model}
        return await self.log(
            session,
            action="llm_call",
            persona_id=persona_id,
            resource=f"{provider}/{model}",
            input_summary=input_summary,
            output_summary=output_summary,
            token_count=token_count,
            cost=cost,
            duration_ms=duration_ms,
            success=success,
            details=details,
        )

    async def list_logs(
        self,
        session: AsyncSession,
        persona_id: int | None = None,
        action: str | None = None,
        resource: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询审计日志(多维度过滤 + 分页)

        返回 {"logs": [...], "total": int, "page": int, "page_size": int}
        """
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if persona_id is not None:
            stmt = stmt.where(AuditLog.persona_id == persona_id)
            count_stmt = count_stmt.where(AuditLog.persona_id == persona_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if resource:
            stmt = stmt.where(AuditLog.resource == resource)
            count_stmt = count_stmt.where(AuditLog.resource == resource)

        start_dt = _parse_date(start_date)
        if start_dt is not None:
            stmt = stmt.where(AuditLog.created_at >= start_dt)
            count_stmt = count_stmt.where(AuditLog.created_at >= start_dt)

        end_dt = _parse_date(end_date)
        if end_dt is not None:
            stmt = stmt.where(AuditLog.created_at <= end_dt)
            count_stmt = count_stmt.where(AuditLog.created_at <= end_dt)

        total = (await session.execute(count_stmt)).scalar_one()

        page = max(page, 1)
        page_size = max(page_size, 1)
        stmt = (
            stmt.order_by(desc(AuditLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(stmt)).scalars().all()

        return {
            "logs": [_log_to_dict(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def get_log(self, session: AsyncSession, log_id: int) -> dict | None:
        """获取单条审计日志"""
        log = await session.get(AuditLog, log_id)
        return _log_to_dict(log) if log else None

    async def get_summary(
        self,
        session: AsyncSession,
        persona_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """获取审计摘要

        汇总: 总记录数, 总token, 总cost, 总duration, 按 action 分组统计
        """
        base = select(AuditLog)
        if persona_id is not None:
            base = base.where(AuditLog.persona_id == persona_id)

        start_dt = _parse_date(start_date)
        if start_dt is not None:
            base = base.where(AuditLog.created_at >= start_dt)
        end_dt = _parse_date(end_date)
        if end_dt is not None:
            base = base.where(AuditLog.created_at <= end_dt)

        # 总体汇总
        total_stmt = select(
            func.count(AuditLog.id).label("total_records"),
            func.coalesce(func.sum(AuditLog.token_count), 0).label("total_tokens"),
            func.coalesce(func.sum(AuditLog.cost), 0.0).label("total_cost"),
            func.coalesce(func.sum(AuditLog.duration_ms), 0).label("total_duration_ms"),
        )
        if persona_id is not None:
            total_stmt = total_stmt.where(AuditLog.persona_id == persona_id)
        if start_dt is not None:
            total_stmt = total_stmt.where(AuditLog.created_at >= start_dt)
        if end_dt is not None:
            total_stmt = total_stmt.where(AuditLog.created_at <= end_dt)

        total_row = (await session.execute(total_stmt)).one()

        # 按 action 分组统计
        group_stmt = (
            select(
                AuditLog.action,
                func.count(AuditLog.id).label("records"),
                func.coalesce(func.sum(AuditLog.token_count), 0).label("tokens"),
                func.coalesce(func.sum(AuditLog.cost), 0.0).label("cost"),
                func.coalesce(func.sum(AuditLog.duration_ms), 0).label("duration_ms"),
            )
            .group_by(AuditLog.action)
        )
        if persona_id is not None:
            group_stmt = group_stmt.where(AuditLog.persona_id == persona_id)
        if start_dt is not None:
            group_stmt = group_stmt.where(AuditLog.created_at >= start_dt)
        if end_dt is not None:
            group_stmt = group_stmt.where(AuditLog.created_at <= end_dt)

        group_rows = (await session.execute(group_stmt)).all()

        by_action: dict[str, dict] = {}
        for row in group_rows:
            by_action[row.action] = {
                "records": int(row.records or 0),
                "tokens": int(row.tokens or 0),
                "cost": float(row.cost or 0.0),
                "duration_ms": int(row.duration_ms or 0),
            }

        return {
            "total_records": int(total_row.total_records or 0),
            "total_tokens": int(total_row.total_tokens or 0),
            "total_cost": float(total_row.total_cost or 0.0),
            "total_duration_ms": int(total_row.total_duration_ms or 0),
            "by_action": by_action,
        }

    async def delete_log(self, session: AsyncSession, log_id: int) -> bool:
        """删除审计日志"""
        log = await session.get(AuditLog, log_id)
        if not log:
            return False
        await session.delete(log)
        await session.commit()
        return True


# 模块级单例
audit_logger = AuditLogger()
