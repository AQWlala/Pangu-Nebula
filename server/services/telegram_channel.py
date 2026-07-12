"""Telegram Bot 消息桥接服务 (Phase 9C)

使用 Telegram Bot API (https://api.telegram.org/bot<token>/...) 发送消息。
- 仅依赖 httpx(始终可用)
- 无 token 时,send_text/send_photo 返回 mock 响应,便于开发与测试
- 凭证(token)存储在内存中(进程重启后需重新配置)

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- Telegram Bot API 官方文档
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class TelegramChannel:
    """Telegram Bot 渠道服务

    - configure(token): 配置 Bot Token
    - send_text(chat_id, text): 发送文本
    - send_photo(chat_id, photo_url): 发送图片
    - get_status(): 获取状态
    - get_me(): 获取 Bot 信息
    """

    API_BASE = "https://api.telegram.org"

    def __init__(self) -> None:
        self._token: str | None = os.environ.get("NEBULA_TELEGRAM_TOKEN") or None

    # ===== 凭证配置 =====

    def configure(self, token: str) -> dict:
        """配置 Telegram Bot Token

        - token: Telegram Bot API Token(从 @BotFather 获取)
        """
        self._token = token
        return {
            "ok": True,
            "configured": True,
            "token_set": True,
            "error": None,
        }

    # ===== 发送消息 =====

    async def send_text(self, chat_id: str | int, text: str) -> dict:
        """发送文本消息

        - chat_id: 目标聊天 ID(用户/群组/频道)
        - text: 文本内容
        - 无 token 时返回 mock 响应
        """
        if not self._token:
            return self._mock_response(chat_id, text=text)

        url = f"{self.API_BASE}/bot{self._token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        return await self._post(url, payload, msg_type="text", chat_id=chat_id)

    async def send_photo(self, chat_id: str | int, photo_url: str) -> dict:
        """发送图片消息

        - chat_id: 目标聊天 ID
        - photo_url: 图片 URL(Telegram 会下载并发送)
        - 无 token 时返回 mock 响应
        """
        if not self._token:
            return self._mock_response(chat_id, photo=photo_url)

        url = f"{self.API_BASE}/bot{self._token}/sendPhoto"
        payload = {"chat_id": chat_id, "photo": photo_url}
        return await self._post(url, payload, msg_type="photo", chat_id=chat_id)

    async def get_me(self) -> dict:
        """获取 Bot 信息(验证 token 有效性)

        返回 {ok, bot_info, error}
        """
        if not self._token:
            return {
                "ok": False,
                "bot_info": None,
                "error": "未配置 Telegram Bot Token",
            }

        url = f"{self.API_BASE}/bot{self._token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "bot_info": None,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "bot_info": None,
                "error": f"请求失败: {e}",
            }

        if isinstance(data, dict) and data.get("ok"):
            return {
                "ok": True,
                "bot_info": data.get("result"),
                "error": None,
            }
        return {
            "ok": False,
            "bot_info": None,
            "error": data.get("description", "unknown error") if isinstance(data, dict) else str(data),
        }

    # ===== 内部辅助 =====

    async def _post(
        self,
        url: str,
        payload: dict,
        msg_type: str = "text",
        chat_id: str | int | None = None,
    ) -> dict:
        """发送 API 请求(内部)

        Telegram Bot API 返回格式:
        {"ok": true, "result": {"message_id": ..., "chat": {...}, ...}}
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "channel": "telegram",
                "msg_type": msg_type,
                "chat_id": chat_id,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "channel": "telegram",
                "msg_type": msg_type,
                "chat_id": chat_id,
                "error": f"请求失败: {e}",
            }
        except Exception as e:
            return {
                "ok": False,
                "channel": "telegram",
                "msg_type": msg_type,
                "chat_id": chat_id,
                "error": f"解析响应失败: {e}",
            }

        if isinstance(data, dict) and data.get("ok"):
            result = data.get("result") or {}
            msg_id = result.get("message_id") if isinstance(result, dict) else None
            return {
                "ok": True,
                "channel": "telegram",
                "msg_type": msg_type,
                "chat_id": chat_id,
                "msg_id": msg_id,
                "error": None,
            }
        return {
            "ok": False,
            "channel": "telegram",
            "msg_type": msg_type,
            "chat_id": chat_id,
            "error": data.get("description", "unknown error") if isinstance(data, dict) else str(data),
        }

    @staticmethod
    def _mock_response(chat_id: str | int, text: str | None = None, photo: str | None = None) -> dict:
        """无 token 时的 mock 响应(便于开发与测试)"""
        data: dict[str, Any] = {"mock": True, "chat_id": chat_id}
        if text is not None:
            data["text"] = text
        if photo is not None:
            data["photo"] = photo
        return {
            "ok": True,
            "channel": "telegram",
            "data": data,
            "error": None,
        }

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取 Telegram 渠道状态

        返回 {ok, configured, token_set, error}
        """
        return {
            "ok": True,
            "configured": self._token is not None,
            "token_set": self._token is not None,
            "error": None if self._token is not None else "未配置 Telegram Bot Token(send_text/send_photo 将返回 mock 响应)",
        }
