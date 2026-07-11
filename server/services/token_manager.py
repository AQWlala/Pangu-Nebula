"""Token 管理服务 (Phase 8B)

实现 OAuth Token 的存储 / 查询 / 刷新 / 撤销 / 删除。
简化实现: 用 base64 编码存储 Token (实际生产应用 AES 加密)。

融合来源:
- Nebula 的 Token 管理设计
- PKCE (Proof Key for Code Exchange) 流程
"""

import base64
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import OauthToken


# 加密前缀,用于区分明文与已编码内容
_ENC_PREFIX = "b64::"


def _token_to_dict(t: OauthToken, decrypt: bool = True) -> dict:
    """ORM 转 dict

    Args:
        t: OauthToken ORM 对象
        decrypt: 是否解密 access_token / refresh_token
    """
    return {
        "id": t.id,
        "provider": t.provider,
        "account_id": t.account_id,
        "access_token": _decrypt_token(t.access_token) if decrypt else t.access_token,
        "refresh_token": _decrypt_token(t.refresh_token) if (decrypt and t.refresh_token) else t.refresh_token,
        "token_type": t.token_type,
        "scope": t.scope,
        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _encrypt_token(token: str | None) -> str | None:
    """简单加密: 用 base64 编码 (实际生产应用 AES 加密)

    Args:
        token: 明文 Token

    Returns:
        编码后的字符串,带 b64:: 前缀;输入为 None 则返回 None
    """
    if token is None:
        return None
    encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{encoded}"


def _decrypt_token(encrypted: str | None) -> str | None:
    """解密: 对 base64 编码的 Token 进行解码

    Args:
        encrypted: 已编码的字符串 (带 b64:: 前缀) 或明文

    Returns:
        解码后的明文 Token;输入为 None 则返回 None;
        若无前缀则视为明文直接返回 (兼容旧数据)
    """
    if encrypted is None:
        return None
    if not encrypted.startswith(_ENC_PREFIX):
        # 无前缀,视为明文 (兼容未加密的旧数据)
        return encrypted
    raw = encrypted[len(_ENC_PREFIX):]
    try:
        return base64.b64decode(raw.encode("ascii")).decode("utf-8")
    except Exception:
        return encrypted


def _parse_expires_at(expires_at) -> datetime | None:
    """解析过期时间,支持多种输入格式

    Args:
        expires_at: datetime / ISO 字符串 / int (秒数偏移) / None

    Returns:
        datetime 对象或 None
    """
    if expires_at is None:
        return None
    if isinstance(expires_at, datetime):
        return expires_at
    if isinstance(expires_at, (int, float)):
        # 视为相对秒数 (expires_in)
        return datetime.utcnow() + timedelta(seconds=int(expires_at))
    if isinstance(expires_at, str):
        s = expires_at.strip()
        if not s:
            return None
        # 尝试纯数字 (秒数)
        if s.isdigit():
            return datetime.utcnow() + timedelta(seconds=int(s))
        # 尝试 ISO 格式
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


class TokenManager:
    """Token 管理器: 存储 / 查询 / 刷新 / 撤销 / 删除"""

    async def store_token(
        self,
        provider: str,
        account_id: str | None,
        access_token: str,
        refresh_token: str | None = None,
        token_type: str = "Bearer",
        scope: str | None = None,
        expires_at=None,
    ) -> dict:
        """存储 Token (加密后写入数据库)

        Args:
            provider: 提供商 (gmail/github/notion/slack)
            account_id: 账户 ID
            access_token: 访问令牌 (明文,会被加密)
            refresh_token: 刷新令牌 (明文,会被加密)
            token_type: 令牌类型,默认 Bearer
            scope: 授权范围
            expires_at: 过期时间 (datetime / ISO 字符串 / 秒数 / None)

        Returns:
            存储后的 Token dict (含 id,已解密)
        """
        parsed_expires = _parse_expires_at(expires_at)
        token = OauthToken(
            provider=provider,
            account_id=account_id,
            access_token=_encrypt_token(access_token) or "",
            refresh_token=_encrypt_token(refresh_token),
            token_type=token_type,
            scope=scope,
            expires_at=parsed_expires,
        )
        async with async_session() as session:
            session.add(token)
            await session.commit()
            await session.refresh(token)
            return _token_to_dict(token)

    async def get_token(self, token_id: int) -> dict | None:
        """获取单个 Token (解密)

        Args:
            token_id: Token ID

        Returns:
            Token dict 或 None (不存在时)
        """
        async with async_session() as session:
            token = await session.get(OauthToken, token_id)
            if token is None:
                return None
            return _token_to_dict(token)

    async def get_token_by_provider(self, provider: str) -> dict | None:
        """按提供商获取最新 Token (解密)

        Args:
            provider: 提供商名称

        Returns:
            Token dict 或 None
        """
        async with async_session() as session:
            stmt = (
                select(OauthToken)
                .where(OauthToken.provider == provider)
                .order_by(OauthToken.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            token = result.scalars().first()
            if token is None:
                return None
            return _token_to_dict(token)

    async def list_tokens(self, provider: str | None = None) -> list[dict]:
        """列出 Token

        Args:
            provider: 可选,按提供商过滤

        Returns:
            Token dict 列表 (已解密)
        """
        async with async_session() as session:
            stmt = select(OauthToken).order_by(OauthToken.created_at.desc())
            if provider:
                stmt = stmt.where(OauthToken.provider == provider)
            result = await session.execute(stmt)
            return [_token_to_dict(t) for t in result.scalars().all()]

    async def refresh_token(self, token_id: int) -> dict | None:
        """刷新 Token

        从提供商的 token_url 发起 refresh_token 请求,
        成功后更新数据库中的 Token。

        Args:
            token_id: Token ID

        Returns:
            刷新后的 Token dict,或 None (Token 不存在 / 无 refresh_token / 刷新失败)
        """
        # 延迟导入,避免循环依赖
        from .oauth_service import PROVIDER_CONFIGS, OAuthService

        async with async_session() as session:
            token = await session.get(OauthToken, token_id)
            if token is None:
                return None

            if not token.refresh_token:
                return None

            provider = token.provider
            config = PROVIDER_CONFIGS.get(provider)
            if config is None:
                return None

            # 获取 client 凭证
            oauth_svc = OAuthService()
            creds = oauth_svc._get_client_credentials(provider)
            if creds is None:
                return None
            client_id, client_secret = creds

            refresh_token_plain = _decrypt_token(token.refresh_token)

            # 构建 refresh 请求
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token_plain,
            }

            token_url = config["token_url"]
            headers = {"Accept": "application/json"}
            # GitHub 要求 Accept 头
            if provider == "github":
                headers["Accept"] = "application/json"

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(token_url, data=data, headers=headers)
            except Exception:
                return None

            if resp.status_code != 200:
                return None

            try:
                token_data = resp.json()
            except Exception:
                return None

            new_access = token_data.get("access_token")
            if not new_access:
                return None

            # 更新字段
            token.access_token = _encrypt_token(new_access) or ""
            new_refresh = token_data.get("refresh_token")
            if new_refresh:
                token.refresh_token = _encrypt_token(new_refresh)
            new_token_type = token_data.get("token_type")
            if new_token_type:
                token.token_type = new_token_type
            new_scope = token_data.get("scope")
            if new_scope:
                token.scope = new_scope
            expires_in = token_data.get("expires_in")
            if expires_in:
                token.expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

            await session.commit()
            await session.refresh(token)
            return _token_to_dict(token)

    async def revoke_token(self, token_id: int) -> bool:
        """撤销 Token: 标记为过期 (保留记录)

        Args:
            token_id: Token ID

        Returns:
            True 表示成功, False 表示 Token 不存在
        """
        async with async_session() as session:
            token = await session.get(OauthToken, token_id)
            if token is None:
                return False
            # 标记为过期
            token.expires_at = datetime.utcnow()
            await session.commit()
            return True

    async def delete_token(self, token_id: int) -> bool:
        """删除 Token

        Args:
            token_id: Token ID

        Returns:
            True 表示成功, False 表示 Token 不存在
        """
        async with async_session() as session:
            token = await session.get(OauthToken, token_id)
            if token is None:
                return False
            await session.delete(token)
            await session.commit()
            return True

    def is_expired(self, token: dict) -> bool:
        """检查 Token 是否过期

        Args:
            token: Token dict (含 expires_at 字段)

        Returns:
            True 表示已过期或无过期时间(保守判断), False 表示有效
        """
        expires_at = token.get("expires_at")
        if not expires_at:
            # 无过期时间,保守视为未过期 (部分 provider 不返回 expires_in)
            return False
        try:
            exp_dt = datetime.fromisoformat(expires_at)
        except (ValueError, TypeError):
            return False
        return datetime.utcnow() >= exp_dt


# 模块级单例
token_manager = TokenManager()
