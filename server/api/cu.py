# server/api/cu.py
"""Computer Use 任务调度 API"""
from __future__ import annotations
import asyncio
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.cu.planner import CUTaskPlanner
from server.cu.safety.emergency_stop import EmergencyStop
from server.cu.safety.audit_log import AuditLogger
from server.cu.executor.runner import CUExecutor
from server.config_kb_cu import CUConfig

router = APIRouter(prefix="/api/cu", tags=["computer-use"])

_emergency_stop = EmergencyStop()
_tasks: dict[str, dict] = {}

# Module-level executor singleton (shares emergency stop with the API)
_executor: CUExecutor | None = None


def _get_executor() -> CUExecutor:
    global _executor
    if _executor is None:
        _executor = CUExecutor(emergency_stop=_emergency_stop)
    return _executor


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

    task = _tasks[task_id]
    plan = task["plan"]
    # CUTaskPlan.steps are dataclasses — convert to dicts for the executor
    plan_steps = [asdict(s) for s in plan.steps]

    task["status"] = "executing"
    task["current_step"] = 0

    executor = _get_executor()
    # Run in a thread to avoid blocking the event loop
    result = await asyncio.to_thread(executor.run_task, task_id, plan_steps)

    task["status"] = result["status"]
    task["current_step"] = result["executed_steps"]
    task["result"] = result

    return {"success": True, "task_id": task_id, "status": result["status"],
            "executed_steps": result["executed_steps"]}


@router.post("/emergency-stop")
async def emergency_stop(req: EmergencyStopRequest):
    _emergency_stop.trigger(req.reason)
    return {"success": True, "reason": req.reason, "message": "已触发急停"}


@router.post("/emergency-stop/reset")
async def reset_emergency_stop():
    _emergency_stop.reset()
    return {"success": True, "message": "急停已重置"}


@router.post("/tasks/{task_id}/rollback")
async def rollback_task(task_id: str, to_step: int | None = None):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    executor = _get_executor()
    result = await asyncio.to_thread(executor.rollback_task, task_id, to_step)

    if result.get("success"):
        _tasks[task_id]["status"] = "rolled_back"

    return result


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
