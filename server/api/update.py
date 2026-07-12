"""自动更新 API 端点 (T4.9)

注意: 此 router 不注册到 main.py,作为可选模块按需启用。
使用方式 (在需要时手动注册):
    from .api.update import router as update_router
    app.include_router(update_router)

端点总览:
- GET   /update/status                - 当前更新状态
- GET   /update/check                 - 检查新版本
- POST  /update/download              - 下载新版本
- POST  /update/install               - 安装新版本
- POST  /update/rollback              - 回滚到上一版本
- GET   /update/history               - 更新历史
- GET   /update/info                  - 模块信息
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.update_service import update_service, CURRENT_VERSION

router = APIRouter(prefix="/update", tags=["update"])


# ----------------------------------------------------------------------
# 请求模型
# ----------------------------------------------------------------------

class DownloadRequest(BaseModel):
    """下载新版本请求"""
    manifest: dict | None = Field(
        None, description="可选,自定义 manifest。如未提供则自动拉取远程 manifest"
    )


class InstallRequest(BaseModel):
    """安装新版本请求"""
    downloaded_file: str | None = Field(
        None,
        description="已下载文件路径。如未提供则自动下载最新版本",
    )


# ----------------------------------------------------------------------
# 端点
# ----------------------------------------------------------------------

@router.get(
    "/info",
    summary="更新模块信息",
    description="获取自动更新模块信息和端点列表",
)
async def get_update_info():
    """模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "update",
            "description": "Pangu Nebula 自动更新服务",
            "current_version": CURRENT_VERSION,
            "endpoints": [
                "GET /update/status",
                "GET /update/check",
                "POST /update/download",
                "POST /update/install",
                "POST /update/rollback",
                "GET /update/history",
            ],
        },
        "error": None,
    }


@router.get(
    "/status",
    summary="当前更新状态",
    description="获取当前版本、上一版本、最近检查/更新/回滚时间",
)
async def get_update_status():
    """当前更新状态"""
    try:
        data = update_service.get_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get(
    "/check",
    summary="检查新版本",
    description="拉取远程 manifest,比对当前版本与最新版本",
)
async def check_for_updates():
    """检查新版本"""
    try:
        data = await update_service.check_for_updates()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post(
    "/download",
    summary="下载新版本",
    description="下载新版本包 (mock 模式下创建虚拟文件,不实际下载)",
)
async def download_update(req: DownloadRequest | None = None):
    """下载新版本"""
    manifest = req.manifest if req else None
    try:
        data = await update_service.download_update(manifest)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if not data.get("downloaded"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": data, "error": data.get("error", "下载失败")},
        )
    return {"ok": True, "data": data, "error": None}


@router.post(
    "/install",
    summary="安装新版本",
    description="安装新版本 (mock 模式下仅更新状态文件,不实际替换文件)",
)
async def install_update(req: InstallRequest | None = None):
    """安装新版本"""
    downloaded_file = req.downloaded_file if req else None
    try:
        data = await update_service.install_update(downloaded_file)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if not data.get("installed"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": data, "error": data.get("error", "安装失败")},
        )
    return {"ok": True, "data": data, "error": None}


@router.post(
    "/rollback",
    summary="回滚到上一版本",
    description="回滚到上一版本 (mock 模式下仅更新状态文件)",
)
async def rollback_update():
    """回滚到上一版本"""
    try:
        data = await update_service.rollback_update()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    if not data.get("rolled_back"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": data, "error": data.get("error", "回滚失败")},
        )
    return {"ok": True, "data": data, "error": None}


@router.get(
    "/history",
    summary="更新历史",
    description="获取更新历史记录 (安装 / 回滚事件)",
)
async def get_update_history(
    limit: int = Query(10, ge=1, le=100, description="返回历史记录数量"),
):
    """更新历史"""
    try:
        data = update_service.get_history(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "data": None, "error": f"{type(exc).__name__}: {exc}"},
        )
    return {"ok": True, "data": {"history": data, "count": len(data)}, "error": None}
