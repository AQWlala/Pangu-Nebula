"""企业微信群机器人消息桥接服务 (T3.7)

使用企业微信群机器人 Webhook 发送消息。
- 仅依赖 httpx(始终可用)
- 无 webhook 时,send_text/send_markdown/send_text_card 返回 mock 响应
- 凭证(webhook_url)存储在内存中(进程重启后需重新配置)

企业微信群机器人 Webhook:
    POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

消息类型:
- text: 文本消息(支持 @userid 列表)
- markdown: Markdown 消息
- textcard: 文本卡片消息

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- 企业微信群机器人官方文档
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class WeComChannel:
    """企业微信机器人渠道服务

    - configure(webhook_url): 配置 Webhook
    - send_text(text): 发送文本
    - send_markdown(content): 发送 Markdown
    - send_text_card(card): 发送文本卡片
    - get_status(): 获取状态
    """

    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

    def __init__(self) -> None:
        self._webhook_url: str | None = os.environ.get("NEBULA_WECOM_WEBHOOK") or None

    # ===== 凭证配置 =====

    def configure(self, webhook_url: str) -> dict:
        """配置企业微信群机器人 Webhook

        - webhook_url: 企业微信群机器人 Webhook 地址
          (格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx)
        """
        self._webhook_url = webhook_url
        return {
            "ok": True,
            "configured": True,
            "webhook_set": True,
            "error": None,
        }

    # ===== 发送消息 =====

    async def send_text(self, text: str, mentioned_list: list[str] | None = None) -> dict:
        """发送文本消息

        - text: 文本内容
        - mentioned_list: 需要 @ 的企业微信用户 userid 列表(@all 表示 @所有人)
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(text=text)

        payload = {
            "msgtype": "text",
            "text": {
                "content": text,
                "mentioned_list": mentioned_list or [],
            },
        }
        return await self._post(payload, msg_type="text")

    async def send_markdown(self, content: str) -> dict:
        """发送 Markdown 消息

        - content: Markdown 内容
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(content=content)

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        return await self._post(payload, msg_type="markdown")

    async def send_text_card(self, card: dict) -> dict:
        """发送文本卡片消息

        - card: 文本卡片 JSON
          (包含 title/description/url/btntxt 等字段)
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(card=card)

        payload = {
            "msgtype": "textcard",
            "textcard": card,
        }
        return await self._post(payload, msg_type="textcard")

    # ===== 内部辅助 =====

    async def _post(self, payload: dict, msg_type: str = "text") -> dict:
        """发送 Webhook 请求(内部)

        企业微信群机器人返回格式:
        {"errcode": 0, "errmsg": "ok", ...}
        - errcode=0 表示成功
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "channel": "wecom",
                "msg_type": msg_type,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "channel": "wecom",
                "msg_type": msg_type,
                "error": f"请求失败: {e}",
            }
        except Exception as e:
            return {
                "ok": False,
                "channel": "wecom",
                "msg_type": msg_type,
                "error": f"解析响应失败: {e}",
            }

        # 企业微信返回 errcode 字段,0 表示成功
        errcode = data.get("errcode", -1) if isinstance(data, dict) else -1
        if errcode == 0:
            return {
                "ok": True,
                "channel": "wecom",
                "msg_type": msg_type,
                "msgid": data.get("msgid") if isinstance(data, dict) else None,
                "error": None,
            }
        errmsg = data.get("errmsg", "unknown error") if isinstance(data, dict) else str(data)
        return {
            "ok": False,
            "channel": "wecom",
            "msg_type": msg_type,
            "error": errmsg,
        }

    @staticmethod
    def _mock_response(
        text: str | None = None,
        content: str | None = None,
        card: dict | None = None,
    ) -> dict:
        """无 webhook 时的 mock 响应(便于开发与测试)"""
        data: dict[str, Any] = {"mock": True}
        if text is not None:
            data["text"] = text
        if content is not None:
            data["content"] = content
        if card is not None:
            data["card"] = card
        return {
            "ok": True,
            "channel": "wecom",
            "data": data,
            "error": None,
        }

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取企业微信渠道状态

        返回 {ok, configured, webhook_set, error}
        """
        return {
            "ok": True,
            "configured": self._webhook_url is not None,
            "webhook_set": self._webhook_url is not None,
            "error": None if self._webhook_url is not None else "未配置企业微信 Webhook URL(send_text/send_markdown/send_text_card 将返回 mock 响应)",
        }
