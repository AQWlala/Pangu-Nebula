"""审计日志 + 预算控制 API(Phase 6D)

端点总览:
- 审计日志: GET/POST /audit/logs, GET/DELETE /audit/logs/{log_id}, GET /audit/summary
- 预算控制: GET/POST/PUT /audit/budget, POST /audit/budget/check, GET /audit/budget/usage
"""

from fastapi import APIRouter, HTTPException, Query

from ..db.engine import async_session
from ..services.audit_logger import audit_logger
from ..services.budget_controller import budget_controller
from .models import (
    AuditLogCreate,
    BudgetCheckRequest,
    BudgetConfigCreate,
    BudgetConfigUpdate,
)

router = APIRouter(prefix="/audit", tags=["audit"])


# ===== 审计日志端点 =====


@router.get("/logs")
async def list_logs(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
    action: str | None = Query(None, description="按动作过滤(llm_call/tool_call/...)"),
    resource: str | None = Query(None, description="按资源过滤(provider/model/tool)"),
    start_date: str | None = Query(None, description="起始日期(ISO 格式)"),
    end_date: str | None = Query(None, description="结束日期(ISO 格式)"),
    page: int = Query(1, ge=1, description="页码,从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """查询审计日志(多维度过滤 + 分页)"""
    async with async_session() as session:
        data = await audit_logger.list_logs(
            session,
            persona_id=persona_id,
            action=action,
            resource=resource,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/logs")
async def create_log(req: AuditLogCreate):
    """手动记录审计日志(供其他模块调用)"""
    async with async_session() as session:
        data = await audit_logger.log(
            session,
            action=req.action,
            persona_id=req.persona_id,
            resource=req.resource,
            input_summary=req.input_summary,
            output_summary=req.output_summary,
            token_count=req.token_count,
            cost=req.cost,
            duration_ms=req.duration_ms,
            success=req.success,
            details=req.details,
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/logs/{log_id}")
async def get_log(log_id: int):
    """获取单条审计日志"""
    async with async_session() as session:
        data = await audit_logger.get_log(session, log_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Audit log not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/logs/{log_id}")
async def delete_log(log_id: int):
    """删除审计日志"""
    async with async_session() as session:
        deleted = await audit_logger.delete_log(session, log_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Audit log not found"},
        )
    return {"ok": True, "data": {"id": log_id, "deleted": True}, "error": None}


@router.get("/summary")
async def get_summary(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
    start_date: str | None = Query(None, description="起始日期(ISO 格式)"),
    end_date: str | None = Query(None, description="结束日期(ISO 格式)"),
):
    """获取审计摘要:总记录数/总token/总cost/总duration/按action分组"""
    async with async_session() as session:
        data = await audit_logger.get_summary(
            session,
            persona_id=persona_id,
            start_date=start_date,
            end_date=end_date,
        )
    return {"ok": True, "data": data, "error": None}


# ===== 预算控制端点 =====


@router.get("/budget")
async def get_budget(
    persona_id: int | None = Query(None, description="Persona ID,为空则获取全局配置"),
):
    """获取预算配置"""
    async with async_session() as session:
        data = await budget_controller.get_config(session, persona_id)
    return {"ok": True, "data": data, "error": None}


@router.post("/budget")
async def create_budget(req: BudgetConfigCreate):
    """设置预算配置(不存在则新建,存在则更新)"""
    async with async_session() as session:
        data = await budget_controller.set_config(
            session,
            persona_id=req.persona_id,
            token_limit=req.token_limit,
            time_limit_seconds=req.time_limit_seconds,
            cost_limit=req.cost_limit,
            period=req.period,
            action_on_exceed=req.action_on_exceed,
            enabled=req.enabled,
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/budget")
async def update_budget(
    req: BudgetConfigUpdate,
    persona_id: int | None = Query(None, description="Persona ID,为空则更新全局配置"),
):
    """更新预算配置(仅更新提供的字段)"""
    async with async_session() as session:
        data = await budget_controller.set_config(
            session,
            persona_id=persona_id,
            **req.model_dump(exclude_unset=True),
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/budget/check")
async def check_budget(req: BudgetCheckRequest):
    """检查预算是否超限"""
    async with async_session() as session:
        data = await budget_controller.check_budget(
            session,
            persona_id=req.persona_id,
            tokens_to_add=req.tokens_to_add,
            time_seconds_to_add=req.time_seconds_to_add,
            cost_to_add=req.cost_to_add,
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/budget/usage")
async def get_budget_usage(
    persona_id: int | None = Query(None, description="Persona ID,为空则查询全局用量"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
):
    """获取当前周期用量"""
    async with async_session() as session:
        data = await budget_controller.get_usage(session, persona_id, period)
    return {"ok": True, "data": data, "error": None}
