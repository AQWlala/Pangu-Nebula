from fastapi import APIRouter, HTTPException

from ..providers import get_provider, get_provider_info, list_providers

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def get_providers():
    return {"ok": True, "data": list_providers(), "error": None}


@router.get("/{name}")
async def get_provider_detail(name: str):
    info = get_provider_info(name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": f"Provider '{name}' not registered"},
        )
    return {"ok": True, "data": info, "error": None}


@router.post("/{name}/test")
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
