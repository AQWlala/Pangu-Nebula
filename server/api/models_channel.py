"""Phase 9C: IM 渠道 Pydantic 请求模型

分离自 api/models.py,避免与其他子智能体(9A/9B)修改 models.py 冲突。
"""

from pydantic import BaseModel


# ===== Phase 9C: IM 渠道 =====


class ChannelRegisterRequest(BaseModel):
    """注册新渠道请求"""

    name: str
    channel_type: str  # wechat/feishu
    config: dict = {}


class ChannelUpdateRequest(BaseModel):
    """更新渠道请求"""

    name: str | None = None
    config: dict | None = None
    enabled: bool | None = None


class ChannelSendRequest(BaseModel):
    """统一发送消息请求"""

    channel_type: str  # wechat/feishu
    target: str  # 用户ID/群ID/Webhook URL
    content: str
    msg_type: str = "text"  # text/image/card


class ChannelReceiveRequest(BaseModel):
    """统一接收消息请求(Webhook 回调)"""

    channel_type: str
    raw_message: dict


class WeChatLoginRequest(BaseModel):
    """微信登录请求(占位,后续可扩展 qr_callback 等字段)"""

    pass


class FeishuConfigureRequest(BaseModel):
    """飞书应用凭证配置请求"""

    app_id: str
    app_secret: str
    verification_token: str = ""


class FeishuSendTextRequest(BaseModel):
    """飞书 Webhook 发送文本请求"""

    webhook_url: str
    text: str


class FeishuSendCardRequest(BaseModel):
    """飞书 Webhook 发送卡片请求"""

    webhook_url: str
    card: dict


# ===== Telegram =====


class TelegramConfigureRequest(BaseModel):
    """Telegram Bot 配置请求"""

    token: str


class TelegramSendTextRequest(BaseModel):
    """Telegram 发送文本请求"""

    chat_id: str | int
    text: str


# ===== Discord =====


class DiscordConfigureRequest(BaseModel):
    """Discord Webhook 配置请求"""

    webhook_url: str


class DiscordSendTextRequest(BaseModel):
    """Discord 发送文本请求"""

    text: str


# ===== 钉钉 =====


class DingTalkConfigureRequest(BaseModel):
    """钉钉机器人配置请求"""

    webhook_url: str
    secret: str = ""


class DingTalkSendTextRequest(BaseModel):
    """钉钉发送文本请求"""

    text: str


# ===== 企业微信 =====


class WeComConfigureRequest(BaseModel):
    """企业微信群机器人配置请求"""

    webhook_url: str


class WeComSendTextRequest(BaseModel):
    """企业微信发送文本请求"""

    text: str
