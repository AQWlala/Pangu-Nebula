"""飞书消息桥接服务 (Phase 9C)

支持两种接入模式:
1. Webhook 发送(无需 lark-oapi,仅依赖 httpx):
   - send_text: 通过自定义机器人 Webhook 发送文本
   - send_card: 通过 Webhook 发送卡片消息
   - send_interactive: 通过 Webhook 发送交互卡片(elements)
2. 事件订阅(需 lark-oapi,可选):
   - verify_webhook: 验证事件订阅签名
   - handle_event: 处理飞书事件回调

设计说明:
- 凭证(app_id / app_secret / verification_token)存储在内存中
- Webhook 发送使用 httpx async,不依赖 lark-oapi
- lark-oapi 未安装时,高级功能(事件订阅)不可用,但 Webhook 发送仍可用

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- 飞书开放平台 Webhook 与事件订阅规范
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

# 可选依赖: lark-oapi(飞书官方 SDK,用于事件订阅等高级功能)
try:
    import lark_oapi as lark  # type: ignore
    HAS_LARK = True
except ImportError:
    HAS_LARK = False


def _not_installed_lark() -> dict:
    """未安装 lark-oapi 时的统一错误响应"""
    return {"ok": False, "data": None, "error": "lark-oapi 库未安装,高级功能不可用"}


class FeishuChannel:
    """飞书渠道桥接服务

    - Webhook 发送: 仅依赖 httpx(始终可用)
    - 事件订阅: 依赖 lark-oapi(可选)
    - 凭证存储在内存中(进程重启后需重新配置)
    """

    def __init__(self) -> None:
        self._app_id: str | None = None
        self._app_secret: str | None = None
        self._verification_token: str | None = None
        self._client: Any = None  # lark-oapi Client(可选)

    # ===== 凭证配置 =====

    def configure(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str = "",
    ) -> dict:
        """配置飞书应用凭证

        - app_id: 飞书应用 App ID
        - app_secret: 飞书应用 App Secret
        - verification_token: 事件订阅校验 Token(可选,用于事件签名校验)
        """
        self._app_id = app_id
        self._app_secret = app_secret
        self._verification_token = verification_token

        # 如果 lark-oapi 可用,创建 Client
        if HAS_LARK:
            try:
                self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
            except Exception:
                self._client = None

        return {
            "ok": True,
            "configured": True,
            "app_id": app_id,
            "has_lark": HAS_LARK,
            "error": None,
        }

    # ===== Webhook 发送(httpx async,不依赖 lark-oapi)=====

    async def send_text(self, webhook_url: str, text: str) -> dict:
        """通过 Webhook 发送文本消息

        - webhook_url: 飞书自定义机器人 Webhook 地址
        - text: 文本内容
        """
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        return await self._post_webhook(webhook_url, payload, msg_type="text")

    async def send_card(self, webhook_url: str, card: dict) -> dict:
        """通过 Webhook 发送卡片消息

        - card: 飞书卡片 JSON(包含 header/elements 等)
        """
        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        return await self._post_webhook(webhook_url, payload, msg_type="card")

    async def send_interactive(self, webhook_url: str, elements: list) -> dict:
        """通过 Webhook 发送交互卡片(elements 列表)

        - elements: 卡片元素列表,会自动包装为卡片结构
        """
        card = {
            "elements": elements,
        }
        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        return await self._post_webhook(webhook_url, payload, msg_type="interactive")

    async def _post_webhook(
        self,
        webhook_url: str,
        payload: dict,
        msg_type: str = "text",
    ) -> dict:
        """发送 Webhook 请求(内部)

        飞书 Webhook 返回格式:
        {"code": 0, "msg": "success", "data": {...}}
        - code=0 表示成功
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "ok": False,
                "channel": "feishu",
                "msg_type": msg_type,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except httpx.RequestError as e:
            return {
                "ok": False,
                "channel": "feishu",
                "msg_type": msg_type,
                "error": f"请求失败: {e}",
            }
        except Exception as e:
            return {
                "ok": False,
                "channel": "feishu",
                "msg_type": msg_type,
                "error": f"解析响应失败: {e}",
            }

        # 飞书 Webhook 返回 code 字段,0 表示成功
        code = data.get("code", -1) if isinstance(data, dict) else -1
        msg_id = None
        if isinstance(data, dict):
            inner = data.get("data") or {}
            if isinstance(inner, dict):
                msg_id = inner.get("message_id") or inner.get("msg_id")

        if code == 0:
            return {
                "ok": True,
                "channel": "feishu",
                "target": webhook_url,
                "msg_type": msg_type,
                "msg_id": msg_id,
                "error": None,
            }
        return {
            "ok": False,
            "channel": "feishu",
            "msg_type": msg_type,
            "error": data.get("msg", "unknown error") if isinstance(data, dict) else str(data),
        }

    # ===== 事件订阅(依赖 lark-oapi)=====

    def verify_webhook(self, token: str, timestamp: str, signature: str) -> bool:
        """验证飞书 Webhook 事件签名

        飞书事件订阅签名规则:
        - 拼接: timestamp + "\n" + app_secret
        - 使用 HMAC-SHA256 计算,然后 base64 编码
        - 与请求头中的 X-Lark-Signature 比较

        Args:
            token: 请求体中的 token(校验 verification_token)
            timestamp: 请求头 X-Lark-Request-Timestamp
            signature: 请求头 X-Lark-Signature

        Returns:
            True 表示校验通过
        """
        # 先校验 verification_token(如果已配置)
        if self._verification_token and token and token != self._verification_token:
            return False

        if not self._app_secret:
            return False

        # 计算签名: HMAC-SHA256(timestamp + "\n" + app_secret)
        string_to_sign = f"{timestamp}\n{self._app_secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        # 飞书签名是 base64 编码
        import base64
        expected = base64.b64encode(hmac_code).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    def handle_event(self, event: dict) -> dict:
        """处理飞书事件回调

        - event: 飞书事件回调 JSON
        - 返回统一格式 {ok, type, data, error}

        对于 URL 校验(challenge)请求,返回 challenge 响应。
        对于其他事件,提取事件类型和数据。
        """
        # URL 校验(challenge)请求
        if "challenge" in event:
            return {
                "ok": True,
                "type": "url_verification",
                "challenge": event.get("challenge"),
                "data": None,
                "error": None,
            }

        # 事件类型取决于 schema(飞书 1.0 / 2.0)
        header = event.get("header") or {}
        event_type = header.get("event_type") or event.get("type")
        event_data = event.get("event") or event.get("data")

        if not HAS_LARK:
            # 未安装 lark-oapi 时,仅做格式转换
            return {
                "ok": True,
                "type": event_type,
                "data": event_data,
                "error": None,
                "note": "lark-oapi 未安装,未做高级事件处理",
            }

        # lark-oapi 可用时,可以做更详细的事件处理
        # 这里仅做格式统一,具体业务逻辑由上层 handler 决定
        return {
            "ok": True,
            "type": event_type,
            "data": event_data,
            "header": header,
            "error": None,
        }

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取飞书渠道状态

        返回 {configured, app_id, has_lark}
        """
        return {
            "ok": True,
            "configured": self._app_id is not None,
            "app_id": self._app_id,
            "has_lark": HAS_LARK,
            "error": None if HAS_LARK else "lark-oapi 库未安装,事件订阅不可用(Webhook 发送仍可用)",
        }
