"""设备配对服务 (Phase 9B)

实现 QR 码 / 配对码配对流程:
- initiate_pairing: 生成设备密钥对 + 配对码 + QR 载荷,存储待配对设备
- confirm_pairing: 验证配对码,计算共享密钥,创建配对设备记录
- list_devices / get_device / revoke_device: 设备管理
- get_pairing_status: 查询配对状态

内部维护内存中的 pending_pairings dict(pairing_code -> 设备信息),
配对码 10 分钟过期。

依赖 Phase 9A 提供的 sync_crypto_service(延迟导入,确保模块可独立加载)。
"""

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import SyncDevice


# 配对码过期时间(秒)
_PAIRING_TTL_SECONDS = 600  # 10 分钟


def _get_sync_crypto_service():
    """延迟导入 sync_crypto_service(Phase 9A 提供)

    使用延迟导入确保本模块在 sync_crypto 尚未创建时也能被 import。
    """
    from .sync_crypto import sync_crypto_service
    return sync_crypto_service


class PairingService:
    """设备配对服务(模块级单例)"""

    def __init__(self):
        # 内存中的待配对记录: pairing_code -> {device_id, public_key, private_key, expires_at, device_name}
        self._pending_pairings: dict[str, dict] = {}

    # ===== 内部辅助 =====

    def _generate_pairing_code(self) -> str:
        """生成 6 位数字配对码"""
        return f"{secrets.randbelow(1000000):06d}"

    def _generate_device_id(self) -> str:
        """生成设备唯一 ID"""
        return f"dev-{uuid.uuid4().hex[:12]}"

    def _is_expired(self, expires_at: datetime) -> bool:
        """检查配对码是否过期"""
        return datetime.utcnow() > expires_at

    def _cleanup_expired(self) -> None:
        """清理过期的待配对记录"""
        now = datetime.utcnow()
        expired_codes = [
            code
            for code, info in self._pending_pairings.items()
            if now > info["expires_at"]
        ]
        for code in expired_codes:
            del self._pending_pairings[code]

    def _device_to_dict(self, device: SyncDevice) -> dict:
        """ORM 对象转 dict(兼容 9A 扩展字段)"""
        result = {
            "id": device.id,
            "device_name": device.device_name,
            "did_key": device.did_key,
            "last_sync_at": device.last_sync_at.isoformat() if device.last_sync_at else None,
        }
        # 9A 扩展字段(可能存在也可能不存在,用 getattr 安全访问)
        result["public_key"] = getattr(device, "public_key", None)
        result["device_id"] = getattr(device, "device_id", None)
        result["status"] = getattr(device, "status", None)
        paired_at = getattr(device, "paired_at", None)
        result["paired_at"] = paired_at.isoformat() if paired_at else None
        return result

    # ===== 对外接口 =====

    async def initiate_pairing(self, device_name: str) -> dict:
        """发起配对

        - 生成设备密钥对(调用 sync_crypto_service.generate_device_keypair)
        - 生成 6 位配对码
        - 生成 QR 载荷(调用 sync_crypto_service.generate_qr_payload)
        - 存储待配对设备到 DB(status=pending)
        - 返回 {device_id, public_key, pairing_code, qr_payload, expires_at}
        """
        crypto = _get_sync_crypto_service()

        # 生成密钥对(返回 tuple: private_pem, public_pem)
        private_key, public_key = crypto.generate_device_keypair()

        # 生成配对码与设备 ID
        pairing_code = self._generate_pairing_code()
        device_id = self._generate_device_id()
        expires_at = datetime.utcnow() + timedelta(seconds=_PAIRING_TTL_SECONDS)

        # 生成 QR 载荷
        qr_payload = crypto.generate_qr_payload(
            device_id=device_id,
            public_key=public_key,
            pairing_code=pairing_code,
        )

        # 内存中保存待配对记录
        self._pending_pairings[pairing_code] = {
            "device_id": device_id,
            "public_key": public_key,
            "private_key": private_key,
            "expires_at": expires_at,
            "device_name": device_name,
        }

        # 存储到 DB(status=pending)
        async with async_session() as session:
            device = SyncDevice(
                device_name=device_name,
                did_key=device_id,
            )
            # 9A 扩展字段:安全设置
            if hasattr(device, "device_id"):
                device.device_id = device_id
            if hasattr(device, "public_key"):
                device.public_key = public_key
            if hasattr(device, "status"):
                device.status = "pending"
            session.add(device)
            await session.commit()

        return {
            "device_id": device_id,
            "public_key": public_key,
            "pairing_code": pairing_code,
            "qr_payload": qr_payload,
            "expires_at": expires_at.isoformat(),
        }

    async def confirm_pairing(
        self, pairing_code: str, peer_public_key: str, peer_device_name: str
    ) -> dict:
        """确认配对

        - 验证配对码有效且未过期
        - 计算共享密钥(基于 ECDH,由 sync_crypto_service 提供)
        - 创建配对设备记录(status=paired)
        - 返回 {device_id, peer_device_id, shared_secret_established: True}
        """
        self._cleanup_expired()

        # 验证配对码
        pending = self._pending_pairings.get(pairing_code)
        if pending is None:
            raise ValueError(f"无效或已过期的配对码: {pairing_code}")
        if self._is_expired(pending["expires_at"]):
            del self._pending_pairings[pairing_code]
            raise ValueError(f"配对码已过期: {pairing_code}")

        crypto = _get_sync_crypto_service()

        # 计算共享密钥(ECDH)
        local_private_key = pending["private_key"]
        shared_secret = None
        if hasattr(crypto, "compute_shared_secret"):
            shared_secret = crypto.compute_shared_secret(
                local_private_key, peer_public_key
            )

        local_device_id = pending["device_id"]
        peer_device_id = self._generate_device_id()

        # 更新本地设备记录为 paired,并创建 peer 设备记录
        async with async_session() as session:
            # 更新本地设备状态
            stmt = select(SyncDevice).where(SyncDevice.did_key == local_device_id)
            result = await session.execute(stmt)
            local_device = result.scalar_one_or_none()
            if local_device is not None:
                if hasattr(local_device, "status"):
                    local_device.status = "paired"
                if hasattr(local_device, "paired_at"):
                    local_device.paired_at = datetime.utcnow()

            # 创建 peer 设备记录
            peer_device = SyncDevice(
                device_name=peer_device_name,
                did_key=peer_device_id,
            )
            if hasattr(peer_device, "device_id"):
                peer_device.device_id = peer_device_id
            if hasattr(peer_device, "public_key"):
                peer_device.public_key = peer_public_key
            if hasattr(peer_device, "status"):
                peer_device.status = "paired"
            if hasattr(peer_device, "paired_at"):
                peer_device.paired_at = datetime.utcnow()
            session.add(peer_device)
            await session.commit()

        # 从内存中移除已完成的配对
        del self._pending_pairings[pairing_code]

        return {
            "device_id": local_device_id,
            "peer_device_id": peer_device_id,
            "shared_secret_established": shared_secret is not None,
        }

    async def list_devices(self) -> list[dict]:
        """列出所有已配对设备"""
        async with async_session() as session:
            stmt = select(SyncDevice).order_by(SyncDevice.id.desc())
            result = await session.execute(stmt)
            devices = result.scalars().all()
            return [self._device_to_dict(d) for d in devices]

    async def get_device(self, device_id: str) -> dict | None:
        """获取单个设备(按 device_id / did_key 查找)"""
        async with async_session() as session:
            # 优先按 did_key 查找
            stmt = select(SyncDevice).where(SyncDevice.did_key == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            if device is None:
                return None
            return self._device_to_dict(device)

    async def revoke_device(self, device_id: str) -> bool:
        """撤销设备配对(status=blocked)"""
        async with async_session() as session:
            stmt = select(SyncDevice).where(SyncDevice.did_key == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            if device is None:
                return False
            if hasattr(device, "status"):
                device.status = "blocked"
            await session.commit()
            return True

    def get_pairing_status(self, pairing_code: str) -> dict | None:
        """查询配对状态(从内存中查询,不查 DB)"""
        self._cleanup_expired()
        pending = self._pending_pairings.get(pairing_code)
        if pending is None:
            return None
        return {
            "pairing_code": pairing_code,
            "device_id": pending["device_id"],
            "device_name": pending["device_name"],
            "status": "pending",
            "expires_at": pending["expires_at"].isoformat(),
        }


# 模块级单例
pairing_service = PairingService()
