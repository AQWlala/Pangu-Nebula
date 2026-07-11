"""E2EE 端到端加密服务(Phase 9A)

为多设备同步提供端到端加密能力:
- X25519 椭圆曲线 Diffie-Hellman 密钥交换(每设备一对密钥)
- HKDF-SHA256 密钥派生(从共享密钥派生会话密钥)
- AES-256-GCM 对称加密(加密同步载荷)

典型流程:
1. 设备 A 调用 generate_device_keypair() 生成 (private, public) PEM
2. 设备 B 同样生成,双方通过带外(配对码/QR)交换 public key
3. compute_shared_secret(my_private, peer_public) 各自算出相同的共享密钥
4. derive_session_key(shared_secret, device_id) 派生会话密钥
5. encrypt_payload(key, data) 加密,decrypt_payload(key, encrypted) 解密

融合来源:
- Signal 协议的 X3DH 简化版
- WebRTC DTLS-SRTP 的密钥派生模式
"""

from __future__ import annotations

import base64
import json
import secrets

# 延迟导入 cryptography,失败时标记不可用
try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes, serialization
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False


# 会话密钥长度(字节):AES-256 需要 32 字节
_SESSION_KEY_LENGTH = 32
# GCM nonce 长度(字节):推荐 12 字节
_GCM_NONCE_LENGTH = 12
# 配对码位数
_PAIRING_CODE_LENGTH = 6


# ----------------------------------------------------------------------
# 底层加密原语(模块级函数)
# ----------------------------------------------------------------------


def generate_keypair() -> tuple[bytes, bytes]:
    """生成 X25519 密钥对

    返回 (private_key_bytes, public_key_bytes),均为原始字节(Raw 格式)
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography 库未安装,无法生成密钥对")
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_bytes, public_bytes


def derive_key(
    shared_secret: bytes,
    salt: bytes | None,
    info: bytes,
    length: int = _SESSION_KEY_LENGTH,
) -> bytes:
    """HKDF-SHA256 密钥派生

    - shared_secret: X25519 共享密钥
    - salt: 盐值(可为 None)
    - info: 上下文信息(如设备 ID)
    - length: 输出密钥长度,默认 32 字节(AES-256)
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography 库未安装,无法派生密钥")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    )
    return hkdf.derive(shared_secret)


def encrypt(
    key: bytes,
    plaintext: bytes,
    aad: bytes | None = None,
) -> tuple[bytes, bytes, bytes]:
    """AES-256-GCM 加密

    返回 (ciphertext, nonce, tag):
    - ciphertext: 密文(不含 tag)
    - nonce: 12 字节随机 nonce
    - tag: 16 字节认证 tag
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography 库未安装,无法加密")
    nonce = secrets.token_bytes(_GCM_NONCE_LENGTH)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt 返回 ciphertext + tag(拼接)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
    # tag 固定 16 字节,附加在末尾
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return ciphertext, nonce, tag


def decrypt(
    key: bytes,
    ciphertext: bytes,
    nonce: bytes,
    tag: bytes,
    aad: bytes | None = None,
) -> bytes:
    """AES-256-GCM 解密

    输入 (ciphertext, nonce, tag),返回明文字节
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography 库未安装,无法解密")
    aesgcm = AESGCM(key)
    # AESGCM.decrypt 期望 ciphertext + tag 拼接
    ct_with_tag = ciphertext + tag
    return aesgcm.decrypt(nonce, ct_with_tag, aad)


# ----------------------------------------------------------------------
# SyncCryptoService: 模块级单例
# ----------------------------------------------------------------------


class SyncCryptoService:
    """E2EE 端到端加密服务

    封装密钥对生成、共享密钥计算、会话密钥派生、载荷加解密、
    配对码/二维码生成等高层接口。所有输入输出均为 base64 字符串
    或 dict,便于 JSON 传输。
    """

    # ===== 密钥对管理 =====

    def generate_device_keypair(self) -> tuple[str, str]:
        """生成设备密钥对

        返回 (private_key_pem, public_key_pem),均为 PEM 格式字符串
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 库未安装,无法生成密钥对")
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        return private_pem, public_pem

    def compute_shared_secret(self, my_private_pem: str, peer_public_pem: str) -> bytes:
        """计算共享密钥

        - my_private_pem: 本设备私钥 PEM
        - peer_public_pem: 对端设备公钥 PEM
        - 返回: X25519 ECDH 共享密钥(原始字节)
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 库未安装,无法计算共享密钥")
        private_key = serialization.load_pem_private_key(
            my_private_pem.encode("ascii"), password=None
        )
        peer_public = serialization.load_pem_public_key(
            peer_public_pem.encode("ascii")
        )
        # X25519 私钥与对端公钥交换
        shared = private_key.exchange(peer_public)
        return shared

    def derive_session_key(self, shared_secret: bytes, device_id: str) -> bytes:
        """派生会话密钥(HKDF)

        - shared_secret: ECDH 共享密钥
        - device_id: 设备标识,作为 HKDF 的 info,确保不同设备会话密钥不同
        - 返回: 32 字节 AES-256 会话密钥
        """
        info = f"nebula-sync-session:{device_id}".encode("utf-8")
        # salt 使用固定值(也可从 shared_secret 派生),保证两端一致
        salt = b"nebula-sync-salt-v1"
        return derive_key(shared_secret, salt=salt, info=info, length=_SESSION_KEY_LENGTH)

    # ===== 载荷加解密 =====

    def encrypt_payload(self, key: bytes, data: dict) -> dict:
        """加密载荷

        - key: 会话密钥
        - data: 明文 dict(会先 JSON 序列化)
        - 返回: {ciphertext, nonce, tag},均为 base64 字符串
        """
        plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
        ciphertext, nonce, tag = encrypt(key, plaintext, aad=None)
        return {
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
        }

    def decrypt_payload(self, key: bytes, encrypted: dict) -> dict:
        """解密载荷

        - key: 会话密钥
        - encrypted: {ciphertext, nonce, tag},均为 base64 字符串
        - 返回: 明文 dict
        """
        ciphertext = base64.b64decode(encrypted["ciphertext"])
        nonce = base64.b64decode(encrypted["nonce"])
        tag = base64.b64decode(encrypted["tag"])
        plaintext = decrypt(key, ciphertext, nonce, tag, aad=None)
        return json.loads(plaintext.decode("utf-8"))

    # ===== 配对码与二维码 =====

    def generate_pairing_code(self) -> str:
        """生成 6 位数字配对码(用于人工确认设备配对)"""
        # 生成 000000-999999 的 6 位数字码
        code = secrets.randbelow(10 ** _PAIRING_CODE_LENGTH)
        return str(code).zfill(_PAIRING_CODE_LENGTH)

    def generate_qr_payload(
        self,
        device_id: str,
        public_key: str,
        pairing_code: str,
    ) -> str:
        """生成二维码载荷

        将设备信息打包为 JSON,再 base64 编码,便于扫码传输:
        - device_id: 设备 ID
        - public_key: 设备公钥 PEM
        - pairing_code: 配对码

        返回: base64 编码的 JSON 字符串
        """
        payload = {
            "device_id": device_id,
            "public_key": public_key,
            "pairing_code": pairing_code,
            "version": 1,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def parse_qr_payload(self, qr_payload: str) -> dict:
        """解析二维码载荷(返回 dict)"""
        raw = base64.b64decode(qr_payload.encode("ascii"))
        return json.loads(raw.decode("utf-8"))

    def is_available(self) -> bool:
        """检查加密功能是否可用(cryptography 库是否安装)"""
        return _CRYPTO_AVAILABLE


# 模块级单例
sync_crypto_service = SyncCryptoService()
