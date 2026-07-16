"""v2.2.1 P3: 统一鉴权依赖 — 供需要显式鉴权的路由使用

现有路由鉴权依赖外层 middleware (sidecar_token_auth)。
本模块提供路由级 Depends 函数,用于:
1. 纵深防御 (middleware 失效时路由仍可拦截)
2. 审计 (路由级鉴权日志)
3. 未来细粒度权限控制

用法:
    from .deps import require_token
    @router.get("/sensitive", dependencies=[Depends(require_token)])
    async def sensitive_endpoint(): ...

本模块为可选依赖,不强制现有路由使用。
与 server/api/terminal.py 的 verify_terminal_access 行为一致:
- pywebview 模式 (sidecar_token 为空): 放行 (向后兼容)
- tauri 模式 (sidecar_token 非空): 校验 Authorization Bearer token
"""
from __future__ import annotations

import logging
import secrets

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def get_sidecar_token() -> str:
    """从 settings 获取 sidecar_token

    使用延迟 import 避免循环依赖 (main.py 反向引用 api 路由)。
    任何异常都视作"无 token" — pywebview 模式放行。
    """
    try:
        from ..main import settings

        return getattr(settings, "sidecar_token", "") or ""
    except Exception:
        # main.py 未导入或 settings 未就绪: 视为无 token (pywebview 模式)
        return ""


def require_token(request: Request) -> None:
    """要求请求携带有效 sidecar_token

    - pywebview 模式 (token 为空): 直接放行 (向后兼容)
    - tauri 模式 (token 非空): 校验 Authorization Bearer token

    Raises:
        HTTPException(401): 缺失/畸形 Authorization 头或 token 不匹配
    """
    token = get_sidecar_token()
    if not token:
        # pywebview 模式: 无 token 配置,允许访问
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization header",
        )

    provided = auth_header[7:]  # 去掉 "Bearer "
    if not secrets.compare_digest(provided, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        )
