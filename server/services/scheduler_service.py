"""定时任务调度器服务(Phase 10B)

基于 APScheduler 实现定时任务调度。APScheduler 为可选依赖:
- 已安装: 任务可注册到 APScheduler,按 cron 表达式自动触发
- 未安装: DB 操作仍可正常进行,但无法自动触发(只能手动 trigger)

action 格式:
    {
        "type": "llm_call" | "tool_call" | "skill_exec" | "api_call",
        "target": "...",
        "params": {...}
    }

cron 表达式: 标准 5 字段格式 "分 时 日 月 周"(如 "*/5 * * * *")
"""

from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import async_session
from ..db.orm import SchedulerJob

# APScheduler 为可选依赖
try:  # noqa: SIM105
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    _APSCHEDULER_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖可选
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]
    _APSCHEDULER_AVAILABLE = False


# 任务执行历史最大保留条数(每个任务)
_HISTORY_MAX = 100


def _job_to_dict(job: SchedulerJob) -> dict:
    """ORM 转 dict"""
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "action": job.action,
        "enabled": bool(job.enabled),
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


class SchedulerService:
    """定时任务调度器(模块级单例)"""

    def __init__(self) -> None:
        self._scheduler: "AsyncIOScheduler | None" = None
        # job_id -> list[{timestamp, success, result, error, duration_ms}]
        self._history: dict[int, list[dict]] = {}

    # ===== 可用性 =====

    @staticmethod
    def is_available() -> bool:
        """APScheduler 是否可用"""
        return _APSCHEDULER_AVAILABLE

    # ===== 调度器生命周期 =====

    async def start(self) -> dict:
        """启动调度器(APScheduler 可用时)"""
        if not _APSCHEDULER_AVAILABLE:
            return {"running": False, "available": False}
        if self._scheduler is not None and self._scheduler.running:
            return {"running": True, "available": True}
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        # 启动时从 DB 加载所有 enabled 的任务
        await self._reload_jobs_from_db()
        return {"running": True, "available": True}

    async def stop(self) -> dict:
        """停止调度器"""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler = None
        return {"running": False, "available": _APSCHEDULER_AVAILABLE}

    def get_status(self) -> dict:
        """获取调度器状态"""
        running = False
        if self._scheduler is not None and self._scheduler.running:
            running = True
        return {"running": running, "available": _APSCHEDULER_AVAILABLE}

    # ===== 任务 CRUD =====

    async def add_job(
        self,
        name: str,
        cron_expr: str,
        action: dict,
        enabled: bool = True,
    ) -> dict:
        """添加定时任务

        - 保存到 SchedulerJob 表
        - 若 enabled 且 APScheduler 可用,注册到调度器
        """
        # 校验 cron 表达式(解析失败抛出 ValueError)
        cron_kwargs = self._parse_cron(cron_expr)

        async with async_session() as session:
            job = SchedulerJob(
                name=name,
                cron_expr=cron_expr,
                action=action,
                enabled=enabled,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            data = _job_to_dict(job)

        if enabled and _APSCHEDULER_AVAILABLE and self._scheduler is not None:
            self._register_apscheduler(job.id, cron_kwargs, action)

        return data

    async def remove_job(self, job_id: int) -> bool:
        """移除任务(从 DB 和 APScheduler)"""
        async with async_session() as session:
            job = await session.get(SchedulerJob, job_id)
            if job is None:
                return False
            await session.delete(job)
            await session.commit()

        # 从 APScheduler 移除
        if _APSCHEDULER_AVAILABLE and self._scheduler is not None:
            try:
                self._scheduler.remove_job(self._aps_job_id(job_id))
            except Exception:  # noqa: BLE001
                # APScheduler 中不存在该任务,忽略
                pass

        # 清理历史
        self._history.pop(job_id, None)
        return True

    async def update_job(self, job_id: int, **kwargs) -> dict | None:
        """更新任务(name, cron_expr, action, enabled)

        仅更新提供的字段。若 cron_expr 或 action 变更且任务 enabled,
        重新注册到 APScheduler。
        """
        async with async_session() as session:
            job = await session.get(SchedulerJob, job_id)
            if job is None:
                return None

            cron_changed = False
            action_changed = False
            for key, value in kwargs.items():
                if value is None:
                    continue
                if key == "cron_expr":
                    # 校验新 cron 表达式
                    self._parse_cron(value)
                    cron_changed = True
                if key == "action":
                    action_changed = True
                if hasattr(job, key):
                    setattr(job, key, value)
            await session.commit()
            await session.refresh(job)
            data = _job_to_dict(job)

        # 重新注册到 APScheduler
        if _APSCHEDULER_AVAILABLE and self._scheduler is not None:
            if job.enabled and (cron_changed or action_changed):
                # 先移除旧的,再注册新的
                try:
                    self._scheduler.remove_job(self._aps_job_id(job_id))
                except Exception:  # noqa: BLE001
                    pass
                cron_kwargs = self._parse_cron(job.cron_expr)
                self._register_apscheduler(job.id, cron_kwargs, job.action or {})
            elif not job.enabled:
                # 禁用:从 APScheduler 移除
                try:
                    self._scheduler.remove_job(self._aps_job_id(job_id))
                except Exception:  # noqa: BLE001
                    pass

        return data

    async def list_jobs(self) -> list[dict]:
        """列出所有任务(从 DB)"""
        async with async_session() as session:
            stmt = select(SchedulerJob).order_by(desc(SchedulerJob.created_at))
            rows = (await session.execute(stmt)).scalars().all()
            return [_job_to_dict(r) for r in rows]

    async def get_job(self, job_id: int) -> dict | None:
        """获取单个任务"""
        async with async_session() as session:
            job = await session.get(SchedulerJob, job_id)
            return _job_to_dict(job) if job else None

    async def trigger_job(self, job_id: int) -> dict | None:
        """手动触发任务(立即执行一次)

        返回执行结果 {job_id, action, result, error, ...}
        """
        async with async_session() as session:
            job = await session.get(SchedulerJob, job_id)
            if job is None:
                return None
            action = job.action or {}

        result = await self._execute_job(action)
        # 记录历史
        self._append_history(job_id, result)
        return {"job_id": job_id, "action": action, **result}

    # ===== 任务执行历史 =====

    def get_job_history(self, job_id: int, limit: int = 20) -> list[dict]:
        """获取任务执行历史(按时间倒序,最多 limit 条)"""
        history = self._history.get(job_id, [])
        limit = max(limit, 1)
        return list(reversed(history[-limit:]))

    # ===== 内部方法 =====

    @staticmethod
    def _aps_job_id(job_id: int) -> str:
        """APScheduler 中任务的 ID(DB job_id 转字符串)"""
        return f"scheduler_job_{job_id}"

    def _register_apscheduler(
        self, job_id: int, cron_kwargs: dict, action: dict
    ) -> None:
        """注册任务到 APScheduler"""
        if not _APSCHEDULER_AVAILABLE or self._scheduler is None:
            return
        trigger = CronTrigger(**cron_kwargs)
        self._scheduler.add_job(
            self._scheduled_execute,
            trigger=trigger,
            id=self._aps_job_id(job_id),
            args=[job_id, action],
            replace_existing=True,
        )

    async def _scheduled_execute(self, job_id: int, action: dict) -> None:
        """APScheduler 调度触发的执行入口"""
        result = await self._execute_job(action)
        self._append_history(job_id, result)

    async def _reload_jobs_from_db(self) -> None:
        """从 DB 加载所有 enabled 任务到 APScheduler"""
        if not _APSCHEDULER_AVAILABLE or self._scheduler is None:
            return
        async with async_session() as session:
            stmt = select(SchedulerJob).where(SchedulerJob.enabled == True)  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            for job in rows:
                try:
                    cron_kwargs = self._parse_cron(job.cron_expr)
                except ValueError:
                    # 无效 cron 表达式,跳过
                    continue
                self._register_apscheduler(job.id, cron_kwargs, job.action or {})

    async def _execute_job(self, action: dict) -> dict:
        """执行任务(根据 action.type 分发)

        返回 {success, result, error, duration_ms, timestamp}
        """
        start = datetime.utcnow()
        action_type = (action or {}).get("type", "")
        target = (action or {}).get("target", "")
        params = (action or {}).get("params", {}) or {}

        success = False
        result: any = None
        error: str | None = None

        try:
            if action_type == "llm_call":
                result = await self._exec_llm_call(target, params)
                success = True
            elif action_type == "tool_call":
                result = await self._exec_tool_call(target, params)
                success = True
            elif action_type == "skill_exec":
                result = await self._exec_skill_exec(target, params)
                success = True
            elif action_type == "api_call":
                result = await self._exec_api_call(target, params)
                success = True
            else:
                error = f"Unknown action type: {action_type}"
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

        duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        return {
            "success": success,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _exec_llm_call(self, target: str, params: dict) -> str:
        """执行 LLM 调用: target 为 provider 名称

        params 可包含: model, messages, **kwargs
        """
        from ..providers.registry import get_provider  # 延迟导入

        provider = get_provider(target)
        model = params.get("model", "gpt-4o")
        messages = params.get("messages", [])
        # generate 是 AsyncIterator[str],收集所有 chunk
        chunks: list[str] = []
        async for chunk in provider.generate(messages=messages, model=model, **params.get("kwargs", {})):
            chunks.append(chunk)
        return "".join(chunks)

    async def _exec_tool_call(self, target: str, params: dict) -> any:
        """执行工具调用: target 为工具名称"""
        from ..tools.registry import get_tool  # 延迟导入

        tool = get_tool(target)
        result = await tool.execute(**params)
        # ToolResult 有 success/output/error 字段
        if hasattr(result, "output"):
            return {"success": result.success, "output": result.output, "error": result.error}
        return result

    async def _exec_skill_exec(self, target: str, params: dict) -> any:
        """执行技能: target 为技能名称

        延迟导入技能服务。
        """
        try:
            from ..services.skill_loader import SkillLoader
            from ..services.skill_engine import PromptSkillEngine
        except ImportError as exc:
            raise RuntimeError(f"Skill service unavailable: {exc}")

        loader = SkillLoader()
        engine = PromptSkillEngine(loader)
        variables = params.get("variables", {})
        result = await engine.execute(target, variables)
        return result

    async def _exec_api_call(self, target: str, params: str) -> any:
        """执行 API 调用: target 为 URL

        params 可包含: method, headers, json, timeout
        """
        import httpx  # 延迟导入

        method = (params.get("method") or "GET").upper()
        headers = params.get("headers") or {}
        json_body = params.get("json")
        timeout = params.get("timeout", 30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(target, headers=headers)
            elif method == "POST":
                resp = await client.post(target, headers=headers, json=json_body)
            elif method == "PUT":
                resp = await client.put(target, headers=headers, json=json_body)
            elif method == "DELETE":
                resp = await client.delete(target, headers=headers)
            else:
                resp = await client.request(method, target, headers=headers, json=json_body)
        try:
            return {"status_code": resp.status_code, "body": resp.json()}
        except ValueError:
            return {"status_code": resp.status_code, "body": resp.text}

    def _append_history(self, job_id: int, result: dict) -> None:
        """追加执行历史,限制最大条数"""
        hist = self._history.setdefault(job_id, [])
        hist.append(result)
        if len(hist) > _HISTORY_MAX:
            self._history[job_id] = hist[-_HISTORY_MAX:]

    @staticmethod
    def _parse_cron(cron_expr: str) -> dict:
        """解析 cron 表达式为 APScheduler CronTrigger 参数

        支持 5 字段格式: "分 时 日 月 周"(如 "*/5 * * * *")
        返回 dict: {minute, hour, day, month, day_of_week}

        无效表达式抛出 ValueError。
        """
        if not cron_expr or not cron_expr.strip():
            raise ValueError("Empty cron expression")

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression '{cron_expr}': expected 5 fields (minute hour day month day_of_week), got {len(parts)}"
            )

        minute, hour, day, month, day_of_week = parts
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }


# 模块级单例
scheduler_service = SchedulerService()
