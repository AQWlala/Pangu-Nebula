"""Keychain service (Phase 8A)

AES-256-GCM encrypted key-value storage:
- Master Key: from env NEBULA_MASTER_KEY,
    else DPAPI-encrypted file (Windows),
    else file with 0600 permissions (Linux/macOS),
    else generate + store
- Data Key: random AES-256 key, encrypted with master key, stored in EncryptionKey table
- Values: encrypted with data key, stored in data/keychain.json

Platform support:
- Windows: DPAPI binds master key to user account
- Linux/macOS: restrictive file permissions (0600) with base64 encoding
"""

import base64
import json
import os
import secrets
import stat
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.orm import EncryptionKey

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False

_MASTER_KEY_FILE = Path("data/.master_key")
_KEYCHAIN_FILE = Path("data/keychain.json")
_KEY_LENGTH = 32
_NONCE_LENGTH = 12
_IS_WINDOWS = sys.platform == "win32"

# ------------------------------------------------------------------
# Platform-specific master key file encryption
# ------------------------------------------------------------------

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    def _platform_protect(data: bytes) -> bytes:
        """Windows DPAPI encrypt (user-account-bound)."""
        crypt32 = ctypes.windll.crypt32
        data_in = _DATA_BLOB(
            len(data),
            ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)),
        )
        data_out = _DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(data_in),
            None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(data_out),
        ):
            raise OSError("CryptProtectData failed")
        result = ctypes.string_at(data_out.pbData, data_out.cbData)
        crypt32.LocalFree(data_out.pbData)
        return result

    def _platform_unprotect(data: bytes) -> bytes:
        """Windows DPAPI decrypt."""
        crypt32 = ctypes.windll.crypt32
        data_in = _DATA_BLOB(
            len(data),
            ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)),
        )
        data_out = _DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(data_in),
            None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(data_out),
        ):
            raise OSError("CryptUnprotectData failed")
        result = ctypes.string_at(data_out.pbData, data_out.cbData)
        crypt32.LocalFree(data_out.pbData)
        return result

else:
    # Linux / macOS: no OS-level key encryption available without extra deps.
    # Use restrictive file permissions (owner-read-only) as the primary
    # defence; the key is base64-encoded at rest.

    def _platform_protect(data: bytes) -> bytes:
        """Passthrough; file permissions provide the security boundary."""
        return data

    def _platform_unprotect(data: bytes) -> bytes:
        """Passthrough."""
        return data


class Keychain:
    """Keychain: AES-256-GCM encrypted storage with platform-protected master key."""

    def __init__(self, master_key_file: str | Path | None = None, keychain_file: str | Path | None = None):
        self._master_key_file = Path(master_key_file) if master_key_file else _MASTER_KEY_FILE
        self._keychain_file = Path(keychain_file) if keychain_file else _KEYCHAIN_FILE
        self._master_key: bytes | None = None

    # ------------------------------------------------------------------
    # Master key: env var > platform-protected file > generate + store
    # ------------------------------------------------------------------

    def _get_master_key(self) -> bytes:
        if self._master_key is not None:
            return self._master_key

        # 1. Environment variable
        env_key = os.environ.get("NEBULA_MASTER_KEY")
        if env_key:
            try:
                key = base64.b64decode(env_key)
                if len(key) == _KEY_LENGTH:
                    self._master_key = key
                    return key
            except Exception:
                pass

        # 2. Platform-protected file
        if self._master_key_file.exists():
            try:
                raw = self._master_key_file.read_bytes()
                raw = _platform_unprotect(raw)
                key = base64.b64decode(raw.decode("ascii").strip())
                if len(key) == _KEY_LENGTH:
                    self._master_key = key
                    # Re-encrypt to upgrade legacy plaintext files
                    if _IS_WINDOWS:
                        self._write_master_key_file(key)
                    return key
            except Exception:
                pass

        # 3. Generate new key
        key = secrets.token_bytes(_KEY_LENGTH)
        self._write_master_key_file(key)
        self._master_key = key
        return key

    def _write_master_key_file(self, key: bytes) -> None:
        self._master_key_file.parent.mkdir(parents=True, exist_ok=True)
        encoded = base64.b64encode(key)
        data = _platform_protect(encoded)
        self._master_key_file.write_bytes(data)
        # On Unix, restrict to owner read/write only
        if not _IS_WINDOWS:
            try:
                os.chmod(self._master_key_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # best-effort

    # ------------------------------------------------------------------
    # Key derivation
    # ------------------------------------------------------------------

    def _derive_key(self, password: str | bytes, salt: bytes) -> bytes:
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not installed")
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
    # AES-256-GCM encrypt / decrypt
    # ------------------------------------------------------------------

    def _encrypt(self, plaintext: str | bytes, key: bytes) -> str:
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not installed")
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, ciphertext_b64: str, key: bytes) -> str:
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library not installed")
        combined = base64.b64decode(ciphertext_b64)
        nonce = combined[:_NONCE_LENGTH]
        ciphertext = combined[_NONCE_LENGTH:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")

    def _generate_data_key(self) -> bytes:
        return secrets.token_bytes(_KEY_LENGTH)

    # ------------------------------------------------------------------
    # Data key (EncryptionKey table) management
    # ------------------------------------------------------------------

    async def _get_active_data_key(self, session: AsyncSession) -> tuple[str, bytes] | None:
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
        existing = await self._get_active_data_key(session)
        if existing is not None:
            return existing
        return await self._create_active_data_key(session)

    async def _get_data_key_by_id(self, session: AsyncSession, key_id: str) -> bytes | None:
        stmt = select(EncryptionKey).where(EncryptionKey.key_id == key_id)
        result = await session.execute(stmt)
        enc_key = result.scalars().first()
        if enc_key is None:
            return None
        master_key = self._get_master_key()
        return base64.b64decode(self._decrypt(enc_key.encrypted_key, master_key))

    # ------------------------------------------------------------------
    # Keychain file (JSON) management
    # ------------------------------------------------------------------

    def _read_keychain_file(self) -> dict:
        if not self._keychain_file.exists():
            return {}
        try:
            return json.loads(self._keychain_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_keychain_file(self, data: dict) -> None:
        self._keychain_file.parent.mkdir(parents=True, exist_ok=True)
        self._keychain_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        session: AsyncSession,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> dict:
        if not _CRYPTO_AVAILABLE:
            return {"error": "cryptography library not installed"}
        if not key:
            return {"error": "Key name cannot be empty"}
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
        return {"key": key, "stored": True, "key_id": key_id, "metadata": metadata or {}}

    async def get(self, session: AsyncSession, key: str) -> dict:
        if not _CRYPTO_AVAILABLE:
            return {"error": "cryptography library not installed"}
        store_data = self._read_keychain_file()
        if key not in store_data:
            return {"error": f"Key '{key}' not found"}
        entry = store_data[key]
        key_id = entry.get("key_id")
        if not key_id:
            return {"error": f"Key '{key}' missing key_id"}
        data_key = await self._get_data_key_by_id(session, key_id)
        if data_key is None:
            return {"error": f"Data key '{key_id}' not found or lost"}
        try:
            plaintext = self._decrypt(entry["ciphertext"], data_key)
        except Exception as e:
            return {"error": f"Decryption failed: {e}"}
        return {
            "key": key,
            "value": plaintext,
            "metadata": entry.get("metadata", {}),
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
        }

    async def delete(self, session: AsyncSession, key: str) -> dict:
        store_data = self._read_keychain_file()
        if key not in store_data:
            return {"deleted": False, "error": f"Key '{key}' not found"}
        del store_data[key]
        self._write_keychain_file(store_data)
        return {"deleted": True, "key": key}

    async def list_keys(self, session: AsyncSession | None = None) -> dict:
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
        return _CRYPTO_AVAILABLE


# Module-level singleton
keychain = Keychain()
