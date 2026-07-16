# server/api/cu.py
"""Computer Use 任务调度 API"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from server.cu.planner import CUTaskPlanner
from server.cu.safety.emergency_stop import EmergencyStop
from server.cu.safety.audit_log import AuditLogger
from server.cu.safety.rollback import RollbackManager
from server.config_kb_cu import CUConfig

router = APIRouter(prefix="/api/cu", tags=["computer-use"])

_emergency_stop = EmergencyStop()
_tasks: dict[str, dict] = {}


class CreateTaskRequest(BaseModel):
    instruction: str
    steps: list[dict]


class CreateTaskResponse(BaseModel):
    success: bool
    task_id: str
    step_count: int


class EmergencyStopRequest(BaseModel):
    reason: str = "manual"


def _get_config() -> CUConfig:
    config = CUConfig()
    config.ensure_dirs()
    return config


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task(req: CreateTaskRequest):
    planner = CUTaskPlanner()
    try:
        plan = planner.plan_manual(req.instruction, req.steps)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task_id = f"cutask-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    _tasks[task_id] = {"task_id": task_id, "plan": plan, "status": "created",
                       "current_step": -1, "created_at": datetime.now(timezone.utc).isoformat() + "Z"}
    return CreateTaskResponse(success=True, task_id=task_id, step_count=len(plan.steps))


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str, auto_confirm: bool = False):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    _tasks[task_id]["status"] = "executing"
    return {"success": True, "task_id": task_id, "status": "executing"}


@router.post("/emergency-stop")
async def emergency_stop(req: EmergencyStopRequest):
    _emergency_stop.trigger(req.reason)
    return {"success": True, "reason": req.reason, "message": "已触发急停"}


@router.post("/emergency-stop/reset")
async def reset_emergency_stop():
    _emergency_stop.reset()
    return {"success": True, "message": "急停已重置"}


@router.post("/tasks/{task_id}/rollback")
async def rollback_task(task_id: str, to_step: int = 0):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    manager = RollbackManager()
    result = await manager.rollback_task(task_id, to_step)
    return {"success": result.success, "rolled_back_count": result.rolled_back_count,
            "skipped_count": result.skipped_count}


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = _tasks[task_id]
    return {"task_id": task_id, "status": task["status"],
            "current_step": task["current_step"], "total_steps": len(task["plan"].steps)}


@router.get("/tasks/{task_id}/audit-log")
async def get_audit_log(task_id: str):
    config = _get_config()
    logger = AuditLogger(log_dir=config.audit_log_dir)
    return {"task_id": task_id, "logs": logger.get_task_logs(task_id)}


@router.get("/tasks")
async def list_tasks():
    return {"tasks": [{"task_id": t["task_id"], "status": t["status"],
                       "instruction": t["plan"].instruction,
                       "step_count": len(t["plan"].steps), "created_at": t["created_at"]}
                      for t in _tasks.values()]}
