from fastapi import APIRouter, HTTPException

from ..providers import get_provider, get_provider_info, list_providers

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", summary="列出 Provider", description="列出所有已注册的 LLM Provider 及其基本信息")
async def get_providers():
    return {"ok": True, "data": list_providers(), "error": None}


@router.get("/{name}", summary="获取 Provider", description="根据名称获取单个 Provider 的详细信息(能力、模型列表等)")
async def get_provider_detail(name: str):
    info = get_provider_info(name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    return {"ok": True, "data": info, "error": None}


@router.post("/{name}/test", summary="测试 Provider 连通性", description="测试指定 Provider 的网络连通性,返回 connected 状态")
async def test_provider(name: str):
    try:
        provider = get_provider(name)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": str(exc)},
        )
    try:
        ok = await provider.test_connection()
    except Exception as exc:
        return {
            "ok": False,
            "data": {"connected": False, "error": str(exc)},
            "error": "Connection test failed",
        }
    return {
        "ok": ok,
        "data": {"connected": ok},
        "error": None if ok else "Provider connectivity check failed",
    }
