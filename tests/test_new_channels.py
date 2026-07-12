"""新增 IM 渠道服务测试 (Telegram / Discord / 钉钉)

覆盖:
1. TelegramChannel 可实例化,configure 后 status 正确
2. TelegramChannel 无 token 时 send_text 返回 mock
3. DiscordChannel 可实例化,configure 后 status 正确
4. DiscordChannel 无 webhook 时 send_text 返回 mock
5. DingTalkChannel 可实例化,configure 后 status 正确
6. DingTalkChannel 无 webhook 时 send_text 返回 mock
"""

from server.services.telegram_channel import TelegramChannel
from server.services.discord_channel import DiscordChannel
from server.services.dingtalk_channel import DingTalkChannel


# ===== Telegram =====


def test_telegram_configure_status():
    """TelegramChannel 可实例化,configure 后 status 正确"""
    channel = TelegramChannel()
    # configure 前(假设环境变量未设置)
    pre_status = channel.get_status()
    assert pre_status["ok"] is True

    # configure
    result = channel.configure(token="123456:ABC-DEF")
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["token_set"] is True
    assert result["error"] is None

    # configure 后 status 应反映已配置
    status = channel.get_status()
    assert status["ok"] is True
    assert status["configured"] is True
    assert status["token_set"] is True
    assert status["error"] is None


async def test_telegram_send_text_mock(monkeypatch):
    """TelegramChannel 无 token 时 send_text 返回 mock"""
    monkeypatch.delenv("NEBULA_TELEGRAM_TOKEN", raising=False)
    channel = TelegramChannel()
    # 确保无 token
    assert channel._token is None

    result = await channel.send_text(chat_id="123456", text="hello telegram")

    assert result["ok"] is True
    assert result["channel"] == "telegram"
    assert result["error"] is None
    data = result["data"]
    assert data["mock"] is True
    assert data["chat_id"] == "123456"
    assert data["text"] == "hello telegram"


# ===== Discord =====


def test_discord_configure_status():
    """DiscordChannel 可实例化,configure 后 status 正确"""
    channel = DiscordChannel()
    pre_status = channel.get_status()
    assert pre_status["ok"] is True

    result = channel.configure(
        webhook_url="https://discord.com/api/webhooks/123/abc"
    )
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["webhook_set"] is True
    assert result["error"] is None

    status = channel.get_status()
    assert status["ok"] is True
    assert status["configured"] is True
    assert status["webhook_set"] is True
    assert status["error"] is None


async def test_discord_send_text_mock(monkeypatch):
    """DiscordChannel 无 webhook 时 send_text 返回 mock"""
    monkeypatch.delenv("NEBULA_DISCORD_WEBHOOK", raising=False)
    channel = DiscordChannel()
    assert channel._webhook_url is None

    result = await channel.send_text("hello discord")

    assert result["ok"] is True
    assert result["channel"] == "discord"
    assert result["error"] is None
    data = result["data"]
    assert data["mock"] is True
    assert data["text"] == "hello discord"


# ===== 钉钉 =====


def test_dingtalk_configure_status():
    """DingTalkChannel 可实例化,configure 后 status 正确"""
    channel = DingTalkChannel()
    pre_status = channel.get_status()
    assert pre_status["ok"] is True

    result = channel.configure(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
        secret="SEC123456",
    )
    assert result["ok"] is True
    assert result["configured"] is True
    assert result["webhook_set"] is True
    assert result["secret_set"] is True
    assert result["error"] is None

    status = channel.get_status()
    assert status["ok"] is True
    assert status["configured"] is True
    assert status["webhook_set"] is True
    assert status["secret_set"] is True
    assert status["error"] is None


async def test_dingtalk_send_text_mock(monkeypatch):
    """DingTalkChannel 无 webhook 时 send_text 返回 mock"""
    monkeypatch.delenv("NEBULA_DINGTALK_WEBHOOK", raising=False)
    monkeypatch.delenv("NEBULA_DINGTALK_SECRET", raising=False)
    channel = DingTalkChannel()
    assert channel._webhook_url is None

    result = await channel.send_text("hello dingtalk")

    assert result["ok"] is True
    assert result["channel"] == "dingtalk"
    assert result["error"] is None
    data = result["data"]
    assert data["mock"] is True
    assert data["text"] == "hello dingtalk"
