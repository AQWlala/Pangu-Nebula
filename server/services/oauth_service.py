"""OAuth 服务 (Phase 8B)

实现 OAuth PKCE (Proof Key for Code Exchange) 流程,
支持 Gmail / GitHub / Notion / Slack 四个提供商。

PKCE 流程:
1. 客户端生成 code_verifier (随机串) 和 code_challenge (sha256+base64url)
2. 授权请求携带 code_challenge,回调时携带 code_verifier
3. 提供商验证 code_verifier 的 sha256 与 code_challenge 一致

融合来源:
- Nebula 的 OAuth 身份设计
- PKCE (Proof Key for Code Exchange) 流程
"""

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from .token_manager import token_manager


# 提供商配置
PROVIDER_CONFIGS: dict[str, dict] = {
    "gmail": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "client_id_env": "GMAIL_CLIENT_ID",
        "client_secret_env": "GMAIL_CLIENT_SECRET",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scope": "repo user",
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET",
    },
    "notion": {
        "authorize_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scope": "",
        "client_id_env": "NOTION_CLIENT_ID",
        "client_secret_env": "NOTION_CLIENT_SECRET",
    },
    "slack": {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scope": "chat:write channels:read",
        "client_id_env": "SLACK_CLIENT_ID",
        "client_secret_env": "SLACK_CLIENT_SECRET",
    },
}


def _b64url_encode(data: bytes) -> str:
    """base64url 编码 (无 padding)"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class OAuthService:
    """OAuth PKCE 服务"""

    def __init__(self):
        # PKCE code_verifier 内存存储, key 为 state
        self._pkce_store: dict[str, dict] = {}

    # ===== PKCE 相关 =====

    def generate_pkce(self) -> dict:
        """生成 PKCE code_verifier 和 code_challenge

        - code_verifier: 随机 43-128 字符字符串
        - code_challenge: base64url(sha256(code_verifier))
        - code_challenge_method: S256

        Returns:
            {"code_verifier": "...", "code_challenge": "...", "code_challenge_method": "S256"}
        """
        # secrets.token_urlsafe(64) 生成约 86 字符的 URL 安全字符串
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = _b64url_encode(digest)
        return {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

    # ===== 授权 URL =====

    def get_authorize_url(self, provider: str, redirect_uri: str, state: str | None = None) -> dict:
        """获取授权 URL

        生成 PKCE,构建 authorize URL,并将 code_verifier 存储到内存供 callback 使用。

        Args:
            provider: 提供商名称 (gmail/github/notion/slack)
            redirect_uri: 回调地址
            state: CSRF 防护 state,为 None 时自动生成

        Returns:
            {"url": "...", "state": "...", "code_verifier": "..."}
        """
        config = PROVIDER_CONFIGS.get(provider)
        if config is None:
            raise ValueError(f"不支持的 OAuth 提供商: {provider}")

        creds = self._get_client_credentials(provider)
        if creds is None:
            raise ValueError(
                f"提供商 {provider} 的 client_id/client_secret 未配置环境变量"
            )
        client_id, _ = creds

        # 生成 state (若未提供)
        if state is None:
            state = secrets.token_urlsafe(32)

        # 生成 PKCE
        pkce = self.generate_pkce()

        # 构建查询参数
        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": pkce["code_challenge_method"],
        }
        # scope 非空时才添加 (Notion scope 为空)
        scope = config.get("scope", "")
        if scope:
            params["scope"] = scope

        # Notion 使用 owner=user 参数
        if provider == "notion":
            params["owner"] = "user"

        authorize_url = f"{config['authorize_url']}?{urlencode(params)}"

        # 存储 code_verifier 供 callback 使用, key 为 state
        self._pkce_store[state] = {
            "code_verifier": pkce["code_verifier"],
            "provider": provider,
            "redirect_uri": redirect_uri,
        }

        return {
            "url": authorize_url,
            "state": state,
            "code_verifier": pkce["code_verifier"],
        }

    # ===== 授权码交换 Token =====

    async def exchange_code(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        state: str | None = None,
        code_verifier: str | None = None,
    ) -> dict:
        """用授权码交换 Token

        向提供商的 token_url 发起 POST 请求,交换 access_token。
        成功后通过 TokenManager 存储到数据库。

        Args:
            provider: 提供商名称
            code: 授权码
            redirect_uri: 回调地址 (需与 authorize 一致)
            state: CSRF state (用于从内存中取回 code_verifier)
            code_verifier: PKCE code_verifier (优先使用显式传入的)

        Returns:
            {"access_token": "...", "token_type": "...", "expires_in": N, "scope": "...", "token_id": int}

        Raises:
            ValueError: 提供商不支持 / 凭证未配置
            RuntimeError: 交换失败
        """
        config = PROVIDER_CONFIGS.get(provider)
        if config is None:
            raise ValueError(f"不支持的 OAuth 提供商: {provider}")

        creds = self._get_client_credentials(provider)
        if creds is None:
            raise ValueError(
                f"提供商 {provider} 的 client_id/client_secret 未配置环境变量"
            )
        client_id, client_secret = creds

        # 若未显式传入 code_verifier,尝试从内存中取回
        if code_verifier is None and state is not None:
            stored = self._pkce_store.get(state)
            if stored:
                code_verifier = stored.get("code_verifier")

        # 构建请求体
        data: dict[str, str] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        # code_verifier 存在时才添加 (部分 provider 可能不要求 PKCE)
        if code_verifier:
            data["code_verifier"] = code_verifier

        headers: dict[str, str] = {"Accept": "application/json"}
        # GitHub 必须指定 Accept: application/json 才返回 JSON
        if provider == "github":
            headers["Accept"] = "application/json"

        # Notion 使用 HTTP Basic Auth (client_id:client_secret)
        auth = None
        if provider == "notion":
            auth = httpx.BasicAuth(client_id, client_secret)
            # Notion 的 body 中不需要 client_secret
            data.pop("client_secret", None)

        token_url = config["token_url"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(token_url, data=data, headers=headers, auth=auth)
        except httpx.RequestError as e:
            raise RuntimeError(f"OAuth token 交换请求失败: {e}")

        if resp.status_code != 200:
            raise RuntimeError(
                f"OAuth token 交换失败: HTTP {resp.status_code} - {resp.text}"
            )

        try:
            token_data = resp.json()
        except Exception:
            raise RuntimeError("OAuth token 响应不是有效的 JSON")

        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(
                f"OAuth token 响应中缺少 access_token: {token_data}"
            )

        refresh_token = token_data.get("refresh_token")
        token_type = token_data.get("token_type", "Bearer")
        expires_in = token_data.get("expires_in")
        scope = token_data.get("scope", config.get("scope", ""))

        # 尝试获取 account_id (各 provider 字段不同)
        account_id = self._extract_account_id(provider, token_data)

        # 计算过期时间
        expires_at = None
        if expires_in:
            expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

        # 存储 Token 到数据库
        stored = await token_manager.store_token(
            provider=provider,
            account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            scope=scope,
            expires_at=expires_at,
        )

        # 清理 PKCE 内存存储
        if state is not None:
            self._pkce_store.pop(state, None)

        return {
            "access_token": access_token,
            "token_type": token_type,
            "expires_in": int(expires_in) if expires_in else 0,
            "scope": scope,
            "refresh_token": refresh_token,
            "token_id": stored.get("id"),
            "account_id": account_id,
        }

    # ===== 提供商列表 =====

    def list_providers(self) -> list[dict]:
        """列出支持的提供商及配置状态

        Returns:
            [{"provider": "gmail", "configured": True/False, "scope": "..."}, ...]
        """
        providers: list[dict] = []
        for name, config in PROVIDER_CONFIGS.items():
            creds = self._get_client_credentials(name)
            providers.append({
                "provider": name,
                "configured": creds is not None,
                "scope": config.get("scope", ""),
                "authorize_url": config["authorize_url"],
            })
        return providers

    # ===== 私有方法 =====

    def _get_client_credentials(self, provider: str) -> tuple[str, str] | None:
        """从环境变量获取 client_id 和 client_secret

        Args:
            provider: 提供商名称

        Returns:
            (client_id, client_secret) 或 None (未配置时)
        """
        config = PROVIDER_CONFIGS.get(provider)
        if config is None:
            return None
        client_id = os.environ.get(config["client_id_env"], "").strip()
        client_secret = os.environ.get(config["client_secret_env"], "").strip()
        if not client_id or not client_secret:
            return None
        return (client_id, client_secret)

    def _extract_account_id(self, provider: str, token_data: dict) -> str | None:
        """从 token 响应中提取 account_id (各 provider 字段不同)

        Args:
            provider: 提供商名称
            token_data: token 响应 dict

        Returns:
            account_id 字符串或 None
        """
        if provider == "gmail":
            # Google 返回 id_token,可解析出 email;简化处理用 id
            return token_data.get("id_token") or None
        elif provider == "github":
            # GitHub token 响应无用户信息,需额外 API 调用
            # 简化: 返回 None,后续可通过 API 补充
            return None
        elif provider == "notion":
            # Notion 返回 bot/user 信息
            bot = token_data.get("bot") or {}
            owner = token_data.get("owner") or {}
            return owner.get("user", {}).get("id") or bot.get("owner", {}).get("user", {}).get("id")
        elif provider == "slack":
            # Slack 返回 authed_user / team
            authed_user = token_data.get("authed_user") or {}
            return authed_user.get("id") or token_data.get("team_id")
        return None


# 模块级单例
oauth_service = OAuthService()
