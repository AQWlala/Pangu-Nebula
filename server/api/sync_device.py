"""设备配对 + 中继同步 API (Phase 9B)

端点总览:
- 配对: POST /sync/pairing/initiate, POST /sync/pairing/confirm,
        GET /sync/pairing/status/{pairing_code}
- 设备: GET /sync/devices, GET /sync/devices/{device_id},
        DELETE /sync/devices/{device_id}
- 中继: POST /sync/relay/start, POST /sync/relay/stop,
        GET /sync/relay/status, POST /sync/relay/sync,
        GET /sync/relay/servers

路由顺序注意: 所有静态路径(pairing/initiate, pairing/confirm, devices,
relay/start 等)必须在动态路径 devices/{device_id} 之前注册。

独立于 api/sync.py,避免与 Phase 9A(CRDT/E2EE)修改冲突。
"""

from fastapi import APIRouter, HTTPException

from ..services.pairing_service import pairing_service
from ..services.relay_service import relay_service
from .models_sync import (
    PairingConfirmRequest,
    PairingInitiateRequest,
    RelayStartRequest,
    RelaySyncRequest,
)

router = APIRouter(prefix="/sync", tags=["sync-device"])


# ===== 配对端点(静态路径) =====


@router.post("/pairing/initiate", summary="发起设备配对", description="发起设备配对(生成密钥对 + 配对码 + QR 载荷)")
async def initiate_pairing(req: PairingInitiateRequest):
    """发起设备配对(生成密钥对 + 配对码 + QR 载荷)"""
    try:
        data = await pairing_service.initiate_pairing(device_name=req.device_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.post("/pairing/confirm", summary="确认设备配对", description="确认设备配对(验证配对码 + 计算共享密钥)")
async def confirm_pairing(req: PairingConfirmRequest):
    """确认设备配对(验证配对码 + 计算共享密钥)"""
    try:
        data = await pairing_service.confirm_pairing(
            pairing_code=req.pairing_code,
            peer_public_key=req.peer_public_key,
            peer_device_name=req.peer_device_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.get("/pairing/status/{pairing_code}", summary="查询配对状态", description="查询指定配对码的配对状态")
async def get_pairing_status(pairing_code: str):
    """查询配对状态"""
    data = pairing_service.get_pairing_status(pairing_code)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "配对码无效或已过期"},
        )
    return {"ok": True, "data": data, "error": None}


# ===== 设备端点(静态路径在前) =====


@router.get("/devices", summary="列出已配对设备", description="列出所有已配对设备")
async def list_devices():
    """列出所有已配对设备"""
    data = await pairing_service.list_devices()
    return {"ok": True, "data": data, "error": None}


# ===== 中继端点(静态路径) =====


@router.post("/relay/start", summary="启动中继", description="启动中继连接(连接到指定 URL 的中继服务器)")
async def start_relay(req: RelayStartRequest):
    """启动中继连接"""
    data = relay_service.start_relay(url=req.url, device_id=req.device_id)
    return {"ok": True, "data": data, "error": None}


@router.post("/relay/stop", summary="停止中继", description="停止中继连接")
async def stop_relay():
    """停止中继连接"""
    data = relay_service.stop_relay()
    return {"ok": True, "data": data, "error": None}


@router.get("/relay/status", summary="中继状态", description="获取中继连接的运行状态")
async def get_relay_status():
    """获取中继状态"""
    data = relay_service.get_status()
    return {"ok": True, "data": data, "error": None}


@router.post("/relay/sync", summary="触发中继同步", description="手动触发与指定设备的同步(push -> pull -> mark synced)")
async def relay_sync(req: RelaySyncRequest):
    """手动触发同步(push -> pull -> mark synced)"""
    device_id = req.device_id or relay_service.get_status().get("device_id", "")
    if not device_id:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": "未指定 device_id 且中继未连接"},
        )
    data = await relay_service.sync_with_device(device_id)
    return {"ok": True, "data": data, "error": None}


@router.get("/relay/servers", summary="列出中继服务器", description="列出已配置的中继服务器列表")
async def list_relay_servers():
    """列出已配置的中继服务器"""
    data = relay_service.list_relay_servers()
    return {"ok": True, "data": data, "error": None}


# ===== 设备端点(动态路径,必须在静态路径之后) =====


@router.get("/devices/{device_id}", summary="获取设备", description="获取单个已配对设备的信息")
async def get_device(device_id: str):
    """获取单个设备信息"""
    data = await pairing_service.get_device(device_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "设备未找到"},
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/devices/{device_id}", summary="撤销设备", description="撤销设备配对(status=blocked)")
async def revoke_device(device_id: str):
    """撤销设备配对(status=blocked)"""
    revoked = await pairing_service.revoke_device(device_id)
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "设备未找到"},
        )
    return {"ok": True, "data": {"device_id": device_id, "revoked": True}, "error": None}
