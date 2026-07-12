"""Provider 健康检查 API 端点(Phase 10B)

注意: main.py 中已有 /health 端点(在 app 上直接定义),此处使用 /health-check 前缀避免冲突。

端点总览:
- GET   /health-check                       - 模块信息
- GET   /health-check/providers             - 列出所有 Provider 健康状态
- GET   /health-check/providers/{name}      - 单个 Provider 状态
- POST  /health-check/check/{name}          - 手动检查单个 Provider
- POST  /health-check/check-all             - 手动检查所有 Provider
- GET   /health-check/history/{name}        - Provider 历史记录
- GET   /health-check/monitor               - 监控状态
- POST  /health-check/monitor/start         - 启动监控
- POST  /health-check/monitor/stop          - 停止监控

路由顺序: 静态路径在动态路径(providers/{name}、check/{name}、history/{name})之前注册。
"""

from fastapi import APIRouter, HTTPException, Query

from ..providers.registry import is_registered
from ..services.health_check import health_check_service
from .models_scheduler import MonitorStartRequest

router = APIRouter(prefix="/health-check", tags=["health-check"])


@router.get("", summary="健康检查模块信息", description="获取 Provider 健康检查 + 降级 + 监控模块信息和端点列表")
async def get_health_check():
    """模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "health-check",
            "description": "Provider 健康检查 + 降级 + 监控",
            "endpoints": [
                "GET /health-check/providers",
                "GET /health-check/providers/{name}",
                "POST /health-check/check/{name}",
                "POST /health-check/check-all",
                "GET /health-check/history/{name}",
                "GET /health-check/monitor",
                "POST /health-check/monitor/start",
                "POST /health-check/monitor/stop",
            ],
        },
        "error": None,
    }


@router.get("/providers", summary="列出 Provider 状态", description="列出所有 Provider 的健康状态")
async def list_providers_status():
    """列出所有 Provider 健康状态"""
    try:
        data = health_check_service.list_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/providers/{name}")
async def get_provider_status(name: str):
    """获取单个 Provider 健康状态"""
    if not is_registered(name):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    data = health_check_service.get_status(name)
    if data is None:
        return {
            "ok": True,
            "data": {
                "name": name,
                "healthy": None,
                "status": "unknown",
                "message": "No health check performed yet",
            },
            "error": None,
        }
    return {"ok": True, "data": data, "error": None}


@router.post("/check-all", summary="检查所有 Provider", description="手动触发检查所有 Provider 的健康状态")
async def check_all_providers():
    """手动检查所有 Provider"""
    try:
        data = await health_check_service.check_all()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/monitor")
async def get_monitor_status():
    """获取监控状态"""
    try:
        data = health_check_service.get_monitor_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/monitor/start")
async def start_monitor(req: MonitorStartRequest):
    """启动后台监控"""
    try:
        data = health_check_service.start_monitor(interval_seconds=req.interval_seconds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/monitor/stop")
async def stop_monitor():
    """停止后台监控"""
    try:
        data = health_check_service.stop_monitor()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/check/{name}")
async def check_provider(name: str):
    """手动检查单个 Provider"""
    if not is_registered(name):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    try:
        data = await health_check_service.check_provider(name)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/history/{name}")
async def get_provider_history(
    name: str,
    limit: int = Query(20, ge=1, le=100, description="返回的历史记录数量"),
):
    """获取 Provider 历史记录"""
    if not is_registered(name):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    try:
        data = health_check_service.get_history(name, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}
