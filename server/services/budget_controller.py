"""预算控制器(Phase 6D)

融合 awesome-llm-apps 的预算控制模式与 Nebula 的审计日志设计:
- 维度: Token / 时间(秒) / 金额(美元)
- 周期: daily / weekly / monthly
- 超限动作: stop(停止) / degrade(降级) / warn(警告)
- 数据源: 通过 AuditLog 表汇总当前周期用量
"""

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import BudgetConfig, AuditLog


# 默认预算配置(未显式配置时使用)
_DEFAULT_CONFIG = {
    "token_limit": 100000,
    "time_limit_seconds": 3600,
    "cost_limit": 10.0,
    "period": "daily",
    "action_on_exceed": "stop",
    "enabled": True,
}


def _config_to_dict(config: BudgetConfig | None) -> dict:
    """ORM 转 dict;config 为 None 时返回默认配置"""
    if config is None:
        return {
            "id": None,
            "persona_id": None,
            **_DEFAULT_CONFIG,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": config.id,
        "persona_id": config.persona_id,
        "token_limit": config.token_limit,
        "time_limit_seconds": config.time_limit_seconds,
        "cost_limit": config.cost_limit,
        "period": config.period,
        "action_on_exceed": config.action_on_exceed,
        "enabled": bool(config.enabled),
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


class BudgetController:
    """预算控制器:基于 AuditLog 汇总当前周期用量,判断是否超限"""

    def _get_period_start(self, period: str) -> datetime:
        """获取周期起始时间

        - daily: 当天 00:00:00
        - weekly: 本周一 00:00:00
        - monthly: 本月 1 号 00:00:00
        未知 period 视为 daily
        """
        now = datetime.utcnow()
        period = (period or "daily").lower()
        if period == "weekly":
            # weekday(): 周一=0 ... 周日=6
            start = now - timedelta(days=now.weekday())
            return start.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "monthly":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # daily / fallback
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def get_config(self, session: AsyncSession, persona_id: int | None) -> dict:
        """获取预算配置

        - persona_id 为 None: 返回全局配置(persona_id IS NULL)
        - persona_id 有值但无配置: 返回默认配置
        """
        stmt = select(BudgetConfig)
        if persona_id is None:
            stmt = stmt.where(BudgetConfig.persona_id.is_(None))
        else:
            stmt = stmt.where(BudgetConfig.persona_id == persona_id)
        result = await session.execute(stmt)
        config = result.scalars().first()
        return _config_to_dict(config)

    async def set_config(
        self, session: AsyncSession, persona_id: int | None, **kwargs
    ) -> dict:
        """设置/更新预算配置;不存在则新建"""
        stmt = select(BudgetConfig)
        if persona_id is None:
            stmt = stmt.where(BudgetConfig.persona_id.is_(None))
        else:
            stmt = stmt.where(BudgetConfig.persona_id == persona_id)
        result = await session.execute(stmt)
        config = result.scalars().first()

        if config is None:
            # 新建: 以 kwargs 为准,缺失字段用默认值补齐
            data = {"persona_id": persona_id, **_DEFAULT_CONFIG}
            data.update(kwargs)
            # 移除 id/created_at/updated_at 等非字段项
            data.pop("id", None)
            data.pop("created_at", None)
            data.pop("updated_at", None)
            config = BudgetConfig(**data)
            session.add(config)
        else:
            for key, value in kwargs.items():
                if value is None:
                    continue
                if hasattr(config, key):
                    setattr(config, key, value)

        await session.commit()
        await session.refresh(config)
        return _config_to_dict(config)

    async def get_usage(
        self, session: AsyncSession, persona_id: int | None, period: str = "daily"
    ) -> dict:
        """获取当前周期用量

        汇总当前周期内的 AuditLog: token_count, duration_ms(转秒), cost
        """
        period = period or "daily"
        start = self._get_period_start(period)

        stmt = select(
            func.coalesce(func.sum(AuditLog.token_count), 0).label("tokens"),
            func.coalesce(func.sum(AuditLog.duration_ms), 0).label("duration_ms"),
            func.coalesce(func.sum(AuditLog.cost), 0.0).label("cost"),
            func.count(AuditLog.id).label("records"),
        ).where(AuditLog.created_at >= start)

        if persona_id is None:
            stmt = stmt.where(AuditLog.persona_id.is_(None))
        else:
            stmt = stmt.where(AuditLog.persona_id == persona_id)

        row = (await session.execute(stmt)).one()
        return {
            "tokens": int(row.tokens or 0),
            "time_seconds": int((row.duration_ms or 0) // 1000),
            "cost": float(row.cost or 0.0),
            "period": period,
            "records": int(row.records or 0),
        }

    async def check_budget(
        self,
        session: AsyncSession,
        persona_id: int | None,
        tokens_to_add: int = 0,
        time_seconds_to_add: int = 0,
        cost_to_add: float = 0.0,
    ) -> dict:
        """检查预算

        获取当前周期用量 + 待添加量,判断是否超限
        """
        config = await self.get_config(session, persona_id)

        # 未启用预算控制: 直接返回不超限
        if not config.get("enabled", True):
            return {
                "exceeded": False,
                "exceeded_dimensions": [],
                "current": {"tokens": 0, "time_seconds": 0, "cost": 0.0},
                "limits": {
                    "tokens": config.get("token_limit", 0),
                    "time_seconds": config.get("time_limit_seconds", 0),
                    "cost": config.get("cost_limit", 0.0),
                },
                "action": config.get("action_on_exceed", "stop"),
                "message": "预算控制未启用",
            }

        period = config.get("period", "daily")
        usage = await self.get_usage(session, persona_id, period)

        current_tokens = usage["tokens"] + tokens_to_add
        current_time = usage["time_seconds"] + time_seconds_to_add
        current_cost = round(usage["cost"] + cost_to_add, 6)

        limit_tokens = config.get("token_limit", 0)
        limit_time = config.get("time_limit_seconds", 0)
        limit_cost = config.get("cost_limit", 0.0)

        exceeded_dimensions: list[str] = []
        if limit_tokens > 0 and current_tokens > limit_tokens:
            exceeded_dimensions.append("tokens")
        if limit_time > 0 and current_time > limit_time:
            exceeded_dimensions.append("time")
        if limit_cost > 0 and current_cost > limit_cost:
            exceeded_dimensions.append("cost")

        exceeded = len(exceeded_dimensions) > 0
        action = config.get("action_on_exceed", "stop")

        if exceeded:
            message = (
                f"预算超限(persona_id={persona_id}, period={period}): "
                f"超限维度={exceeded_dimensions}, "
                f"当前 tokens={current_tokens}/{limit_tokens}, "
                f"time={current_time}s/{limit_time}s, "
                f"cost=${current_cost:.4f}/${limit_cost:.4f}, "
                f"动作={action}"
            )
        else:
            message = "预算正常"

        return {
            "exceeded": exceeded,
            "exceeded_dimensions": exceeded_dimensions,
            "current": {
                "tokens": current_tokens,
                "time_seconds": current_time,
                "cost": current_cost,
            },
            "limits": {
                "tokens": limit_tokens,
                "time_seconds": limit_time,
                "cost": limit_cost,
            },
            "action": action,
            "message": message,
        }

    async def should_stop(
        self,
        session: AsyncSession,
        persona_id: int | None,
        tokens_to_add: int = 0,
        time_seconds_to_add: int = 0,
        cost_to_add: float = 0.0,
    ) -> tuple[bool, str]:
        """判断是否应当停止执行

        返回 (should_stop, reason):
        - action_on_exceed=="stop" 且超限: (True, reason)
        - action_on_exceed=="degrade" 且超限: (False, "degrade")
        - action_on_exceed=="warn" 且超限: (False, "warn")
        - 未超限: (False, "ok")
        """
        result = await self.check_budget(
            session, persona_id, tokens_to_add, time_seconds_to_add, cost_to_add
        )

        if not result["exceeded"]:
            return (False, "ok")

        action = result.get("action", "stop")
        if action == "stop":
            return (True, result.get("message", "budget exceeded (stop)"))
        if action == "degrade":
            return (False, "degrade")
        if action == "warn":
            return (False, "warn")
        # 未知动作,保守起见停止
        return (True, result.get("message", "budget exceeded (unknown action)"))


# 模块级单例
budget_controller = BudgetController()
