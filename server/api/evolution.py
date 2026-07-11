"""进化引擎 API 端点(Phase 6B)"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db.engine import async_session
from ..services.evolution_engine import EvolutionEngine
from .models import EvolutionTriggerRequest

router = APIRouter(prefix="/evolution", tags=["evolution"])

# 进化引擎单例
_engine = EvolutionEngine()


class ConfirmSoulRequest(BaseModel):
    """确认 SOUL.md 更新请求"""

    persona_id: int
    log_id: int


@router.post("/trigger")
async def trigger_evolution(req: EvolutionTriggerRequest):
    """触发进化管道"""
    try:
        logs = await _engine.run_pipeline(req.persona_id, req.phases, req.trigger)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"进化管道执行失败: {e}"},
        )

    return {"ok": True, "data": {"logs": logs}, "error": None}


@router.get("/logs")
async def list_logs(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
    phase: str | None = Query(None, description="按阶段过滤(extract/compile/reflect/soul)"),
    limit: int = Query(20, ge=1, le=100, description="返回条数上限"),
):
    """查询进化日志"""
    async with async_session() as session:
        logs = await _engine.list_logs(
            session, persona_id=persona_id, phase=phase, limit=limit
        )
    return {"ok": True, "data": {"items": logs, "count": len(logs)}, "error": None}


@router.get("/logs/{log_id}")
async def get_log(log_id: int):
    """获取单个进化日志"""
    async with async_session() as session:
        log = await _engine.get_log(session, log_id)
    if log is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "EvolutionLog not found"},
        )
    return {"ok": True, "data": log, "error": None}


@router.post("/confirm-soul")
async def confirm_soul(req: ConfirmSoulRequest):
    """确认 SOUL.md 更新:将 soul 阶段生成的新 SOUL.md 写入 Persona.system_prompt"""
    async with async_session() as session:
        persona = await _engine.confirm_soul(session, req.persona_id, req.log_id)
    if persona is None:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "data": None,
                "error": "未找到对应的 EvolutionLog 或 Persona,或日志非 soul 阶段",
            },
        )
    return {"ok": True, "data": persona, "error": None}


@router.get("")
async def get_evolution_info():
    """获取进化引擎状态信息(返回各阶段说明)"""
    return {
        "ok": True,
        "data": {
            "engine": "EvolutionEngine",
            "version": "6B",
            "phases": [
                {
                    "name": "extract",
                    "description": "L1→L2:从原始对话记忆提取关键信息",
                    "input_layer": "L1",
                    "output_layer": "L2",
                },
                {
                    "name": "compile",
                    "description": "L2→L3:将零散信息结构化为知识网络",
                    "input_layer": "L2",
                    "output_layer": "L3",
                },
                {
                    "name": "reflect",
                    "description": "L2+L3→L5:深度反思生成元认知",
                    "input_layer": "L2+L3",
                    "output_layer": "L5",
                },
                {
                    "name": "soul",
                    "description": "L5→SOUL.md:生成新的角色灵魂文件(需用户确认)",
                    "input_layer": "L5",
                    "output_layer": "SOUL.md",
                },
            ],
        },
        "error": None,
    }
