"""IM 渠道管理 API (Phase 9C)

提供微信 / 飞书 / IM 渠道统一路由的 REST API。

端点总览:
- GET  /channel           - 渠道模块信息
- GET  /channel/types     - 支持的渠道类型
- GET  /channel/list      - 列出所有渠道
- POST /channel           - 注册新渠道
- POST /channel/send      - 统一发送消息
- POST /channel/receive   - 统一接收消息(Webhook 回调)
- POST /channel/wechat/login    - 微信登录
- POST /channel/wechat/logout   - 微信登出
- GET  /channel/wechat/status   - 微信状态
- GET  /channel/wechat/contacts - 微信联系人
- POST /channel/feishu/configure - 飞书配置
- POST /channel/feishu/send-text - 飞书发送文本
- POST /channel/feishu/send-card - 飞书发送卡片
- GET  /channel/feishu/status    - 飞书状态
- POST /channel/{id}/test - 测试渠道连通性
- GET  /channel/{id}      - 获取单个渠道
- PUT  /channel/{id}      - 更新渠道
- DELETE /channel/{id}    - 删除渠道

路由顺序注意: 静态路径(types, list, send, receive, wechat/*, feishu/*)
必须在动态路径 /{id} 之前注册。
"""

from fastapi import APIRouter, HTTPException

from ..services.channel_router import channel_router
from .models_channel import (
    ChannelReceiveRequest,
    ChannelRegisterRequest,
    ChannelSendRequest,
    ChannelUpdateRequest,
    DingTalkConfigureRequest,
    DingTalkSendTextRequest,
    DiscordConfigureRequest,
    DiscordSendTextRequest,
    FeishuConfigureRequest,
    FeishuSendCardRequest,
    FeishuSendTextRequest,
    TelegramConfigureRequest,
    TelegramSendTextRequest,
    WeChatLoginRequest,
    WeComConfigureRequest,
    WeComSendTextRequest,
)

router = APIRouter(prefix="/channel", tags=["channel"])


# ===== 模块信息 =====


@router.get("")
async def get_channel():
    """获取渠道模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "channel",
            "phase": "9C",
            "supported_types": channel_router.get_supported_types(),
            "features": [
                "list_channels",
                "register_channel",
                "update_channel",
                "delete_channel",
                "get_channel",
                "test_channel",
                "send_message",
                "receive_message",
                "wechat_login",
                "wechat_logout",
                "wechat_status",
                "wechat_contacts",
                "feishu_configure",
                "feishu_send_text",
                "feishu_send_card",
                "feishu_status",
                "telegram_configure",
                "telegram_send_text",
                "telegram_status",
                "discord_configure",
                "discord_send_text",
                "discord_status",
                "dingtalk_configure",
                "dingtalk_send_text",
                "dingtalk_status",
                "wecom_configure",
                "wecom_send_text",
                "wecom_status",
            ],
        },
        "error": None,
    }


# ===== 静态路径(必须在 /{id} 之前)=====


@router.get("/types")
async def get_channel_types():
    """获取支持的渠道类型"""
    return {
        "ok": True,
        "data": channel_router.get_supported_types(),
        "error": None,
    }


@router.get("/list")
async def list_channels():
    """列出所有渠道"""
    data = await channel_router.list_channels()
    return {"ok": True, "data": data, "error": None}


@router.post("")
async def register_channel(req: ChannelRegisterRequest):
    """注册新渠道"""
    data = await channel_router.register_channel(
        name=req.name,
        channel_type=req.channel_type,
        config=req.config,
    )
    if not data.get("ok", True) and "error" in data:
        # 渠道类型不支持的错误
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": data["error"]},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/send")
async def send_message(req: ChannelSendRequest):
    """统一发送消息

    - channel_type: wechat / feishu
    - target: 微信用户名 / 飞书 Webhook URL
    - content: 文本内容(对于 card 类型,应为 JSON 字符串)
    - msg_type: text / image / card / interactive
    """
    result = await channel_router.send_message(
        channel_type=req.channel_type,
        target=req.target,
        content=req.content,
        msg_type=req.msg_type,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/receive")
async def receive_message(req: ChannelReceiveRequest):
    """统一接收消息(Webhook 回调)

    将渠道特定的原始消息转换为统一格式。
    对于飞书 challenge 请求,直接返回 challenge 响应。
    """
    result = channel_router.receive_message(
        channel_type=req.channel_type,
        raw_message=req.raw_message,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


# ===== 微信端点(静态路径)=====


@router.post("/wechat/login")
async def wechat_login(req: WeChatLoginRequest):
    """微信登录(扫码)

    注意: 实际二维码回调需通过 WebSocket / SSE 推送,这里简化为阻塞式登录。
    """
    # 在线程中执行同步登录(避免阻塞事件循环)
    import asyncio

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, channel_router.wechat.login, None)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/wechat/logout")
async def wechat_logout():
    """微信登出"""
    result = channel_router.wechat.logout()
    return {"ok": True, "data": result, "error": None}


@router.get("/wechat/status")
async def wechat_status():
    """获取微信登录状态"""
    data = channel_router.wechat.get_status()
    return {"ok": True, "data": data, "error": None}


@router.get("/wechat/contacts")
async def wechat_contacts():
    """获取微信联系人列表"""
    data = channel_router.wechat.get_contacts()
    return {"ok": True, "data": data, "error": None}


# ===== 飞书端点(静态路径)=====


@router.post("/feishu/configure")
async def feishu_configure(req: FeishuConfigureRequest):
    """配置飞书应用凭证"""
    data = channel_router.feishu.configure(
        app_id=req.app_id,
        app_secret=req.app_secret,
        verification_token=req.verification_token,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("/feishu/send-text")
async def feishu_send_text(req: FeishuSendTextRequest):
    """通过飞书 Webhook 发送文本消息"""
    result = await channel_router.feishu.send_text(req.webhook_url, req.text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.post("/feishu/send-card")
async def feishu_send_card(req: FeishuSendCardRequest):
    """通过飞书 Webhook 发送卡片消息"""
    result = await channel_router.feishu.send_card(req.webhook_url, req.card)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.get("/feishu/status")
async def feishu_status():
    """获取飞书渠道状态"""
    data = channel_router.feishu.get_status()
    return {"ok": True, "data": data, "error": None}


# ===== Telegram 端点(静态路径)=====


@router.post("/telegram/configure")
async def telegram_configure(req: TelegramConfigureRequest):
    """配置 Telegram Bot Token"""
    data = channel_router.telegram.configure(token=req.token)
    return {"ok": True, "data": data, "error": None}


@router.post("/telegram/send-text")
async def telegram_send_text(req: TelegramSendTextRequest):
    """通过 Telegram Bot 发送文本消息"""
    result = await channel_router.telegram.send_text(req.chat_id, req.text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.get("/telegram/status")
async def telegram_status():
    """获取 Telegram 渠道状态"""
    data = channel_router.telegram.get_status()
    return {"ok": True, "data": data, "error": None}


# ===== Discord 端点(静态路径)=====


@router.post("/discord/configure")
async def discord_configure(req: DiscordConfigureRequest):
    """配置 Discord Webhook URL"""
    data = channel_router.discord.configure(webhook_url=req.webhook_url)
    return {"ok": True, "data": data, "error": None}


@router.post("/discord/send-text")
async def discord_send_text(req: DiscordSendTextRequest):
    """通过 Discord Webhook 发送文本消息"""
    result = await channel_router.discord.send_text(req.text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.get("/discord/status")
async def discord_status():
    """获取 Discord 渠道状态"""
    data = channel_router.discord.get_status()
    return {"ok": True, "data": data, "error": None}


# ===== 钉钉端点(静态路径)=====


@router.post("/dingtalk/configure")
async def dingtalk_configure(req: DingTalkConfigureRequest):
    """配置钉钉机器人 Webhook 和签名密钥"""
    data = channel_router.dingtalk.configure(
        webhook_url=req.webhook_url,
        secret=req.secret,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("/dingtalk/send-text")
async def dingtalk_send_text(req: DingTalkSendTextRequest):
    """通过钉钉机器人发送文本消息"""
    result = await channel_router.dingtalk.send_text(req.text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.get("/dingtalk/status")
async def dingtalk_status():
    """获取钉钉渠道状态"""
    data = channel_router.dingtalk.get_status()
    return {"ok": True, "data": data, "error": None}


# ===== 企业微信端点(静态路径)=====


@router.post("/wecom/configure")
async def wecom_configure(req: WeComConfigureRequest):
    """配置企业微信群机器人 Webhook"""
    data = channel_router.wecom.configure(webhook_url=req.webhook_url)
    return {"ok": True, "data": data, "error": None}


@router.post("/wecom/send-text")
async def wecom_send_text(req: WeComSendTextRequest):
    """通过企业微信群机器人发送文本消息"""
    result = await channel_router.wecom.send_text(req.text)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result, "error": None}


@router.get("/wecom/status")
async def wecom_status():
    """获取企业微信渠道状态"""
    data = channel_router.wecom.get_status()
    return {"ok": True, "data": data, "error": None}


# ===== 动态路径(必须在所有静态路径之后)=====


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int):
    """测试渠道连通性"""
    data = await channel_router.test_channel(channel_id)
    if not data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": data.get("error")},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/{channel_id}")
async def get_channel_by_id(channel_id: int):
    """获取单个渠道"""
    data = await channel_router.get_channel(channel_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Channel not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{channel_id}")
async def update_channel(channel_id: int, req: ChannelUpdateRequest):
    """更新渠道

    - name: 新名称(会写入 config.name)
    - config: 新配置(会与现有 config 合并)
    - enabled: 是否启用
    """
    # 构建 config 更新字典
    config_update: dict = {}
    if req.config is not None:
        config_update.update(req.config)
    if req.name is not None:
        config_update["name"] = req.name

    # 处理 enabled 字段(需要单独更新 ORM 列)
    if req.enabled is not None:
        # 通过 update_channel 间接更新 config 后,再单独更新 enabled
        # 这里先获取当前 channel,然后整体更新
        from ..db.engine import async_session
        from ..db.orm import Channel

        async with async_session() as session:
            channel = await session.get(Channel, channel_id)
            if channel is None:
                raise HTTPException(
                    status_code=404,
                    detail={"ok": False, "data": None, "error": "Channel not found"},
                )
            existing_config = dict(channel.config) if channel.config else {}
            for k, v in config_update.items():
                existing_config[k] = v
            channel.config = existing_config
            channel.enabled = req.enabled
            await session.commit()
            await session.refresh(channel)
            data = channel_router._channel_to_dict(channel)
        return {"ok": True, "data": data, "error": None}

    # 仅更新 config
    data = await channel_router.update_channel(channel_id, config_update)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Channel not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int):
    """删除渠道"""
    deleted = await channel_router.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Channel not found"},
        )
    return {"ok": True, "data": {"id": channel_id, "deleted": True}, "error": None}
