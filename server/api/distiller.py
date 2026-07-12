"""自进化技能蒸馏 API 端点(Phase 5C)"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, desc, func

from ..db.engine import async_session
from ..db.orm import TaskRecord as TaskRecordORM
from .models import (
    DistillCheckRequest,
    DistillConfirmRequest,
    TaskRecordCreate,
)
from ..services.distiller import SkillDistiller

router = APIRouter(prefix="/distiller", tags=["distiller"])

# 蒸馏器单例(默认使用 openai provider)
_distiller = SkillDistiller()


def _record_to_dict(r: TaskRecordORM) -> dict:
    return {
        "id": r.id,
        "task_type": r.task_type,
        "description": r.description,
        "inputs": r.inputs,
        "output": r.output,
        "success": bool(r.success),
        "iterations": r.iterations,
        "persona_id": r.persona_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/check", summary="检查并触发蒸馏", description="检查并触发蒸馏:连续3次同类任务成功/失败时触发")
async def check_distill(req: DistillCheckRequest):
    """检查并触发蒸馏:连续3次同类任务成功/失败时触发"""
    try:
        result = await _distiller.check_and_distill(req.task_type, req.persona_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"蒸馏检查失败: {e}"},
        )

    if result is None:
        return {
            "ok": True,
            "data": {"triggered": False, "reason": "未达到蒸馏阈值"},
            "error": None,
        }

    return {
        "ok": True,
        "data": {
            "triggered": True,
            "success": result.success,
            "skill_name": result.skill_name,
            "skill_content": result.skill_content,
            "lesson": result.lesson,
            "reason": result.reason,
        },
        "error": None,
    }


@router.post("/confirm", summary="确认蒸馏结果", description="人工确认蒸馏结果,将技能写入 data/skills/{skill_name}.md")
async def confirm_distill(req: DistillConfirmRequest):
    """人工确认蒸馏结果,将技能写入 data/skills/{skill_name}.md"""
    try:
        write_result = await _distiller.confirm_distillation(req.skill_content, req.skill_name)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"技能写入失败: {e}"},
        )

    if not write_result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": write_result.get("error")},
        )

    return {"ok": True, "data": write_result, "error": None}


@router.get("/records", summary="列出任务记录", description="获取任务记录列表,支持按任务类型和 Persona 过滤并分页")
async def list_records(
    task_type: str | None = Query(None, description="按任务类型过滤"),
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
    page: int = Query(1, ge=1, description="页码,从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取任务记录列表,支持分页与过滤"""
    async with async_session() as session:
        stmt = select(TaskRecordORM)
        count_stmt = select(func.count()).select_from(TaskRecordORM)

        if task_type:
            stmt = stmt.where(TaskRecordORM.task_type == task_type)
            count_stmt = count_stmt.where(TaskRecordORM.task_type == task_type)
        if persona_id is not None:
            stmt = stmt.where(TaskRecordORM.persona_id == persona_id)
            count_stmt = count_stmt.where(TaskRecordORM.persona_id == persona_id)

        total = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(desc(TaskRecordORM.created_at)).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()

    return {
        "ok": True,
        "data": {
            "items": [_record_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "error": None,
    }


@router.post("/records", summary="记录任务", description="记录新任务到任务记录表 (供蒸馏引擎分析成功/失败模式)")
async def create_record(req: TaskRecordCreate):
    """记录新任务(供其他模块调用)"""
    async with async_session() as session:
        record = TaskRecordORM(
            task_type=req.task_type,
            description=req.description,
            inputs=req.inputs,
            output=req.output,
            success=req.success,
            iterations=req.iterations,
            persona_id=req.persona_id,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

    return {"ok": True, "data": _record_to_dict(record), "error": None}
