"""调度器 API 端点(Phase 10B)

端点总览:
- GET    /scheduler                  - 模块信息
- GET    /scheduler/status           - 调度器状态
- POST   /scheduler/start            - 启动调度器
- POST   /scheduler/stop             - 停止调度器
- GET    /scheduler/jobs             - 列出所有任务
- POST   /scheduler/jobs             - 创建任务
- GET    /scheduler/jobs/{job_id}    - 获取单个任务
- PUT    /scheduler/jobs/{job_id}    - 更新任务
- DELETE /scheduler/jobs/{job_id}    - 删除任务
- POST   /scheduler/jobs/{job_id}/trigger     - 手动触发任务
- GET    /scheduler/jobs/{job_id}/history     - 任务执行历史

路由顺序: 静态路径(status/start/stop/jobs)在动态路径(jobs/{job_id})之前注册。
"""

from fastapi import APIRouter, HTTPException, Query

from ..services.scheduler_service import scheduler_service
from .models_scheduler import SchedulerJobCreateRequest, SchedulerJobUpdateRequest

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("")
async def get_scheduler():
    """模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "scheduler",
            "description": "定时任务调度器(基于 APScheduler)",
            "available": scheduler_service.is_available(),
            "endpoints": [
                "GET /scheduler/status",
                "POST /scheduler/start",
                "POST /scheduler/stop",
                "GET /scheduler/jobs",
                "POST /scheduler/jobs",
                "GET /scheduler/jobs/{job_id}",
                "PUT /scheduler/jobs/{job_id}",
                "DELETE /scheduler/jobs/{job_id}",
                "POST /scheduler/jobs/{job_id}/trigger",
                "GET /scheduler/jobs/{job_id}/history",
            ],
        },
        "error": None,
    }


@router.get("/status")
async def get_status():
    """获取调度器状态"""
    try:
        data = scheduler_service.get_status()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "data": data, "error": None}


@router.post("/start")
async def start_scheduler():
    """启动调度器"""
    try:
        data = await scheduler_service.start()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if not data.get("available"):
        return {
            "ok": False,
            "data": data,
            "error": "APScheduler not available; install apscheduler to enable",
        }
    return {"ok": True, "data": data, "error": None}


@router.post("/stop")
async def stop_scheduler():
    """停止调度器"""
    try:
        data = await scheduler_service.stop()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/jobs")
async def list_jobs():
    """列出所有定时任务"""
    try:
        data = await scheduler_service.list_jobs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/jobs")
async def create_job(req: SchedulerJobCreateRequest):
    """创建定时任务"""
    try:
        data = await scheduler_service.add_job(
            name=req.name,
            cron_expr=req.cron_expr,
            action=req.action,
            enabled=req.enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int):
    """获取单个定时任务"""
    try:
        data = await scheduler_service.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Job {job_id} not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/jobs/{job_id}")
async def update_job(job_id: int, req: SchedulerJobUpdateRequest):
    """更新定时任务(仅更新提供的字段)"""
    try:
        data = await scheduler_service.update_job(
            job_id, **req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Job {job_id} not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    """删除定时任务"""
    try:
        deleted = await scheduler_service.remove_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Job {job_id} not found"},
        )
    return {"ok": True, "data": {"id": job_id, "deleted": True}, "error": None}


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(job_id: int):
    """手动触发任务(立即执行一次)"""
    try:
        data = await scheduler_service.trigger_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Job {job_id} not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/jobs/{job_id}/history")
async def get_job_history(
    job_id: int,
    limit: int = Query(20, ge=1, le=100, description="返回的历史记录数量"),
):
    """获取任务执行历史"""
    data = scheduler_service.get_job_history(job_id, limit=limit)
    return {"ok": True, "data": data, "error": None}
