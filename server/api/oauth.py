"""OAuth API 端点 (Phase 8B)

提供 OAuth 授权流程和 Token 管理的 REST API。

路由:
- GET    /oauth              获取 OAuth 模块信息
- GET    /oauth/providers    列出支持的提供商
- POST   /oauth/authorize    获取授权 URL
- POST   /oauth/callback     OAuth 回调 (交换 Token)
- POST   /oauth/refresh      刷新 Token
- GET    /oauth/tokens       列出 Token
- POST   /oauth/tokens       手动存储 Token
- GET    /oauth/tokens/{id}  获取单个 Token
- DELETE /oauth/tokens/{id}  删除 Token
- POST   /oauth/tokens/{id}/revoke  撤销 Token

注意: 静态路由必须在动态路由之前声明。
"""

from fastapi import APIRouter, HTTPException

from ..services.oauth_service import oauth_service
from ..services.token_manager import token_manager
from .models import (
    OAuthAuthorizeRequest,
    OAuthCallbackRequest,
    OAuthRefreshRequest,
    TokenStoreRequest,
)

router = APIRouter(prefix="/oauth", tags=["oauth"])


# ===== 模块信息 / 提供商 =====


@router.get("")
async def get_oauth():
    """获取 OAuth 模块信息 (支持的平台列表 + 配置状态)"""
    providers = oauth_service.list_providers()
    return {
        "ok": True,
        "data": {
            "module": "oauth",
            "providers": providers,
            "supported": [p["provider"] for p in providers],
        },
        "error": None,
    }


@router.get("/providers")
async def list_providers():
    """列出支持的 OAuth 提供商及配置状态"""
    providers = oauth_service.list_providers()
    return {"ok": True, "data": providers, "error": None}


# ===== OAuth 授权流程 =====


@router.post("/authorize")
async def authorize(req: OAuthAuthorizeRequest):
    """获取 OAuth 授权 URL (启动 PKCE 流程)

    生成授权 URL,前端跳转到该 URL 让用户授权。
    """
    try:
        result = oauth_service.get_authorize_url(
            provider=req.provider,
            redirect_uri=req.redirect_uri,
            state=req.state,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/callback")
async def callback(req: OAuthCallbackRequest):
    """OAuth 回调: 用授权码交换 Token

    前端收到提供商重定向后,将 code 和 state 提交到此端点。
    """
    try:
        result = await oauth_service.exchange_code(
            provider=req.provider,
            code=req.code,
            redirect_uri=req.redirect_uri,
            state=req.state,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail={"ok": False, "data": None, "error": str(e)}
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=502, detail={"ok": False, "data": None, "error": str(e)}
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/refresh")
async def refresh_token(req: OAuthRefreshRequest):
    """刷新 Token"""
    result = await token_manager.refresh_token(req.token_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "data": None,
                "error": "Token 不存在 / 无 refresh_token / 刷新失败",
            },
        )
    return {"ok": True, "data": result, "error": None}


# ===== Token 管理 =====


@router.get("/tokens")
async def list_tokens(provider: str | None = None):
    """列出 Token (可按 provider 过滤)"""
    data = await token_manager.list_tokens(provider=provider)
    return {"ok": True, "data": data, "error": None}


@router.post("/tokens")
async def store_token(req: TokenStoreRequest):
    """手动存储 Token (非 OAuth 流程,直接写入)"""
    data = await token_manager.store_token(
        provider=req.provider,
        account_id=req.account_id,
        access_token=req.access_token,
        refresh_token=req.refresh_token,
        token_type=req.token_type,
        scope=req.scope,
        expires_at=req.expires_at,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/tokens/{token_id}")
async def get_token(token_id: int):
    """获取单个 Token"""
    data = await token_manager.get_token(token_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Token 不存在"}
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: int):
    """删除 Token"""
    deleted = await token_manager.delete_token(token_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Token 不存在"}
        )
    return {"ok": True, "data": {"id": token_id, "deleted": True}, "error": None}


@router.post("/tokens/{token_id}/revoke")
async def revoke_token(token_id: int):
    """撤销 Token (标记为过期)"""
    revoked = await token_manager.revoke_token(token_id)
    if not revoked:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "Token 不存在"}
        )
    return {"ok": True, "data": {"id": token_id, "revoked": True}, "error": None}
