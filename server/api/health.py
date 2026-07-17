"""Provider 健康检查 API 端点(Phase 10B)

注意: main.py 中已有 /health 端点(在 app 上直接定义),此处使用 /health-check 前缀避免冲突。

端点总览:
- GET   /health-check                                - 模块信息
- GET   /health-check/providers                      - 列出所有 Provider 健康状态
- GET   /health-check/providers/{name}               - 单个 Provider 状态
- POST  /health-check/check/{name}                   - 手动检查单个 Provider
- POST  /health-check/check-all                      - 手动检查所有 Provider
- GET   /health-check/history/{name}                 - Provider 历史记录
- GET   /health-check/monitor                        - 监控状态
- POST  /health-check/monitor/start                  - 启动监控
- POST  /health-check/monitor/stop                   - 停止监控

v2.3.0 Phase 3-D 新增:
- POST  /health-check/start                          - 全局启动健康检查
- POST  /health-check/stop                           - 全局停止健康检查
- GET   /health-check/status                         - 全局状态 + 所有 Provider 状态 (仪表盘用)
- POST  /health-check/providers/{name}/test          - 单 Provider 测试 (返回延迟/可用性)
- POST  /health-check/providers/{name}/toggle        - 单 Provider 启停

事件发布: 测试/启停后 publish `health.provider.toggled` 和 `health.check.completed`
(包 try/except,发布失败不影响主流程)。

路由顺序: 静态路径在动态路径(providers/{name}、check/{name}、history/{name})之前注册。
providers/{name}/test 与 providers/{name}/toggle 为 POST 子路径, 不与 GET providers/{name} 冲突。
"""

from fastapi import APIRouter, HTTPException, Query

from ..core.event_bus import get_event_bus
from ..providers.registry import is_registered
from ..services.health_check import health_check_service
from .models_scheduler import HealthStartRequest, MonitorStartRequest, ProviderToggleRequest

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
                "POST /health-check/start",
                "POST /health-check/stop",
                "GET /health-check/status",
                "POST /health-check/providers/{name}/test",
                "POST /health-check/providers/{name}/toggle",
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


@router.get("/providers/{name}", summary="获取 Provider 健康状态", description="获取单个 Provider 的当前健康状态")
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


@router.get("/monitor", summary="获取监控状态", description="获取 Provider 健康检查后台监控的当前状态")
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


@router.post("/monitor/start", summary="启动监控", description="启动 Provider 健康检查后台监控")
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


@router.post("/monitor/stop", summary="停止监控", description="停止 Provider 健康检查后台监控")
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


# ===== v2.3.0 Phase 3-D: 全局启停 + 单 Provider 测试/开关 + 状态汇总 =====


@router.post("/start", summary="全局启动健康检查", description="全局启动 Provider 健康检查 (打开总开关 + 启动后台监控)")
async def start_global(req: HealthStartRequest):
    """全局启动健康检查

    - 置 global_enabled=True
    - 若后台监控未运行,则启动监控
    - publish `health.check.completed` 事件 (try/except)
    """
    try:
        data = health_check_service.start_global(interval_seconds=req.interval_seconds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    # publish 事件 (失败不影响主流程)
    try:
        bus = get_event_bus()
        await bus.publish(
            "health.check.completed",
            {
                "global_enabled": True,
                "monitor": data.get("monitor", {}),
                "action": "start",
            },
            source="health_api",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "data": data, "error": None}


@router.post("/stop", summary="全局停止健康检查", description="全局停止 Provider 健康检查 (关闭总开关 + 停止后台监控)")
async def stop_global():
    """全局停止健康检查

    - 置 global_enabled=False
    - 停止后台监控
    - publish `health.check.completed` 事件 (try/except)
    """
    try:
        data = health_check_service.stop_global()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    try:
        bus = get_event_bus()
        await bus.publish(
            "health.check.completed",
            {
                "global_enabled": False,
                "monitor": data.get("monitor", {}),
                "action": "stop",
            },
            source="health_api",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "data": data, "error": None}


@router.get("/status", summary="全局状态 + 所有 Provider 状态", description="获取全局开关 + 监控 + 所有 Provider 健康状态汇总 (仪表盘用)")
async def get_full_status():
    """全局状态 + 所有 Provider 状态 (仪表盘用)"""
    try:
        data = health_check_service.get_full_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/providers/{name}/test", summary="单 Provider 测试", description="强制对单个 Provider 执行一次健康检查 (忽略 enabled 标记), 返回延迟/可用性")
async def test_provider(name: str):
    """单 Provider 测试

    - 即使 Provider 被禁用 (enabled=False), 也强制执行一次检查
    - 返回最新状态 (含 latency_ms / healthy / status)
    - publish `health.provider.toggled` 和 `health.check.completed` 事件 (try/except)
    """
    if not is_registered(name):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    try:
        data = await health_check_service.test_provider(name)
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
    # publish 事件 (失败不影响主流程)
    enabled = health_check_service.is_provider_enabled(name)
    try:
        bus = get_event_bus()
        await bus.publish(
            "health.provider.toggled",
            {
                "provider": name,
                "healthy": data.get("healthy"),
                "enabled": enabled,
                "latency_ms": data.get("latency_ms"),
                "action": "test",
            },
            source="health_api",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        bus = get_event_bus()
        await bus.publish(
            "health.check.completed",
            {
                "provider": name,
                "healthy": data.get("healthy"),
                "latency_ms": data.get("latency_ms"),
                "action": "test",
            },
            source="health_api",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "data": data, "error": None}


@router.post("/providers/{name}/toggle", summary="单 Provider 启停", description="启用/禁用单个 Provider 的健康检查 (禁用后监控循环跳过该 Provider)")
async def toggle_provider(name: str, req: ProviderToggleRequest):
    """单 Provider 启停

    - enabled=True: 恢复监控
    - enabled=False: 监控循环跳过该 Provider
    - publish `health.provider.toggled` 事件 (try/except)
    """
    if not is_registered(name):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    try:
        data = health_check_service.toggle_provider(name, req.enabled)
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
    # publish 事件 (失败不影响主流程)
    try:
        bus = get_event_bus()
        await bus.publish(
            "health.provider.toggled",
            {
                "provider": name,
                "healthy": data.get("healthy"),
                "enabled": data.get("enabled"),
                "action": "toggle",
            },
            source="health_api",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "data": data, "error": None}


@router.post("/check/{name}", summary="检查单个 Provider", description="手动触发检查单个 Provider 的健康状态")
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


@router.get("/history/{name}", summary="Provider 历史记录", description="获取指定 Provider 的健康检查历史记录")
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
