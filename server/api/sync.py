"""同步 API(Phase 9A: CRDT 部分)

端点总览(CRDT 部分,中继端点由 9B 子智能体补充):
- GET  /sync                 模块信息
- GET  /sync/crdt/keys       列出所有 CRDT 键
- POST /sync/crdt/lww        创建/更新 LWW Register
- POST /sync/crdt/lww/{key}/merge  合并远程 LWW Register(静态子路径,在 /{key} 前)
- GET  /sync/crdt/lww/{key}  获取 LWW Register 值
- POST /sync/crdt/orset      创建 OR-Set
- POST /sync/crdt/orset/{key}/add     添加元素
- POST /sync/crdt/orset/{key}/remove  删除元素
- POST /sync/crdt/orset/{key}/merge   合并远程 OR-Set
- GET  /sync/crdt/orset/{key}         获取 OR-Set 值
- GET  /sync/operations                列出待同步操作
- POST /sync/operations/{op_id}/synced 标记操作已同步

路由顺序注意: 所有静态/更具体的子路径(如 /crdt/keys、/crdt/lww、
/crdt/lww/{key}/merge)必须在动态路径 /crdt/lww/{key} 之前注册。
"""

from fastapi import APIRouter, HTTPException, Query

from ..services.crdt_service import crdt_service
from .models import (
    LWWCreateRequest,
    LWWMergeRequest,
    ORSetAddRequest,
    ORSetCreateRequest,
    ORSetMergeRequest,
    ORSetRemoveRequest,
    SyncOpSyncedRequest,
)

router = APIRouter(prefix="/sync", tags=["sync"])


# ===== 模块信息 =====


@router.get("")
async def get_sync():
    """获取同步模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "sync",
            "phase": "9A",
            "features": [
                "crdt_lww",
                "crdt_orset",
                "crdt_rga",
                "sync_operations",
            ],
            "relay": "pending_9b",  # 中继端点由 9B 补充
        },
        "error": None,
    }


# ===== CRDT 键列表(静态路径,在动态路径前) =====


@router.get("/crdt/keys")
async def list_crdt_keys():
    """列出所有 CRDT 键(去重,标注 op_type)"""
    try:
        data = await crdt_service.list_keys()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


# ===== LWW Register =====


@router.post("/crdt/lww")
async def create_lww(req: LWWCreateRequest):
    """创建/更新 LWW Register"""
    try:
        data = await crdt_service.create_lww(
            key=req.key, value=req.value, node_id=req.node_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/crdt/lww/{key}/merge")
async def merge_lww(key: str, req: LWWMergeRequest):
    """合并远程 LWW Register

    注意:此路由在 /crdt/lww/{key} 之前注册,避免路径冲突。
    """
    other_register = {
        "value": req.value,
        "timestamp": req.timestamp,
        "node_id": req.node_id,
    }
    try:
        data = await crdt_service.merge_lww(key, other_register)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/crdt/lww/{key}")
async def get_lww(key: str):
    """获取 LWW Register 值"""
    try:
        data = await crdt_service.get_lww(key)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"LWW register '{key}' not found"},
        )
    return {"ok": True, "data": data, "error": None}


# ===== OR-Set =====


@router.post("/crdt/orset")
async def create_orset(req: ORSetCreateRequest):
    """创建空 OR-Set"""
    try:
        data = await crdt_service.create_orset(req.key)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/crdt/orset/{key}/add")
async def add_to_orset(key: str, req: ORSetAddRequest):
    """向 OR-Set 添加元素"""
    try:
        data = await crdt_service.add_to_orset(key, req.value)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/crdt/orset/{key}/remove")
async def remove_from_orset(key: str, req: ORSetRemoveRequest):
    """从 OR-Set 删除元素"""
    try:
        data = await crdt_service.remove_from_orset(key, req.value)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/crdt/orset/{key}/merge")
async def merge_orset(key: str, req: ORSetMergeRequest):
    """合并远程 OR-Set"""
    try:
        data = await crdt_service.merge_orset(key, req.elements)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/crdt/orset/{key}")
async def get_orset(key: str):
    """获取 OR-Set 的所有值"""
    try:
        data = await crdt_service.get_orset_values(key)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"OR-Set '{key}' not found"},
        )
    return {"ok": True, "data": data, "error": None}


# ===== 同步操作追踪 =====


@router.get("/operations")
async def list_operations(
    device_id: str = Query(..., description="查询未同步到该设备的操作"),
):
    """列出待同步操作(未同步到指定设备)"""
    try:
        data = await crdt_service.list_pending_ops(device_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": {"operations": data, "count": len(data)}, "error": None}


@router.post("/operations/{op_id}/synced")
async def mark_op_synced(op_id: int, req: SyncOpSyncedRequest):
    """标记操作已同步到某设备"""
    try:
        data = await crdt_service.mark_synced(op_id, req.device_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"ok": False, "data": None, "error": str(e)}
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Operation {op_id} not found"},
        )
    return {"ok": True, "data": data, "error": None}
