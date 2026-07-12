"""钉钉机器人消息桥接服务 (Phase 9C)

使用钉钉自定义机器人 Webhook 发送消息。
- 仅依赖 httpx(始终可用)
- 支持加签安全设置(通过 secret 计算 timestamp + sign)
- 无 webhook 时,send_text/send_markdown/send_action_card 返回 mock 响应
- 凭证(webhook_url / secret)存储在内存中(进程重启后需重新配置)

钉钉自定义机器人 Webhook:
    POST https://oapi.dingtalk.com/robot/send?access_token=xxx&timestamp=xxx&sign=xxx

加签规则:
    sign = base64(hmac_sha256(secret, timestamp + "\n" + secret))

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- 钉钉开放平台自定义机器人文档
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import urllib.parse
from typing import Any

import httpx


class DingTalkChannel:
    """钉钉机器人渠道服务

    - configure(webhook_url, secret): 配置 Webhook 和签名密钥
    - send_text(text): 发送文本
    - send_markdown(title, text): 发送 Markdown
    - send_action_card(card): 发送 ActionCard
    - get_status(): 获取状态
    """

    API_BASE = "https://oapi.dingtalk.com/robot/send"

    def __init__(self) -> None:
        self._webhook_url: str | None = os.environ.get("NEBULA_DINGTALK_WEBHOOK") or None
        self._secret: str | None = os.environ.get("NEBULA_DINGTALK_SECRET") or None

    # ===== 凭证配置 =====

    def configure(self, webhook_url: str, secret: str = "") -> dict:
        """配置钉钉机器人 Webhook 和签名密钥

        - webhook_url: 钉钉自定义机器人 Webhook 地址
          (格式: https://oapi.dingtalk.com/robot/send?access_token=xxx)
        - secret: 加签密钥(SECRET),如果机器人启用了加签安全设置则需要
        """
        self._webhook_url = webhook_url
        self._secret = secret or None
        return {
            "ok": True,
            "configured": True,
            "webhook_set": True,
            "secret_set": self._secret is not None,
            "error": None,
        }

    # ===== 发送消息 =====

    async def send_text(self, text: str) -> dict:
        """发送文本消息

        - text: 文本内容
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(text=text)

        payload = {
            "msgtype": "text",
            "text": {"content": text},
        }
        return await self._post(payload, msg_type="text")

    async def send_markdown(self, title: str, text: str) -> dict:
        """发送 Markdown 消息

        - title: 消息标题(会话列表中展示)
        - text: Markdown 内容
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(title=title, text=text)

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
        return await self._post(payload, msg_type="markdown")

    async def send_action_card(self, card: dict) -> dict:
        """发送 ActionCard 消息

        - card: ActionCard JSON
          (包含 title/text/btns/btnOrientation 等字段)
        - 无 webhook 时返回 mock 响应
        """
        if not self._webhook_url:
            return self._mock_response(card=card)

        payload = {
            "msgtype": "actionCard",
            "actionCard": card,
        }
        return await self._post(payload, msg_type="actionCard")

    # ===== 内部辅助 =====

    def _build_url(self) -> str:
        """构建带签名的 Webhook URL

        钉钉加签规则:
        - timestamp: 毫秒级时间戳
        - sign = base64(hmac_sha256(secret, timestamp + "\\n" + secret))
        - URL 追加 &timestamp=xxx&sign=xxx(需 URL 编码)
        """
        if not self._webhook_url:
            return ""

        url = self._webhook_url
        if not self._secret:
            return url

        timestamp = str(int(round(time.time() * 1000)))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))

        # 拼接 timestamp 和 sign 参数
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}timestamp={timestamp}&sign={sign}"
        return url

    async def _post(self, payload: dict, msg_type: str = "text") -> dict:
        """发送 Webhook 请求(内部)

        钉钉机器人返回格式:
        {"errcode": 0, "errmsg": "ok", ...}
        - errcode=0 表示成功
        """
        url = self._build_url()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "channel": "dingtalk",
                "msg_type": msg_type,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "channel": "dingtalk",
                "msg_type": msg_type,
                "error": f"请求失败: {e}",
            }
        except Exception as e:
            return {
                "ok": False,
                "channel": "dingtalk",
                "msg_type": msg_type,
                "error": f"解析响应失败: {e}",
            }

        # 钉钉返回 errcode 字段,0 表示成功
        errcode = data.get("errcode", -1) if isinstance(data, dict) else -1
        if errcode == 0:
            return {
                "ok": True,
                "channel": "dingtalk",
                "msg_type": msg_type,
                "msgid": data.get("msgid") if isinstance(data, dict) else None,
                "error": None,
            }
        errmsg = data.get("errmsg", "unknown error") if isinstance(data, dict) else str(data)
        return {
            "ok": False,
            "channel": "dingtalk",
            "msg_type": msg_type,
            "error": errmsg,
        }

    @staticmethod
    def _mock_response(
        text: str | None = None,
        title: str | None = None,
        card: dict | None = None,
    ) -> dict:
        """无 webhook 时的 mock 响应(便于开发与测试)"""
        data: dict[str, Any] = {"mock": True}
        if text is not None:
            data["text"] = text
        if title is not None:
            data["title"] = title
        if card is not None:
            data["card"] = card
        return {
            "ok": True,
            "channel": "dingtalk",
            "data": data,
            "error": None,
        }

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取钉钉渠道状态

        返回 {ok, configured, webhook_set, secret_set, error}
        """
        return {
            "ok": True,
            "configured": self._webhook_url is not None,
            "webhook_set": self._webhook_url is not None,
            "secret_set": self._secret is not None,
            "error": None if self._webhook_url is not None else "未配置钉钉 Webhook URL(send_text/send_markdown/send_action_card 将返回 mock 响应)",
        }
