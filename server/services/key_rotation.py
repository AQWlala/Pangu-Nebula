"""密钥轮换服务 (Phase 8A)

实现数据密钥的定期轮换:
- 生成新数据密钥
- 用旧密钥解密所有 keychain 中的值
- 用新密钥重新加密所有值
- 标记旧密钥为 is_active=False, rotated_at=now
- 创建新 EncryptionKey(is_active=True)

轮换策略:
- 默认 90 天轮换一次
- 可通过 force=True 强制轮换

融合来源:
- Nebula 的安全模块设计
- NomiFun 的密钥管理
"""

import base64
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import EncryptionKey
from .keychain import keychain as _keychain


# 轮换周期(天)
_ROTATION_PERIOD_DAYS = 90


def _key_to_dict(key: EncryptionKey) -> dict:
    """ORM 转 dict"""
    return {
        "id": key.id,
        "key_id": key.key_id,
        "key_type": key.key_type,
        "is_active": bool(key.is_active),
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "rotated_at": key.rotated_at.isoformat() if key.rotated_at else None,
    }


class KeyRotationService:
    """密钥轮换服务"""

    def __init__(self, keychain=None):
        """初始化

        - keychain: Keychain 实例,默认使用模块级单例
        """
        self._keychain = keychain or _keychain

    async def get_active_key(self, session: AsyncSession) -> EncryptionKey | None:
        """获取当前活跃密钥(ORM 对象)"""
        stmt = (
            select(EncryptionKey)
            .where(EncryptionKey.is_active == True)  # noqa: E712
            .order_by(EncryptionKey.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_key_history(self, session: AsyncSession) -> list[dict]:
        """获取密钥历史(按创建时间倒序)"""
        stmt = select(EncryptionKey).order_by(EncryptionKey.created_at.desc())
        result = await session.execute(stmt)
        return [_key_to_dict(k) for k in result.scalars().all()]

    async def should_rotate(self, session: AsyncSession) -> bool:
        """是否应该轮换

        - 无活跃密钥: 不需要轮换(由 keychain 自动创建)
        - 活跃密钥创建超过 90 天: 需要轮换
        - 否则: 不需要
        """
        active_key = await self.get_active_key(session)
        if active_key is None:
            return False

        if not active_key.created_at:
            return False

        age = datetime.utcnow() - active_key.created_at
        return age > timedelta(days=_ROTATION_PERIOD_DAYS)

    async def rotate(self, session: AsyncSession, force: bool = False) -> dict:
        """执行密钥轮换

        流程:
        1. 获取当前活跃的 EncryptionKey
        2. 判断是否需要轮换(超过 90 天或 force=True)
        3. 生成新数据密钥
        4. 用旧密钥解密所有 keychain 中的值
        5. 用新密钥重新加密所有值
        6. 标记旧密钥为 is_active=False, rotated_at=now
        7. 创建新 EncryptionKey(is_active=True)

        返回 {"rotated": bool, "old_key_id": "...", "new_key_id": "...", "items_reencrypted": N}
        """
        if not self._keychain.is_available():
            return {
                "rotated": False,
                "error": "cryptography 库未安装,无法执行密钥轮换",
                "old_key_id": None,
                "new_key_id": None,
                "items_reencrypted": 0,
            }

        active_key = await self.get_active_key(session)

        # 无活跃密钥:创建一个新的即可
        if active_key is None:
            key_id, _ = await self._keychain._get_or_create_data_key(session)
            return {
                "rotated": True,
                "old_key_id": None,
                "new_key_id": key_id,
                "items_reencrypted": 0,
                "reason": "无活跃密钥,已创建新密钥",
            }

        # 判断是否需要轮换
        if not force and not await self.should_rotate(session):
            return {
                "rotated": False,
                "old_key_id": active_key.key_id,
                "new_key_id": active_key.key_id,
                "items_reencrypted": 0,
                "reason": f"密钥未到期(创建于 {active_key.created_at.isoformat() if active_key.created_at else 'unknown'})",
            }

        old_key_id = active_key.key_id
        master_key = self._keychain._get_master_key()

        # 1. 解密旧数据密钥
        old_data_key_b64 = self._keychain._decrypt(active_key.encrypted_key, master_key)
        old_data_key = base64.b64decode(old_data_key_b64)

        # 2. 生成新数据密钥
        new_data_key = self._keychain._generate_data_key()
        encrypted_new_data_key = self._keychain._encrypt(
            base64.b64encode(new_data_key), master_key
        )
        new_key_id = str(uuid.uuid4())

        # 3. 重新加密所有 keychain 中的值
        store_data = self._keychain._read_keychain_file()
        items_reencrypted = 0
        for key_name, entry in store_data.items():
            try:
                # 用旧数据密钥解密
                plaintext = self._keychain._decrypt(entry["ciphertext"], old_data_key)
                # 用新数据密钥重新加密
                new_ciphertext = self._keychain._encrypt(plaintext, new_data_key)
                entry["ciphertext"] = new_ciphertext
                entry["key_id"] = new_key_id
                entry["updated_at"] = datetime.utcnow().isoformat()
                items_reencrypted += 1
            except Exception:
                # 解密/加密失败,跳过该项(保留原密文)
                continue

        # 4. 写回 keychain.json
        self._keychain._write_keychain_file(store_data)

        # 5. 标记旧密钥为非活跃
        active_key.is_active = False
        active_key.rotated_at = datetime.utcnow()

        # 6. 创建新活跃密钥
        new_enc_key = EncryptionKey(
            key_id=new_key_id,
            key_type="AES-256-GCM",
            encrypted_key=encrypted_new_data_key,
            is_active=True,
        )
        session.add(new_enc_key)
        await session.commit()

        return {
            "rotated": True,
            "old_key_id": old_key_id,
            "new_key_id": new_key_id,
            "items_reencrypted": items_reencrypted,
            "reason": "密钥轮换成功",
        }


# 模块级单例
key_rotation_service = KeyRotationService()
