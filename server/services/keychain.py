"""密钥管理服务 (Phase 8A)

实现 AES-256-GCM 加密的密钥存储:
- 主密钥(Master Key): 从环境变量 NEBULA_MASTER_KEY 读取,不存在则生成并存储到 data/.master_key
- 数据密钥(Data Key): 随机生成的 AES-256 密钥,用主密钥加密后存储在 EncryptionKey 表
- 密钥值(Value): 用数据密钥加密后存储在 data/keychain.json

设计说明:
- 系统维护一个活跃的数据密钥(is_active=True),用于加密所有密钥值
- 密钥轮换时生成新数据密钥,重新加密所有密钥值

融合来源:
- Nebula 的安全模块设计
- NomiFun 的 nomifun-secret 加密存储
"""

import base64
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import EncryptionKey

# 尝试导入 cryptography,失败则标记不可用
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False


# 主密钥文件路径
_MASTER_KEY_FILE = Path("data/.master_key")
# 密钥值存储文件
_KEYCHAIN_FILE = Path("data/keychain.json")
# AES-256 密钥长度(字节)
_KEY_LENGTH = 32
# GCM nonce 长度(字节)
_NONCE_LENGTH = 12


class Keychain:
    """密钥管理:AES-256-GCM 加密存储"""

    def __init__(self, master_key_file: str | Path | None = None, keychain_file: str | Path | None = None):
        """初始化密钥管理器

        - master_key_file: 主密钥存储文件路径,默认 data/.master_key
        - keychain_file: 密钥值存储文件路径,默认 data/keychain.json
        """
        self._master_key_file = Path(master_key_file) if master_key_file else _MASTER_KEY_FILE
        self._keychain_file = Path(keychain_file) if keychain_file else _KEYCHAIN_FILE
        self._master_key: bytes | None = None

    # ------------------------------------------------------------------
    # 主密钥管理
    # ------------------------------------------------------------------

    def _get_master_key(self) -> bytes:
        """获取主密钥

        优先级:
        1. 内存缓存
        2. 环境变量 NEBULA_MASTER_KEY (base64 编码的 32 字节)
        3. data/.master_key 文件 (base64 编码的 32 字节)
        4. 以上都没有: 生成新的 32 字节随机密钥,存储到文件
        """
        if self._master_key is not None:
            return self._master_key

        # 1. 尝试从环境变量读取
        env_key = os.environ.get("NEBULA_MASTER_KEY")
        if env_key:
            try:
                key = base64.b64decode(env_key)
                if len(key) == _KEY_LENGTH:
                    self._master_key = key
                    return key
            except Exception:
                pass  # 环境变量格式无效,继续尝试其他来源

        # 2. 尝试从文件读取
        if self._master_key_file.exists():
            try:
                file_key = self._master_key_file.read_text(encoding="utf-8").strip()
                key = base64.b64decode(file_key)
                if len(key) == _KEY_LENGTH:
                    self._master_key = key
                    return key
            except Exception:
                pass  # 文件损坏,继续重新生成

        # 3. 生成新密钥并存储
        key = secrets.token_bytes(_KEY_LENGTH)
        self._master_key_file.parent.mkdir(parents=True, exist_ok=True)
        self._master_key_file.write_text(
            base64.b64encode(key).decode("ascii"), encoding="utf-8"
        )
        self._master_key = key
        return key

    def _derive_key(self, password: str | bytes, salt: bytes) -> bytes:
        """HKDF 派生密钥

        从密码 + 盐派生 32 字节 AES-256 密钥
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 库未安装,无法派生密钥")
        if isinstance(password, str):
            password = password.encode("utf-8")
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=_KEY_LENGTH,
            salt=salt,
            info=b"nebula-keychain-key-derivation",
        )
        return hkdf.derive(password)

    # ------------------------------------------------------------------
    # 加密/解密核心
    # ------------------------------------------------------------------

    def _encrypt(self, plaintext: str | bytes, key: bytes) -> str:
        """AES-256-GCM 加密

        格式: base64(nonce(12) + ciphertext + tag)
        AESGCM 自动将 tag 附加到 ciphertext 末尾

        返回 base64 编码的字符串
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 库未安装,无法加密")
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        # ciphertext 已包含 tag
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def _decrypt(self, ciphertext_b64: str, key: bytes) -> str:
        """AES-256-GCM 解密

        输入: base64 编码的 nonce + ciphertext + tag
        返回明文字符串
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 库未安装,无法解密")
        combined = base64.b64decode(ciphertext_b64)
        nonce = combined[:_NONCE_LENGTH]
        ciphertext = combined[_NONCE_LENGTH:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def _generate_data_key(self) -> bytes:
        """生成随机 32 字节数据密钥"""
        return secrets.token_bytes(_KEY_LENGTH)

    # ------------------------------------------------------------------
    # 数据密钥(EncryptionKey 表)管理
    # ------------------------------------------------------------------

    async def _get_active_data_key(self, session: AsyncSession) -> tuple[str, bytes] | None:
        """获取当前活跃的数据密钥

        返回 (key_id, decrypted_data_key),无活跃密钥返回 None
        """
        stmt = (
            select(EncryptionKey)
            .where(EncryptionKey.is_active == True)  # noqa: E712
            .order_by(EncryptionKey.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        enc_key = result.scalars().first()
        if enc_key is None:
            return None

        master_key = self._get_master_key()
        data_key = base64.b64decode(self._decrypt(enc_key.encrypted_key, master_key))
        return (enc_key.key_id, data_key)

    async def _create_active_data_key(self, session: AsyncSession) -> tuple[str, bytes]:
        """创建新的活跃数据密钥

        生成随机数据密钥,用主密钥加密后存入 EncryptionKey 表
        返回 (key_id, data_key)
        """
        master_key = self._get_master_key()
        data_key = self._generate_data_key()
        encrypted_data_key = self._encrypt(base64.b64encode(data_key), master_key)
        key_id = str(uuid4())

        enc_key = EncryptionKey(
            key_id=key_id,
            key_type="AES-256-GCM",
            encrypted_key=encrypted_data_key,
            is_active=True,
        )
        session.add(enc_key)
        await session.commit()
        await session.refresh(enc_key)
        return (key_id, data_key)

    async def _get_or_create_data_key(self, session: AsyncSession) -> tuple[str, bytes]:
        """获取或创建活跃数据密钥"""
        existing = await self._get_active_data_key(session)
        if existing is not None:
            return existing
        return await self._create_active_data_key(session)

    async def _get_data_key_by_id(self, session: AsyncSession, key_id: str) -> bytes | None:
        """根据 key_id 获取解密后的数据密钥"""
        stmt = select(EncryptionKey).where(EncryptionKey.key_id == key_id)
        result = await session.execute(stmt)
        enc_key = result.scalars().first()
        if enc_key is None:
            return None
        master_key = self._get_master_key()
        data_key_b64 = self._decrypt(enc_key.encrypted_key, master_key)
        return base64.b64decode(data_key_b64)

    # ------------------------------------------------------------------
    # 密钥值文件管理
    # ------------------------------------------------------------------

    def _read_keychain_file(self) -> dict:
        """读取 keychain.json 文件"""
        if not self._keychain_file.exists():
            return {}
        try:
            return json.loads(self._keychain_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_keychain_file(self, data: dict) -> None:
        """写入 keychain.json 文件"""
        self._keychain_file.parent.mkdir(parents=True, exist_ok=True)
        self._keychain_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    async def store(
        self,
        session: AsyncSession,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> dict:
        """存储密钥

        - 获取或创建活跃数据密钥
        - 用数据密钥加密 value
        - 将加密后的 value 存储到 keychain.json
        """
        if not _CRYPTO_AVAILABLE:
            return {"error": "cryptography 库未安装,密钥存储不可用"}

        if not key:
            return {"error": "密钥名称不能为空"}

        key_id, data_key = await self._get_or_create_data_key(session)
        encrypted_value = self._encrypt(value, data_key)

        store_data = self._read_keychain_file()
        store_data[key] = {
            "ciphertext": encrypted_value,
            "key_id": key_id,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._write_keychain_file(store_data)

        return {
            "key": key,
            "stored": True,
            "key_id": key_id,
            "metadata": metadata or {},
        }

    async def get(self, session: AsyncSession, key: str) -> dict:
        """获取密钥

        - 从 keychain.json 读取加密的 value
        - 根据 key_id 获取数据密钥
        - 用数据密钥解密 value
        """
        if not _CRYPTO_AVAILABLE:
            return {"error": "cryptography 库未安装,密钥获取不可用"}

        store_data = self._read_keychain_file()
        if key not in store_data:
            return {"error": f"密钥 '{key}' 不存在"}

        entry = store_data[key]
        key_id = entry.get("key_id")
        if not key_id:
            return {"error": f"密钥 '{key}' 缺少 key_id"}

        data_key = await self._get_data_key_by_id(session, key_id)
        if data_key is None:
            return {"error": f"数据密钥 '{key_id}' 不存在或已失效"}

        try:
            plaintext = self._decrypt(entry["ciphertext"], data_key)
        except Exception as e:
            return {"error": f"解密失败: {e}"}

        return {
            "key": key,
            "value": plaintext,
            "metadata": entry.get("metadata", {}),
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
        }

    async def delete(self, session: AsyncSession, key: str) -> dict:
        """删除密钥"""
        store_data = self._read_keychain_file()
        if key not in store_data:
            return {"deleted": False, "error": f"密钥 '{key}' 不存在"}

        del store_data[key]
        self._write_keychain_file(store_data)
        return {"deleted": True, "key": key}

    async def list_keys(self, session: AsyncSession | None = None) -> dict:
        """列出所有密钥名称(不返回值)"""
        store_data = self._read_keychain_file()
        keys = []
        for key, entry in store_data.items():
            keys.append({
                "key": key,
                "key_id": entry.get("key_id"),
                "metadata": entry.get("metadata", {}),
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
            })
        return {"keys": keys, "count": len(keys)}

    def is_available(self) -> bool:
        """检查密钥管理功能是否可用(cryptography 库是否安装)"""
        return _CRYPTO_AVAILABLE


# 模块级单例
keychain = Keychain()
