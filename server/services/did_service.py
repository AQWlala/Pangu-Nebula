"""DID 去中心化身份服务(Phase 8C)

基于 Ed25519 + did:key 方法实现去中心化身份:
- 生成 Ed25519 密钥对
- 公钥通过 multicodec(0xed01) + base58btc 编码为 did:key:z6Mk... 格式
- 私钥加密存储(base64 简化加密,实际应用应使用 Keychain)
- 支持 Ed25519 签名与验签

融合来源:
- Nebula 的 DID 去中心化身份设计
- W3C did:key 规范(https://w3c-ccg.github.io/did-method-key/)
"""

import base64

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import DidKey


# Ed25519 的 multicodec prefix(指示公钥类型)
_ED25519_MULTICODEC = b"\xed\x01"


def _has_ed25519() -> bool:
    """检查 cryptography 库的 ed25519 模块是否可用"""
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
        return True
    except ImportError:
        return False


def _b58encode(data: bytes) -> str:
    """base58btc 编码,未安装 base58 库时回退到 base64url"""
    try:
        import base58
        return base58.b58encode(data).decode()
    except ImportError:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b58decode(data: str) -> bytes:
    """base58btc 解码,未安装 base58 库时回退到 base64url"""
    try:
        import base58
        return base58.b58decode(data)
    except ImportError:
        padding = "=" * (4 - len(data) % 4) if len(data) % 4 else ""
        return base64.urlsafe_b64decode(data + padding)


class DIDService:
    """DID 去中心化身份服务(Ed25519 + did:key)"""

    # ===== 密钥与 DID 编码 =====

    def _generate_keypair(self) -> tuple[bytes, bytes]:
        """生成 Ed25519 密钥对

        返回 (private_key_bytes, public_key_bytes)
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PrivateFormat,
            PublicFormat,
            NoEncryption,
        )
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return private_bytes, public_bytes

    def _public_key_to_did(self, public_key_bytes: bytes) -> str:
        """公钥转 did:key

        格式: did:key:z + base58(multicodec_prefix + public_key)
        Ed25519 multicodec prefix = 0xed01
        """
        multicodec = _ED25519_MULTICODEC + public_key_bytes
        encoded = _b58encode(multicodec)
        return f"did:key:z{encoded}"

    def _did_to_public_key(self, did: str) -> bytes:
        """从 did:key 解析出原始公钥字节

        去掉 "did:key:z" 前缀,base58 解码,再去掉前2字节 multicodec prefix
        """
        encoded = did.replace("did:key:z", "").replace("did:key:", "")
        decoded = _b58decode(encoded)
        # 去掉 multicodec prefix(前2字节)
        if len(decoded) >= 2 and decoded[0] == 0xED and decoded[1] == 0x01:
            return decoded[2:]
        # 兼容:未知 prefix 时直接返回(可能未带 prefix)
        return decoded[2:] if len(decoded) > 32 else decoded

    def _encrypt_private_key(self, private_key: bytes) -> str:
        """加密私钥(简化实现:base64 编码)

        实际应用应使用 Keychain / Fernet 等加密方案
        """
        return base64.b64encode(private_key).decode()

    def _decrypt_private_key(self, encrypted: str) -> bytes:
        """解密私钥(base64 解码)"""
        return base64.b64decode(encrypted)

    def _did_to_dict(self, did_key: DidKey) -> dict:
        """ORM 对象转 dict"""
        return {
            "id": did_key.id,
            "persona_id": did_key.persona_id,
            "did": did_key.did,
            "method": did_key.method,
            "public_key": did_key.public_key,
            "key_type": did_key.key_type,
            "active": bool(did_key.active),
            "created_at": did_key.created_at.isoformat() if did_key.created_at else None,
        }

    # ===== 对外接口 =====

    async def create_did(
        self, persona_id: int | None = None, key_type: str = "Ed25519"
    ) -> dict:
        """创建 DID

        - 生成 Ed25519 密钥对
        - 构建 did:key:z6Mk... 格式的 DID
        - 私钥加密存储,创建 DidKey 记录
        """
        if not _has_ed25519():
            raise RuntimeError("cryptography 库未安装 Ed25519 支持,无法创建 DID")
        if key_type != "Ed25519":
            raise ValueError(f"暂不支持的密钥类型: {key_type}(仅支持 Ed25519)")

        private_bytes, public_bytes = self._generate_keypair()
        did = self._public_key_to_did(public_bytes)
        public_key_b58 = _b58encode(public_bytes)
        private_enc = self._encrypt_private_key(private_bytes)

        async with async_session() as session:
            did_key = DidKey(
                persona_id=persona_id,
                did=did,
                method="key",
                public_key=public_key_b58,
                private_key_enc=private_enc,
                key_type=key_type,
                active=True,
            )
            session.add(did_key)
            await session.commit()
            await session.refresh(did_key)
            return {
                **self._did_to_dict(did_key),
                "private_key_enc": private_enc,  # 仅创建时返回一次,便于备份
            }

    async def list_dids(self, persona_id: int | None = None) -> list[dict]:
        """列出 DID

        - persona_id 为 None: 列出所有
        - persona_id 有值: 仅列出该 Persona 的 DID
        """
        async with async_session() as session:
            stmt = select(DidKey).order_by(DidKey.created_at.desc())
            if persona_id is not None:
                stmt = stmt.where(DidKey.persona_id == persona_id)
            result = await session.execute(stmt)
            return [self._did_to_dict(dk) for dk in result.scalars().all()]

    async def get_did(self, did_id: int) -> dict | None:
        """获取单个 DID"""
        async with async_session() as session:
            did_key = await session.get(DidKey, did_id)
            return self._did_to_dict(did_key) if did_key else None

    async def sign(self, did_id: int, message: str) -> dict:
        """用 DID 的私钥对消息签名

        返回 {"signature": "base64...", "did": "...", "message": "..."}
        """
        if not _has_ed25519():
            raise RuntimeError("cryptography 库未安装 Ed25519 支持,无法签名")

        async with async_session() as session:
            did_key = await session.get(DidKey, did_id)
            if did_key is None:
                raise ValueError(f"DID not found: {did_id}")
            if not did_key.active:
                raise ValueError(f"DID 已停用: {did_id}")
            private_enc = did_key.private_key_enc
            did = did_key.did

        # 解密私钥并签名
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        private_bytes = self._decrypt_private_key(private_enc)
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        signature = private_key.sign(message.encode("utf-8"))
        return {
            "signature": base64.b64encode(signature).decode(),
            "did": did,
            "message": message,
        }

    async def verify(self, did: str, message: str, signature: str) -> dict:
        """验证签名

        - 从 did 解析出公钥
        - 用 Ed25519 验证签名
        - 返回 {"valid": bool, "did": "...", "message": "..."}
        """
        if not _has_ed25519():
            raise RuntimeError("cryptography 库未安装 Ed25519 支持,无法验签")

        try:
            public_bytes = self._did_to_public_key(did)
            sig_bytes = base64.b64decode(signature)
        except Exception:
            return {"valid": False, "did": did, "message": message}

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
            public_key.verify(sig_bytes, message.encode("utf-8"))
            return {"valid": True, "did": did, "message": message}
        except Exception:
            return {"valid": False, "did": did, "message": message}

    async def deactivate_did(self, did_id: int) -> dict | None:
        """停用 DID(active=False),不删除记录"""
        async with async_session() as session:
            did_key = await session.get(DidKey, did_id)
            if did_key is None:
                return None
            did_key.active = False
            await session.commit()
            await session.refresh(did_key)
            return self._did_to_dict(did_key)

    async def delete_did(self, did_id: int) -> bool:
        """删除 DID"""
        async with async_session() as session:
            did_key = await session.get(DidKey, did_id)
            if did_key is None:
                return False
            await session.delete(did_key)
            await session.commit()
            return True


# 模块级单例
did_service = DIDService()
