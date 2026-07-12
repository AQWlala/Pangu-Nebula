"""技能跨实例 gift 服务 (Phase 5 v2.0.0 T5.5)

Pangu Nebula v2.0.0 阶段5(T5.5):
基于 E2EE 同步通道(server/services/sync_crypto.py)实现多实例间的技能 gift。
让用户可以在不同 Pangu Nebula 实例间赠送/同步技能包。

设计要点:
- 复用 SyncCryptoService 的 X25519 ECDH + HKDF + AES-256-GCM 加密栈
- gift 协议: 打包 .skill 内容 → 加密 → 包装为 gift 载荷 → 接收端解密 → 安装
- 跨实例传输在测试中以 mock 通道模拟(本地内存队列)

协议格式(SkillGift envelope):
    {
        "version": 1,
        "gift_id": "<uuid>",
        "from_instance": "<instance_id>",
        "to_instance": "<instance_id>",
        "encrypted_payload": {
            "ciphertext": "<base64>",
            "nonce": "<base64>",
            "tag": "<base64>"
        },
        "skill_name": "<hint, 不加密, 用于路由展示>",
        "skill_version": "<hint>",
        "created_at": "<ISO8601>",
        "checksum": "<sha256 of plaintext, 用于完整性校验>"
    }

注: skill_name/version 是明文 hint,用于在接收端展示礼物信息;
真实技能内容由 encrypted_payload 加密保护。
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .skill_package import SkillManifest, SkillPackager, SkillInstaller


# ===== 协议常量 =====

# gift 协议版本
GIFT_PROTOCOL_VERSION = 1


def _get_sync_crypto_service():
    """延迟导入 SyncCryptoService(避免循环依赖)"""
    from .sync_crypto import sync_crypto_service
    return sync_crypto_service


def _now_iso() -> str:
    """当前 UTC 时间 ISO 字符串"""
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    """计算 SHA256 hex"""
    return hashlib.sha256(data).hexdigest()


# ===== 模拟跨实例传输通道 =====
#
# 进程内内存队列,模拟两个实例间的网络传输。
# 真实场景下,这部分将由 E2EE 同步通道(relay_service)承担。

_TRANSIT_QUEUE: dict[str, list[dict[str, Any]]] = {}
"""_TRANSIT_QUEUE: to_instance -> [gift_envelope, ...]

每个实例有自己的收件箱,send_gift 投递到收件箱,
receive_gift 从收件箱拉取。
"""


class SkillGiftService:
    """技能跨实例 gift 服务

    提供完整的 gift 生命周期:
    1. create_gift: 打包技能为 .skill bytes,准备 gift 载荷
    2. encrypt_gift: 用对端公钥(共享密钥派生)加密技能内容
    3. send_gift: 通过传输通道发送给目标实例
    4. receive_gift: 接收并解密,可选自动安装

    典型流程:
        # 实例 A
        gift = await gift_service.create_gift(
            skill_name="my-skill",
            from_instance="instance-A",
            to_instance="instance-B",
            session_key=shared_key,
        )
        await gift_service.send_gift(gift)

        # 实例 B
        envelope = await gift_service.fetch_gift("instance-B")
        result = await gift_service.receive_gift(envelope, session_key=shared_key)

    注意: session_key 由调用方(配对服务)预先通过 ECDH 派生,
    本服务不处理密钥交换,仅做载荷加解密。
    """

    def __init__(self) -> None:
        # 已接收的 gift 历史(去重用)
        self._received_gift_ids: set[str] = set()

    # ===== gift 创建与加密 =====

    async def create_gift(
        self,
        skill_name: str,
        from_instance: str,
        to_instance: str,
        session_key: bytes,
        skill_loader: Any = None,
        skill_version: str | None = None,
    ) -> dict[str, Any]:
        """创建一个 gift envelope

        流程:
        1. 获取技能(从本地已安装的技能包读取,或从 SkillLoader 加载)
        2. 打包为 .skill 格式(JSON bytes)
        3. 计算 checksum(用于完整性校验)
        4. 用 session_key 加密 .skill 内容(AES-256-GCM)
        5. 包装为 gift envelope

        参数:
        - skill_name: 技能名(必须已安装到本地)
        - from_instance: 发送方实例 ID
        - to_instance: 接收方实例 ID
        - session_key: 预共享的会话密钥(由 ECDH 派生)
        - skill_loader: 可选的 SkillLoader(用于加载技能)
        - skill_version: 可选的版本提示(用于明文 hint)

        返回: gift envelope dict
        """
        crypto = _get_sync_crypto_service()

        # 1. 获取技能包内容(.skill bytes)
        # 优先从本地已安装的技能包读取
        installer = SkillInstaller()
        try:
            skill_bytes = await installer.export(skill_name)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"skill not installed locally: {skill_name}"
            ) from e

        # 2. 解析 manifest 以提取 hint
        manifest, _code = SkillPackager.unpack(skill_bytes)
        hint_version = skill_version or manifest.version

        # 3. 计算明文 checksum(用于完整性校验,接收端可对比)
        checksum = _sha256_hex(skill_bytes)

        # 4. 加密 .skill 内容
        plaintext_payload = {
            "skill_bytes_b64": base64.b64encode(skill_bytes).decode("ascii"),
            "skill_name": manifest.name,
            "skill_version": manifest.version,
        }
        encrypted = crypto.encrypt_payload(session_key, plaintext_payload)

        # 5. 包装为 gift envelope
        envelope = {
            "version": GIFT_PROTOCOL_VERSION,
            "gift_id": uuid.uuid4().hex,
            "from_instance": from_instance,
            "to_instance": to_instance,
            "encrypted_payload": encrypted,
            "skill_name": manifest.name,  # 明文 hint(用于展示)
            "skill_version": hint_version,  # 明文 hint
            "created_at": _now_iso(),
            "checksum": checksum,
        }
        return envelope

    async def create_gift_from_manifest(
        self,
        manifest: SkillManifest,
        code_bytes: bytes | None,
        from_instance: str,
        to_instance: str,
        session_key: bytes,
    ) -> dict[str, Any]:
        """从一个内存中的 manifest 创建 gift(无需预先安装)

        用于测试场景或运行时动态生成的技能。
        """
        crypto = _get_sync_crypto_service()

        # 打包 manifest 为 .skill bytes
        # 如果有 code_bytes,先用 base64 编码注入 manifest.code
        if code_bytes is not None and not manifest.code:
            manifest = manifest.model_copy(
                update={"code": base64.b64encode(code_bytes).decode("ascii")}
            )
        skill_bytes = SkillPackager.pack(manifest)

        # 计算 checksum
        checksum = _sha256_hex(skill_bytes)

        # 加密
        plaintext_payload = {
            "skill_bytes_b64": base64.b64encode(skill_bytes).decode("ascii"),
            "skill_name": manifest.name,
            "skill_version": manifest.version,
        }
        encrypted = crypto.encrypt_payload(session_key, plaintext_payload)

        return {
            "version": GIFT_PROTOCOL_VERSION,
            "gift_id": uuid.uuid4().hex,
            "from_instance": from_instance,
            "to_instance": to_instance,
            "encrypted_payload": encrypted,
            "skill_name": manifest.name,
            "skill_version": manifest.version,
            "created_at": _now_iso(),
            "checksum": checksum,
        }

    # ===== 传输(内存模拟) =====

    async def send_gift(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """发送 gift 到目标实例的收件箱

        在真实场景下,这会通过 E2EE 同步通道(relay_service)发送;
        此处使用内存队列模拟。

        返回: {"ok": True, "data": {"gift_id": ..., "delivered_to": ...}}
        """
        to_instance = envelope.get("to_instance")
        if not to_instance:
            return {"ok": False, "data": None, "error": "envelope missing to_instance"}

        _TRANSIT_QUEUE.setdefault(to_instance, []).append(envelope)
        return {
            "ok": True,
            "data": {
                "gift_id": envelope["gift_id"],
                "delivered_to": to_instance,
                "delivered_at": _now_iso(),
                "transport": "mock-in-memory",
            },
            "error": None,
        }

    async def fetch_gift(self, instance_id: str) -> dict[str, Any] | None:
        """从收件箱拉取一个 gift(先进先出)

        返回 envelope dict,若无礼物返回 None。
        """
        queue = _TRANSIT_QUEUE.get(instance_id, [])
        if not queue:
            return None
        return queue.pop(0)

    async def list_pending_gifts(self, instance_id: str) -> list[dict[str, Any]]:
        """列出收件箱中所有待接收的 gift(不弹出)"""
        return list(_TRANSIT_QUEUE.get(instance_id, []))

    # ===== 接收与解密 =====

    async def receive_gift(
        self,
        envelope: dict[str, Any],
        session_key: bytes,
        auto_install: bool = False,
        target_dir: Any = None,
    ) -> dict[str, Any]:
        """接收并解密 gift

        流程:
        1. 检查 envelope 协议版本
        2. 检查是否已接收过(去重)
        3. 解密 encrypted_payload
        4. 校验 checksum(完整性)
        5. 可选:auto_install=True 时安装到本地技能目录

        参数:
        - envelope: gift envelope dict
        - session_key: 与发送方共享的会话密钥
        - auto_install: 是否自动安装到本地
        - target_dir: 安装目录(auto_install=True 时生效)

        返回: {"ok": True, "data": {"skill_name", "skill_version", "installed", "checksum_valid"}}
        """
        # 1. 协议版本检查
        version = envelope.get("version")
        if version != GIFT_PROTOCOL_VERSION:
            return {
                "ok": False,
                "data": None,
                "error": f"unsupported gift protocol version: {version}",
            }

        # 2. 去重检查
        gift_id = envelope.get("gift_id")
        if gift_id and gift_id in self._received_gift_ids:
            return {
                "ok": False,
                "data": None,
                "error": f"gift already received: {gift_id}",
            }

        crypto = _get_sync_crypto_service()

        # 3. 解密
        encrypted = envelope.get("encrypted_payload")
        if not encrypted:
            return {"ok": False, "data": None, "error": "envelope missing encrypted_payload"}

        try:
            plaintext = crypto.decrypt_payload(session_key, encrypted)
        except Exception as e:
            return {"ok": False, "data": None, "error": f"decrypt failed: {e}"}

        # 4. 完整性校验
        skill_bytes_b64 = plaintext.get("skill_bytes_b64")
        if not skill_bytes_b64:
            return {"ok": False, "data": None, "error": "plaintext missing skill_bytes_b64"}

        try:
            skill_bytes = base64.b64decode(skill_bytes_b64)
        except Exception as e:
            return {"ok": False, "data": None, "error": f"invalid base64 skill content: {e}"}

        expected_checksum = envelope.get("checksum")
        actual_checksum = _sha256_hex(skill_bytes)
        checksum_valid = (expected_checksum == actual_checksum) if expected_checksum else False

        # 5. 可选安装
        installed = False
        install_path: str | None = None
        if auto_install:
            installer = (
                SkillInstaller() if target_dir is None else SkillInstaller(skills_dir=target_dir)
            )
            install_result = await installer.install(skill_bytes)
            if not install_result["ok"]:
                return {
                    "ok": False,
                    "data": None,
                    "error": f"auto-install failed: {install_result.get('error')}",
                }
            installed = True
            install_path = install_result["data"].get("path")

        # 6. 标记已接收(去重)
        if gift_id:
            self._received_gift_ids.add(gift_id)

        return {
            "ok": True,
            "data": {
                "gift_id": gift_id,
                "skill_name": plaintext.get("skill_name") or envelope.get("skill_name"),
                "skill_version": plaintext.get("skill_version") or envelope.get("skill_version"),
                "from_instance": envelope.get("from_instance"),
                "checksum_valid": checksum_valid,
                "installed": installed,
                "install_path": install_path,
                "received_at": _now_iso(),
            },
            "error": None,
        }

    # ===== 辅助方法 =====

    def clear_received_history(self) -> None:
        """清空已接收 gift 历史(用于测试)"""
        self._received_gift_ids.clear()

    def get_transit_queue_state(self) -> dict[str, int]:
        """获取传输队列状态(每个实例的待接收数量)"""
        return {k: len(v) for k, v in _TRANSIT_QUEUE.items()}


# 模块级单例
skill_gift_service = SkillGiftService()


def _reset_transit_for_testing() -> None:
    """重置传输队列(仅用于测试隔离)"""
    _TRANSIT_QUEUE.clear()
    skill_gift_service.clear_received_history()
