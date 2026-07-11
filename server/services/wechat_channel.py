"""微信消息桥接服务 (Phase 9C)

基于 itchat 实现微信个人号消息桥接(可选依赖)。
- itchat 未安装时,所有方法返回结构化错误
- itchat 已安装时,支持二维码登录、收发消息、获取联系人

设计说明:
- itchat 是同步库,在 async 服务中需要谨慎使用,这里通过线程池封装
- 消息处理器(handler)在收到消息时被调用
- 状态(登录态、用户信息)维护在内存中

融合来源:
- Pangu Nebula 的 IM 渠道统一路由设计
- itchat 个人号接入模式
"""

from __future__ import annotations

import threading
from typing import Any, Callable

# 可选依赖: itchat(微信个人号 SDK)
try:
    import itchat  # type: ignore
    HAS_ITCHAT = True
except ImportError:
    HAS_ITCHAT = False


def _not_installed() -> dict:
    """未安装 itchat 时的统一错误响应"""
    return {"ok": False, "data": None, "error": "itchat 库未安装"}


class WeChatChannel:
    """微信渠道桥接服务

    - 内部维护登录态、用户信息、消息处理器
    - itchat 不可用时,所有方法返回结构化错误
    """

    def __init__(self) -> None:
        self._logged_in: bool = False
        self._user_name: str | None = None
        self._nick_name: str | None = None
        self._message_handler: Callable[[dict], Any] | None = None
        self._messages: list[dict] = []  # 最近消息缓存
        self._lock = threading.Lock()

    # ===== 登录 / 登出 =====

    def login(self, qr_callback: Callable[[str], Any] | None = None) -> dict:
        """登录微信(扫码)

        - qr_callback: 二维码回调,接收二维码图片路径或 base64
        - 成功返回 {ok, logged_in, user_name, nick_name}
        - itchat 未安装时返回 {ok: False, error: "itchat 库未安装"}
        """
        if not HAS_ITCHAT:
            return _not_installed()

        try:
            # itchat.auto_login 支持二维码回调(picDir 或 qrCallback)
            # 这里使用 enableCmdQR=False + hotReload=False
            if qr_callback is not None:
                itchat.auto_login(
                    hotReload=False,
                    enableCmdQR=False,
                    picDir=None,
                    qrCallback=qr_callback,
                )
            else:
                itchat.auto_login(hotReload=False, enableCmdQR=False)

            # 获取登录用户信息
            user = itchat.search_friends() or {}
            with self._lock:
                self._logged_in = True
                self._user_name = user.get("UserName")
                self._nick_name = user.get("NickName")

            # 注册消息接收处理器(将 itchat 消息转发到 _on_raw_message)
            itchat.msg_register([itchat.content.TEXT, itchat.content.PICTURE, itchat.content.VIDEO])(self._on_raw_message)

            return {
                "ok": True,
                "logged_in": True,
                "user_name": self._user_name,
                "nick_name": self._nick_name,
                "error": None,
            }
        except Exception as e:
            return {"ok": False, "logged_in": False, "error": f"登录失败: {e}"}

    def logout(self) -> dict:
        """登出微信"""
        if not HAS_ITCHAT:
            return _not_installed()

        try:
            itchat.logout()
        except Exception:
            # 登出失败不阻塞状态重置
            pass
        with self._lock:
            self._logged_in = False
            self._user_name = None
            self._nick_name = None
        return {"ok": True, "logged_in": False, "error": None}

    # ===== 发送消息 =====

    def send_message(self, to_user: str, content: str) -> dict:
        """发送文本消息

        - to_user: 微信用户名(UserName)或备注名
        - content: 文本内容
        """
        if not HAS_ITCHAT:
            return _not_installed()
        if not self._logged_in:
            return {"ok": False, "error": "微信未登录"}

        try:
            result = itchat.send(content, toUserName=to_user)
            msg_id = result.get("MsgId") if isinstance(result, dict) else None
            return {
                "ok": True,
                "channel": "wechat",
                "target": to_user,
                "msg_id": str(msg_id) if msg_id else None,
                "error": None,
            }
        except Exception as e:
            return {"ok": False, "channel": "wechat", "target": to_user, "error": f"发送失败: {e}"}

    def send_image(self, to_user: str, image_path: str) -> dict:
        """发送图片消息

        - to_user: 微信用户名
        - image_path: 本地图片路径
        """
        if not HAS_ITCHAT:
            return _not_installed()
        if not self._logged_in:
            return {"ok": False, "error": "微信未登录"}

        try:
            result = itchat.send_image(image_path, toUserName=to_user)
            msg_id = result.get("MsgId") if isinstance(result, dict) else None
            return {
                "ok": True,
                "channel": "wechat",
                "target": to_user,
                "msg_type": "image",
                "msg_id": str(msg_id) if msg_id else None,
                "error": None,
            }
        except Exception as e:
            return {"ok": False, "channel": "wechat", "target": to_user, "error": f"发送图片失败: {e}"}

    # ===== 联系人 / 消息 =====

    def get_contacts(self) -> list[dict]:
        """获取联系人列表

        返回 [{user_name, nick_name, remark_name, type}, ...]
        itchat 未安装时返回空列表
        """
        if not HAS_ITCHAT:
            return []

        try:
            friends = itchat.get_friends(update=True) or []
            contacts: list[dict] = []
            for f in friends:
                contacts.append({
                    "user_name": f.get("UserName"),
                    "nick_name": f.get("NickName"),
                    "remark_name": f.get("RemarkName"),
                    "type": "friend",
                })
            # 也包含群聊
            groups = itchat.get_chatrooms(update=True) or []
            for g in groups:
                contacts.append({
                    "user_name": g.get("UserName"),
                    "nick_name": g.get("NickName"),
                    "remark_name": g.get("RemarkName"),
                    "type": "group",
                })
            return contacts
        except Exception:
            return []

    def get_messages(self, limit: int = 20) -> list[dict]:
        """获取最近消息缓存(从内存中读取)

        - limit: 最多返回多少条
        """
        with self._lock:
            return list(self._messages[-limit:])

    # ===== 消息处理器 =====

    def register_message_handler(self, handler: Callable[[dict], Any]) -> dict:
        """注册消息处理器

        - handler: 收到消息时调用的回调,接收统一格式 dict
        """
        self._message_handler = handler
        return {"ok": True, "error": None}

    def _on_raw_message(self, msg: dict) -> None:
        """itchat 消息回调(内部)

        将 itchat 原始消息转为统一格式并缓存,然后调用已注册的 handler。
        """
        try:
            normalized = {
                "from": msg.get("FromUserName"),
                "to": msg.get("ToUserName"),
                "content": msg.get("Text") or msg.get("Content"),
                "timestamp": msg.get("CreateTime"),
                "type": self._normalize_msg_type(msg.get("Type")),
                "raw": msg,
            }
            with self._lock:
                self._messages.append(normalized)
                # 限制缓存大小
                if len(self._messages) > 200:
                    self._messages = self._messages[-200:]
            if self._message_handler is not None:
                try:
                    self._message_handler(normalized)
                except Exception:
                    pass
        except Exception:
            pass
        # itchat 要求处理器返回值(可选)
        return None

    @staticmethod
    def _normalize_msg_type(raw_type: str | None) -> str:
        """将 itchat 消息类型归一化为统一类型(text/image/video/other)"""
        if not raw_type:
            return "other"
        t = raw_type.lower()
        if t == "text":
            return "text"
        if t == "picture":
            return "image"
        if t == "video":
            return "video"
        return "other"

    # ===== 状态 =====

    def get_status(self) -> dict:
        """获取微信渠道状态

        返回 {logged_in, user_name, nick_name, has_itchat}
        """
        with self._lock:
            return {
                "ok": True,
                "logged_in": self._logged_in,
                "user_name": self._user_name,
                "nick_name": self._nick_name,
                "has_itchat": HAS_ITCHAT,
                "error": None if HAS_ITCHAT else "itchat 库未安装",
            }

    # ===== 后台运行(可选)=====

    def run_in_background(self) -> dict:
        """在后台线程启动 itchat 消息循环(阻塞式)

        itchat.run(debug=False) 会阻塞,因此需在线程中运行。
        """
        if not HAS_ITCHAT:
            return _not_installed()
        if not self._logged_in:
            return {"ok": False, "error": "微信未登录"}

        def _run():
            try:
                itchat.run(debug=False, blockThread=True)
            except Exception:
                pass

        thread = threading.Thread(target=_run, daemon=True, name="wechat-itchat")
        thread.start()
        return {"ok": True, "thread": thread.name, "error": None}
