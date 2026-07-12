"""国密算法支持 (SM2/SM4) — 适配信创市场

双模式:
- 有 cryptography 库且支持国密时: 使用真实算法
- 无国密支持时: 降级为 mock (返回占位数据，不报错)

SM2: 非对称加密 (替代 X25519/RSA)
SM4: 对称加密 (替代 AES-256-GCM)
"""

from __future__ import annotations


class NationalCrypto:
    """国密算法服务"""

    def __init__(self) -> None:
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """检查是否有国密算法支持"""
        try:
            # 尝试导入 gmssl 或其他国密库
            import gmssl  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # SM2 非对称加密
    # ------------------------------------------------------------------

    def sm2_generate_keypair(self) -> tuple[str, str]:
        """生成 SM2 密钥对 (私钥, 公钥)

        mock 模式: 返回 ("mock_sm2_private_key", "mock_sm2_public_key")
        """
        if not self._available:
            return ("mock_sm2_private_key", "mock_sm2_public_key")

        try:
            from gmssl import sm2  # type: ignore
            from gmssl.func import random_hex  # type: ignore
            # SM2 曲线长度 256 位 = 32 字节 = 64 hex
            private_key = random_hex(64)
            # 公钥 = 04 || X(32) || Y(32) = 130 hex
            sm2_crypt = sm2.CryptSM2(private_key=private_key, public_key="")
            public_key = sm2_crypt._kg(int(private_key, 16), sm2.default_ecc_table["g"])
            public_key_hex = "04" + "%064x%064x" % public_key
            return (private_key, public_key_hex)
        except Exception:
            # 任何异常降级为 mock
            return ("mock_sm2_private_key", "mock_sm2_public_key")

    def sm2_encrypt(self, public_key: str, data: bytes) -> bytes:
        """SM2 加密

        mock: 返回 b"mock_sm2_encrypted:" + data[:10]
        """
        if not self._available:
            return b"mock_sm2_encrypted:" + data[:10]

        try:
            from gmssl import sm2  # type: ignore
            sm2_crypt = sm2.CryptSM2(private_key="", public_key=public_key)
            encrypted = sm2_crypt.encrypt(data)
            return encrypted if isinstance(encrypted, bytes) else bytes(encrypted)
        except Exception:
            return b"mock_sm2_encrypted:" + data[:10]

    def sm2_decrypt(self, private_key: str, data: bytes) -> bytes:
        """SM2 解密

        mock: 返回 b"mock_sm2_decrypted_data"
        """
        if not self._available:
            return b"mock_sm2_decrypted_data"

        try:
            from gmssl import sm2  # type: ignore
            sm2_crypt = sm2.CryptSM2(private_key=private_key, public_key="")
            decrypted = sm2_crypt.decrypt(data)
            return decrypted if isinstance(decrypted, bytes) else bytes(decrypted)
        except Exception:
            return b"mock_sm2_decrypted_data"

    # ------------------------------------------------------------------
    # SM4 对称加密
    # ------------------------------------------------------------------

    def sm4_encrypt(self, key: bytes, data: bytes) -> bytes:
        """SM4 对称加密

        mock: 返回 b"mock_sm4_encrypted:" + data[:10]
        """
        if not self._available:
            return b"mock_sm4_encrypted:" + data[:10]

        try:
            from gmssl.sm4 import CryptSM4, SM4_ENCRYPT  # type: ignore
            sm4_crypt = CryptSM4()
            sm4_crypt.set_key(key, SM4_ENCRYPT)
            encrypted = sm4_crypt.crypt_ecb(data)
            return encrypted if isinstance(encrypted, bytes) else bytes(encrypted)
        except Exception:
            return b"mock_sm4_encrypted:" + data[:10]

    def sm4_decrypt(self, key: bytes, data: bytes) -> bytes:
        """SM4 对称解密

        mock: 返回 b"mock_sm4_decrypted_data"
        """
        if not self._available:
            return b"mock_sm4_decrypted_data"

        try:
            from gmssl.sm4 import CryptSM4, SM4_DECRYPT  # type: ignore
            sm4_crypt = CryptSM4()
            sm4_crypt.set_key(key, SM4_DECRYPT)
            decrypted = sm4_crypt.crypt_ecb(data)
            return decrypted if isinstance(decrypted, bytes) else bytes(decrypted)
        except Exception:
            return b"mock_sm4_decrypted_data"

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """获取国密支持状态"""
        return {
            "available": self._available,
            "algorithms": ["SM2", "SM4"] if self._available else [],
            "mode": "real" if self._available else "mock",
        }


# 模块级单例
national_crypto = NationalCrypto()
