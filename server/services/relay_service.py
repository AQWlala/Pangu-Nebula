"""中继客户端服务 (Phase 9B)

实现基于 HTTP 长轮询的同步协议(简化版,不依赖 WebSocket 库):
- start_relay / stop_relay: 管理中继连接
- get_status: 查询中继状态
- push_operations: 推送同步操作到中继服务器
- pull_operations: 从中继服务器拉取待同步操作
- sync_with_device: 完整同步流程(push -> pull -> mark synced)
- list_relay_servers: 列出已配置的中继服务器

使用 httpx.AsyncClient 做 HTTP 通信。
中继服务器 URL 可配置,默认为空(本地模式)。
"""

from datetime import datetime

import httpx
from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import SyncDevice


# HTTP 请求超时(秒)
_HTTP_TIMEOUT = 30.0


class RelayService:
    """中继客户端服务(模块级单例)"""

    def __init__(self):
        # 当前中继连接状态
        self._connected: bool = False
        self._url: str = ""
        self._device_id: str = ""
        self._last_sync_at: datetime | None = None
        # 已配置的中继服务器列表(可配置多个)
        self._servers: list[dict] = []

    # ===== 连接管理 =====

    def start_relay(self, url: str, device_id: str) -> dict:
        """启动中继连接

        - 记录中继服务器 URL 和本地 device_id
        - 返回 {connected: True, url, device_id}
        """
        self._url = url.rstrip("/")
        self._device_id = device_id
        self._connected = True

        # 记录到已配置服务器列表(去重)
        existing = next((s for s in self._servers if s["url"] == self._url), None)
        if existing is None:
            self._servers.append({"url": self._url, "device_id": device_id})

        return {
            "connected": True,
            "url": self._url,
            "device_id": self._device_id,
        }

    def stop_relay(self) -> dict:
        """停止中继连接"""
        prev_url = self._url
        prev_device = self._device_id
        self._connected = False
        self._url = ""
        self._device_id = ""
        return {
            "connected": False,
            "url": prev_url,
            "device_id": prev_device,
        }

    def get_status(self) -> dict:
        """返回当前中继状态"""
        return {
            "connected": self._connected,
            "url": self._url,
            "device_id": self._device_id,
            "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
        }

    # ===== 推送 / 拉取 =====

    async def push_operations(
        self, target_device_id: str, operations: list[dict]
    ) -> dict:
        """通过 HTTP POST 推送同步操作到中继服务器

        - 返回 {pushed: count, success: bool, error: str | None}
        - 如果中继 URL 为空,返回 {pushed: 0, success: False, error: "No relay server configured"}
        """
        if not self._connected or not self._url:
            return {
                "pushed": 0,
                "success": False,
                "error": "No relay server configured",
            }

        payload = {
            "source_device_id": self._device_id,
            "target_device_id": target_device_id,
            "operations": operations,
        }

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._url}/api/relay/push",
                    json=payload,
                )
        except httpx.RequestError as e:
            return {
                "pushed": 0,
                "success": False,
                "error": f"推送请求失败: {e}",
            }

        if resp.status_code != 200:
            return {
                "pushed": 0,
                "success": False,
                "error": f"推送失败: HTTP {resp.status_code} - {resp.text}",
            }

        try:
            body = resp.json()
        except Exception:
            body = {}

        pushed = body.get("pushed", len(operations))
        return {
            "pushed": pushed,
            "success": True,
            "error": None,
        }

    async def pull_operations(self) -> list[dict]:
        """通过 HTTP GET 从中继服务器拉取待同步操作

        - 返回操作列表
        - 如果中继 URL 为空,返回空列表
        """
        if not self._connected or not self._url:
            return []

        params = {"device_id": self._device_id}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    f"{self._url}/api/relay/pull",
                    params=params,
                )
        except httpx.RequestError:
            return []

        if resp.status_code != 200:
            return []

        try:
            body = resp.json()
        except Exception:
            return []

        # 兼容中继服务器返回格式: {operations: [...]} 或直接 [...]
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get("operations", [])
        return []

    # ===== 完整同步 =====

    async def sync_with_device(self, device_id: str) -> dict:
        """完整同步流程: push -> pull -> mark synced

        - 推送本地待同步操作到中继
        - 拉取对端待同步操作
        - 更新设备的 last_sync_at
        - 返回 {pushed: N, pulled: N, errors: [...]}
        """
        errors: list[str] = []

        # 推送阶段(空操作列表作为占位,实际应由调用方提供)
        push_result = await self.push_operations(device_id, [])
        pushed = push_result.get("pushed", 0)
        if not push_result.get("success", False):
            err = push_result.get("error", "推送失败")
            errors.append(err)

        # 拉取阶段
        pulled_ops = await self.pull_operations()
        pulled = len(pulled_ops)

        # 标记同步时间(DB + 内存)
        self._last_sync_at = datetime.utcnow()
        await self._mark_device_synced(device_id)

        return {
            "pushed": pushed,
            "pulled": pulled,
            "errors": errors,
        }

    async def _mark_device_synced(self, device_id: str) -> None:
        """更新设备的 last_sync_at"""
        try:
            async with async_session() as session:
                stmt = select(SyncDevice).where(SyncDevice.did_key == device_id)
                result = await session.execute(stmt)
                device = result.scalar_one_or_none()
                if device is not None:
                    device.last_sync_at = datetime.utcnow()
                    await session.commit()
        except Exception:
            # 标记同步时间失败不应影响整体同步流程
            pass

    # ===== 服务器列表 =====

    def list_relay_servers(self) -> list[dict]:
        """列出已配置的中继服务器"""
        return list(self._servers)


# 模块级单例
relay_service = RelayService()
