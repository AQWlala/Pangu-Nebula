"""Discord Webhook 消息桥接服务 (Phase 9C)

使用 Discord Webhook (最简模式,不需要 discord.py 库)发送消息。
- 仅依赖 httpx(始终可用)
- 无 webhook 时,send_text/send_embed 返回 mock 响应,便于开发与测试
- 凭证(webhook_url)存储在内存中(进程重启后需重新配置)

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- Discord Webhook 官方文档
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class DiscordChannel:
    """Discord Bot 渠道服务

    - configure(webhook_url): 配置 Webhook URL
    - send_text(text): 通过 Webhook 发送文本
    - send_embed(embed): 通过 Webhook 发送嵌入消息
    - get_status(): 获取状态
    """

    def __init__(self) -> None:
        self._webhook_url: str | None = os.environ.get("NEBULA_DISCORD_WEBHOOK") or None

    # ===== 凭证配置 =====

    def configure(self, webhook_url: str) -> dict:
        """配置 Discord Webhook URL

        - webhook_url: Discord 频道 Webhook 地址
          (格式: https://discord.com/api/webhooks/<id>/<token>)
        """
        self._webhook_url = webhook_url
        return {
            "ok": True,
            "configured": True,
            "webhook_set": True,
            "error": None,
        }

    # ===== 发送消息 =====

    async def send_text(self, text: str) -> dict:
        """通过 Webhook 发送文本消息

        - text: 文本内容
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(text=text)

        payload = {"content": text}
        return await self._post_webhook(payload, msg_type="text")

    async def send_embed(self, embed: dict) -> dict:
        """通过 Webhook 发送嵌入消息

        - embed: Discord embed JSON(包含 title/description/color/fields 等)
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(embed=embed)

        payload = {"embeds": [embed]}
        return await self._post_webhook(payload, msg_type="embed")

    # ===== 内部辅助 =====

    async def _post_webhook(self, payload: dict, msg_type: str = "text") -> dict:
        """发送 Webhook 请求(内部)

        Discord Webhook 返回:
        - 成功: 204 No Content(空 body)或 200 + 消息对象
        - 失败: 4xx + JSON 错误体
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                # Discord 成功时返回 204(无 body)或 200
                if resp.status_code not in (200, 204):
                    resp.raise_for_status()
                # 204 时无响应体
                try:
                    data = resp.json()
                except Exception:
                    data = None
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "channel": "discord",
                "msg_type": msg_type,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "channel": "discord",
                "msg_type": msg_type,
                "error": f"请求失败: {e}",
            }
        except Exception as e:
            return {
                "ok": False,
                "channel": "discord",
                "msg_type": msg_type,
                "error": f"解析响应失败: {e}",
            }

        # Discord 成功响应可能为空(204)或包含消息对象
        msg_id = None
        if isinstance(data, dict):
            msg_id = data.get("id")

        return {
            "ok": True,
            "channel": "discord",
            "msg_type": msg_type,
            "msg_id": msg_id,
            "error": None,
        }

    @staticmethod
    def _mock_response(text: str | None = None, embed: dict | None = None) -> dict:
        """无 webhook 时的 mock 响应(便于开发与测试)"""
        data: dict[str, Any] = {"mock": True}
        if text is not None:
            data["text"] = text
        if embed is not None:
            data["embed"] = embed
        return {
            "ok": True,
            "channel": "discord",
            "data": data,
            "error": None,
        }

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取 Discord 渠道状态

        返回 {ok, configured, webhook_set, error}
        """
        return {
            "ok": True,
            "configured": self._webhook_url is not None,
            "webhook_set": self._webhook_url is not None,
            "error": None if self._webhook_url is not None else "未配置 Discord Webhook URL(send_text/send_embed 将返回 mock 响应)",
        }
