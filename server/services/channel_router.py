"""IM 渠道统一路由服务 (Phase 9C)

负责微信 / 飞书渠道的统一消息格式转换与分发。

统一消息格式(发送/接收):
    {
        "from": "user_id",         # 发送方
        "to": "target_id",         # 接收方(用户ID/群ID/Webhook URL)
        "content": "文本内容",
        "timestamp": 1234567890,   # Unix 时间戳(秒)
        "type": "text"             # text/image/card/interactive
    }

设计说明:
- 模块级单例: `channel_router = ChannelRouter()`
- 内部维护 `wechat = WeChatChannel()` 和 `feishu = FeishuChannel()` 实例
- 使用 `from ..db.engine import async_session` 读写 Channel 表
- 由于多智能体不能同时修改 orm.py,额外的字段(name/webhook_url/avatar/
  last_message_at)存储在 Channel.config JSON 中,而不是新增 ORM 列

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- awesome-llm-apps 的多渠道接入模式
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import Channel
from .dingtalk_channel import DingTalkChannel
from .discord_channel import DiscordChannel
from .feishu_channel import FeishuChannel
from .telegram_channel import TelegramChannel
from .wechat_channel import WeChatChannel
from .wecom_channel import WeComChannel


# 支持的渠道类型
SUPPORTED_TYPES: list[str] = ["wechat", "feishu", "telegram", "discord", "dingtalk", "wecom"]


class ChannelRouter:
    """IM 渠道统一路由

    - 统一发送: send_message(channel_type, target, content, msg_type)
    - 统一接收: receive_message(channel_type, raw_message)
    - 渠道 CRUD: register_channel / update_channel / delete_channel / get_channel / list_channels
    - 测试连通性: test_channel(channel_id)
    """

    def __init__(self) -> None:
        # 内部维护的渠道实例(单例)
        self.wechat: WeChatChannel = WeChatChannel()
        self.feishu: FeishuChannel = FeishuChannel()
        self.telegram: TelegramChannel = TelegramChannel()
        self.discord: DiscordChannel = DiscordChannel()
        self.dingtalk: DingTalkChannel = DingTalkChannel()
        self.wecom: WeComChannel = WeComChannel()

    # ===== 渠道实例访问 =====

    def get_supported_types(self) -> list[str]:
        """返回支持的渠道类型列表"""
        return list(SUPPORTED_TYPES)

    # ===== 统一发送 / 接收 =====

    async def send_message(
        self,
        channel_type: str,
        target: str,
        content: str,
        msg_type: str = "text",
    ) -> dict:
        """统一发送接口

        - channel_type: wechat / feishu
        - target: 微信用户名 / 飞书 Webhook URL
        - content: 文本内容(对于 card 类型,应为 JSON 字符串或 dict)
        - msg_type: text / image / card / interactive

        返回 {ok, channel, target, msg_id, error}
        """
        if channel_type not in SUPPORTED_TYPES:
            return {
                "ok": False,
                "channel": channel_type,
                "target": target,
                "error": f"不支持的渠道类型: {channel_type}(支持: {SUPPORTED_TYPES})",
            }

        if channel_type == "wechat":
            return self._send_wechat(target, content, msg_type)
        if channel_type == "feishu":
            return await self._send_feishu(target, content, msg_type)

        # 兜底(理论上不会到达)
        return {"ok": False, "channel": channel_type, "target": target, "error": "未知渠道"}

    def _send_wechat(self, target: str, content: str, msg_type: str) -> dict:
        """微信发送(同步,因为 itchat 是同步库)"""
        if msg_type == "text":
            result = self.wechat.send_message(target, content)
        elif msg_type == "image":
            # content 视为图片路径
            result = self.wechat.send_image(target, content)
        else:
            return {
                "ok": False,
                "channel": "wechat",
                "target": target,
                "error": f"微信暂不支持的消息类型: {msg_type}",
            }

        # 统一返回字段
        return {
            "ok": result.get("ok", False),
            "channel": "wechat",
            "target": target,
            "msg_id": result.get("msg_id"),
            "error": result.get("error"),
        }

    async def _send_feishu(self, target: str, content: str, msg_type: str) -> dict:
        """飞书发送(target 视为 Webhook URL)"""
        if msg_type == "text":
            result = await self.feishu.send_text(target, content)
        elif msg_type == "card":
            # content 是卡片 JSON,尝试解析
            card = self._parse_card_content(content)
            if card is None:
                return {
                    "ok": False,
                    "channel": "feishu",
                    "target": target,
                    "error": "card 类型消息的 content 必须是有效的 JSON",
                }
            result = await self.feishu.send_card(target, card)
        elif msg_type == "interactive":
            elements = self._parse_card_content(content)
            if not isinstance(elements, list):
                return {
                    "ok": False,
                    "channel": "feishu",
                    "target": target,
                    "error": "interactive 类型消息的 content 必须是 JSON 数组",
                }
            result = await self.feishu.send_interactive(target, elements)
        else:
            return {
                "ok": False,
                "channel": "feishu",
                "target": target,
                "error": f"飞书暂不支持的消息类型: {msg_type}",
            }

        return {
            "ok": result.get("ok", False),
            "channel": "feishu",
            "target": target,
            "msg_id": result.get("msg_id"),
            "error": result.get("error"),
        }

    @staticmethod
    def _parse_card_content(content: str | dict | list) -> Any:
        """将 content 解析为 dict/list

        - 如果已经是 dict/list,直接返回
        - 如果是字符串,尝试 JSON 解析
        - 解析失败返回 None
        """
        if isinstance(content, (dict, list)):
            return content
        if isinstance(content, str):
            try:
                import json
                return json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    def receive_message(self, channel_type: str, raw_message: dict) -> dict:
        """统一接收接口

        将渠道特定的原始消息转换为统一格式:
            {from, to, content, timestamp, type, channel, raw}

        - channel_type: wechat / feishu
        - raw_message: 渠道原始消息体

        返回 {ok, channel, from, to, content, timestamp, type, raw, error}
        """
        if channel_type not in SUPPORTED_TYPES:
            return {
                "ok": False,
                "channel": channel_type,
                "error": f"不支持的渠道类型: {channel_type}",
            }

        if channel_type == "wechat":
            return self._receive_wechat(raw_message)
        if channel_type == "feishu":
            return self._receive_feishu(raw_message)
        return {"ok": False, "channel": channel_type, "error": "未知渠道"}

    def _receive_wechat(self, raw: dict) -> dict:
        """微信消息归一化

        itchat 消息字段: FromUserName / ToUserName / Text|Content / CreateTime / Type
        """
        return {
            "ok": True,
            "channel": "wechat",
            "from": raw.get("FromUserName") or raw.get("from"),
            "to": raw.get("ToUserName") or raw.get("to"),
            "content": raw.get("Text") or raw.get("Content") or raw.get("content"),
            "timestamp": raw.get("CreateTime") or raw.get("timestamp"),
            "type": self._normalize_type(raw.get("Type") or raw.get("type") or "text"),
            "raw": raw,
            "error": None,
        }

    def _receive_feishu(self, raw: dict) -> dict:
        """飞书消息归一化

        飞书事件 2.0 schema:
            {
                "schema": "2.0",
                "header": {"event_type": "im.message.receive_v1", ...},
                "event": {"sender": {...}, "message": {"content": "...", ...}}
            }
        飞书事件 1.0 schema:
            {"type": "...", "data": {...}}
        """
        header = raw.get("header") or {}
        event_data = raw.get("event") or raw.get("data") or {}
        event_type = header.get("event_type") or raw.get("type")

        # 提取消息内容
        message = event_data.get("message") if isinstance(event_data, dict) else None
        sender = event_data.get("sender") if isinstance(event_data, dict) else None

        from_id = None
        to_id = None
        content = None
        msg_type = "text"

        if isinstance(sender, dict):
            sender_id = sender.get("sender_id") or {}
            from_id = sender_id.get("open_id") or sender_id.get("user_id")

        if isinstance(message, dict):
            to_id = message.get("chat_id")
            # message.content 是 JSON 字符串,如 {"text":"hello"}
            raw_content = message.get("content")
            msg_type = message.get("message_type") or "text"
            content = self._extract_feishu_content(raw_content, msg_type)

        # 对于 challenge 请求,单独处理
        if "challenge" in raw:
            return {
                "ok": True,
                "channel": "feishu",
                "type": "url_verification",
                "challenge": raw.get("challenge"),
                "raw": raw,
                "error": None,
            }

        return {
            "ok": True,
            "channel": "feishu",
            "from": from_id,
            "to": to_id,
            "content": content,
            "timestamp": header.get("create_time") or raw.get("timestamp"),
            "type": self._normalize_type(msg_type),
            "event_type": event_type,
            "raw": raw,
            "error": None,
        }

    @staticmethod
    def _extract_feishu_content(raw_content: Any, msg_type: str) -> Any:
        """从飞书 message.content 中提取文本

        飞书 message.content 是 JSON 字符串:
        - text: {"text": "hello"}
        - post: {"title": "...", "content": [[...]]}
        """
        if raw_content is None:
            return None
        if isinstance(raw_content, str):
            try:
                import json
                parsed = json.loads(raw_content)
            except (json.JSONDecodeError, ValueError):
                return raw_content
        else:
            parsed = raw_content
        if isinstance(parsed, dict):
            if msg_type == "text":
                return parsed.get("text")
            return parsed
        return parsed

    @staticmethod
    def _normalize_type(raw_type: str) -> str:
        """归一化消息类型为统一类型(text/image/video/card/interactive/other)"""
        if not raw_type:
            return "text"
        t = str(raw_type).lower()
        mapping = {
            "text": "text",
            "picture": "image",
            "image": "image",
            "video": "video",
            "file": "file",
            "post": "card",
            "interactive": "interactive",
        }
        return mapping.get(t, "other")

    # ===== Channel 表 CRUD(额外字段存于 config JSON)=====

    def _channel_to_dict(self, channel: Channel) -> dict:
        """ORM 对象转 dict(额外字段从 config JSON 提取)"""
        config = dict(channel.config) if channel.config else {}
        return {
            "id": channel.id,
            "type": channel.type,
            "name": config.get("name") or f"{channel.type}-{channel.id}",
            "webhook_url": config.get("webhook_url"),
            "avatar": config.get("avatar"),
            "last_message_at": config.get("last_message_at"),
            "config": config,
            "enabled": bool(channel.enabled),
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
        }

    async def list_channels(self) -> list[dict]:
        """列出所有已配置的渠道"""
        async with async_session() as session:
            stmt = select(Channel).order_by(Channel.created_at.desc())
            result = await session.execute(stmt)
            return [self._channel_to_dict(ch) for ch in result.scalars().all()]

    async def register_channel(
        self,
        name: str,
        channel_type: str,
        config: dict,
    ) -> dict:
        """注册新渠道到 DB

        - name: 渠道名称(存于 config.name)
        - channel_type: wechat / feishu
        - config: 渠道配置(可包含 webhook_url / avatar 等)
        """
        if channel_type not in SUPPORTED_TYPES:
            return {
                "ok": False,
                "error": f"不支持的渠道类型: {channel_type}(支持: {SUPPORTED_TYPES})",
            }

        # 将 name 注入 config
        merged_config = dict(config) if config else {}
        merged_config["name"] = name
        # 记录注册时间
        merged_config.setdefault("registered_at", datetime.utcnow().isoformat())

        async with async_session() as session:
            channel = Channel(
                type=channel_type,
                config=merged_config,
                enabled=True,
            )
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            return self._channel_to_dict(channel)

    async def update_channel(self, channel_id: int, config: dict) -> dict | None:
        """更新渠道配置

        - channel_id: 渠道 ID
        - config: 新的配置(会与现有 config 合并)

        返回更新后的渠道 dict,如果渠道不存在返回 None
        """
        async with async_session() as session:
            channel = await session.get(Channel, channel_id)
            if channel is None:
                return None

            existing_config = dict(channel.config) if channel.config else {}
            # 合并新配置(浅合并)
            for k, v in (config or {}).items():
                existing_config[k] = v

            channel.config = existing_config
            await session.commit()
            await session.refresh(channel)
            return self._channel_to_dict(channel)

    async def delete_channel(self, channel_id: int) -> bool:
        """删除渠道

        返回 True 表示删除成功,False 表示渠道不存在
        """
        async with async_session() as session:
            channel = await session.get(Channel, channel_id)
            if channel is None:
                return False
            await session.delete(channel)
            await session.commit()
            return True

    async def get_channel(self, channel_id: int) -> dict | None:
        """获取单个渠道

        返回渠道 dict 或 None(不存在时)
        """
        async with async_session() as session:
            channel = await session.get(Channel, channel_id)
            return self._channel_to_dict(channel) if channel else None

    async def test_channel(self, channel_id: int) -> dict:
        """测试渠道连通性

        - 对于飞书 Webhook:发送一条测试文本消息
        - 对于微信:返回登录状态
        - 返回 {ok, channel_id, type, result, error}
        """
        channel = await self.get_channel(channel_id)
        if channel is None:
            return {"ok": False, "channel_id": channel_id, "error": "渠道不存在"}

        channel_type = channel["type"]
        config = channel.get("config") or {}

        if channel_type == "wechat":
            status = self.wechat.get_status()
            return {
                "ok": status.get("has_itchat", False) and status.get("logged_in", False),
                "channel_id": channel_id,
                "type": "wechat",
                "result": status,
                "error": status.get("error"),
            }

        if channel_type == "feishu":
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                return {
                    "ok": False,
                    "channel_id": channel_id,
                    "type": "feishu",
                    "error": "渠道配置中缺少 webhook_url",
                }
            # 发送一条测试消息
            result = await self.feishu.send_text(webhook_url, "【Pangu Nebula】渠道连通性测试 ✓")
            return {
                "ok": result.get("ok", False),
                "channel_id": channel_id,
                "type": "feishu",
                "result": result,
                "error": result.get("error"),
            }

        return {
            "ok": False,
            "channel_id": channel_id,
            "type": channel_type,
            "error": f"未知渠道类型: {channel_type}",
        }

    async def update_last_message_at(self, channel_id: int) -> None:
        """更新渠道的最后消息时间(内部辅助方法)

        将 last_message_at 写入 config JSON
        """
        async with async_session() as session:
            channel = await session.get(Channel, channel_id)
            if channel is None:
                return
            existing_config = dict(channel.config) if channel.config else {}
            existing_config["last_message_at"] = datetime.utcnow().isoformat()
            channel.config = existing_config
            await session.commit()


# 模块级单例
channel_router = ChannelRouter()
