"""技能跨实例 gift 测试 (T5.5)

覆盖:
1. SkillGiftService 可实例化
2. create_gift_from_manifest 创建 envelope
3. send_gift 投递到内存通道
4. fetch_gift / list_pending_gifts 收件箱查询
5. receive_gift 解密并返回技能内容
6. auto_install=True 时自动安装到本地
7. 完整的端到端 gift 流程(create→send→fetch→receive)
8. 去重(同一 gift_id 重复接收应被拒绝)
9. 协议版本不匹配应被拒绝
10. 错误的 session_key 解密应失败
11. checksum 完整性校验
12. E2EE 加密验证(ciphertext 不包含明文技能名)
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from server.services.skill_gift import (
    SkillGiftService,
    skill_gift_service,
    _reset_transit_for_testing,
    GIFT_PROTOCOL_VERSION,
)
from server.services.skill_package import SkillManifest, SkillPackager, SkillInstaller
from server.services.sync_crypto import sync_crypto_service


# ===== Fixtures =====


@pytest.fixture
def crypto_available():
    """检查 cryptography 是否可用,否则跳过"""
    if not sync_crypto_service.is_available():
        pytest.skip("cryptography 库未安装,跳过 gift 加密测试")
    return sync_crypto_service


@pytest.fixture
def two_instances_keys(crypto_available):
    """生成两个实例的密钥对,并派生共享会话密钥"""
    crypto = crypto_available
    # 实例 A 与 B 各自的密钥对
    a_priv, a_pub = crypto.generate_device_keypair()
    b_priv, b_pub = crypto.generate_device_keypair()
    # 共享密钥(由 A 的私钥 + B 的公钥 计算得到)
    shared = crypto.compute_shared_secret(a_priv, b_pub)
    # 会话密钥(派生)
    session_key = crypto.derive_session_key(shared, "instance-B")
    return {
        "session_key": session_key,
        "a_priv": a_priv,
        "a_pub": a_pub,
        "b_priv": b_priv,
        "b_pub": b_pub,
    }


@pytest.fixture
def clean_gift_service():
    """每个测试用例前清空传输队列与已接收历史"""
    _reset_transit_for_testing()
    yield skill_gift_service
    _reset_transit_for_testing()


# ===== 1. SkillGiftService 可实例化 =====


def test_skill_gift_service_instantiable():
    """SkillGiftService 应可实例化,且模块级单例存在"""
    svc = SkillGiftService()
    assert svc is not None
    assert skill_gift_service is not None
    assert isinstance(skill_gift_service, SkillGiftService)


def test_get_transit_queue_state_initial(clean_gift_service):
    """初始传输队列状态应为空 dict"""
    state = clean_gift_service.get_transit_queue_state()
    assert state == {}


# ===== 2. create_gift_from_manifest =====


async def test_create_gift_from_manifest(clean_gift_service, two_instances_keys):
    """create_gift_from_manifest 应生成有效的 envelope"""
    manifest = SkillManifest(
        name="gift-skill",
        version="1.0.0",
        description="a gift skill",
        author="alice",
    )
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="instance-A",
        to_instance="instance-B",
        session_key=two_instances_keys["session_key"],
    )

    # 检查 envelope 字段
    assert envelope["version"] == GIFT_PROTOCOL_VERSION
    assert envelope["from_instance"] == "instance-A"
    assert envelope["to_instance"] == "instance-B"
    assert envelope["skill_name"] == "gift-skill"
    assert envelope["skill_version"] == "1.0.0"
    assert "gift_id" in envelope
    assert "created_at" in envelope
    assert len(envelope["checksum"]) == 64  # SHA256

    # encrypted_payload 应包含 ciphertext/nonce/tag
    enc = envelope["encrypted_payload"]
    assert "ciphertext" in enc
    assert "nonce" in enc
    assert "tag" in enc


async def test_create_gift_with_code(clean_gift_service, two_instances_keys):
    """create_gift_from_manifest 应能注入代码"""
    code = b"def handler():\n    return 'gift'\n"
    manifest = SkillManifest(name="code-gift", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=code,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )
    assert envelope["skill_name"] == "code-gift"


# ===== 3. send_gift =====


async def test_send_gift(clean_gift_service, two_instances_keys):
    """send_gift 应将 envelope 投递到目标实例的收件箱"""
    manifest = SkillManifest(name="send-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    result = await clean_gift_service.send_gift(envelope)
    assert result["ok"] is True
    assert result["data"]["delivered_to"] == "B"
    assert result["data"]["gift_id"] == envelope["gift_id"]
    assert result["data"]["transport"] == "mock-in-memory"

    # 收件箱应有 1 个待接收
    state = clean_gift_service.get_transit_queue_state()
    assert state.get("B") == 1


async def test_send_gift_missing_to_instance(clean_gift_service, two_instances_keys):
    """envelope 缺少 to_instance 应失败"""
    manifest = SkillManifest(name="bad", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )
    # 删除 to_instance
    del envelope["to_instance"]
    result = await clean_gift_service.send_gift(envelope)
    assert result["ok"] is False
    assert "to_instance" in result["error"]


# ===== 4. fetch_gift / list_pending_gifts =====


async def test_fetch_and_list_pending(clean_gift_service, two_instances_keys):
    """fetch_gift 弹出元素,list_pending_gifts 不弹出"""
    manifest = SkillManifest(name="fetch-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )
    await clean_gift_service.send_gift(envelope)

    # list_pending 应有 1 个
    pending = await clean_gift_service.list_pending_gifts("B")
    assert len(pending) == 1
    assert pending[0]["gift_id"] == envelope["gift_id"]

    # fetch 应返回该元素
    fetched = await clean_gift_service.fetch_gift("B")
    assert fetched is not None
    assert fetched["gift_id"] == envelope["gift_id"]

    # 再次 list_pending 应为空(fetch 已弹出)
    pending_after = await clean_gift_service.list_pending_gifts("B")
    assert len(pending_after) == 0


async def test_fetch_gift_empty(clean_gift_service):
    """空收件箱 fetch 应返回 None"""
    result = await clean_gift_service.fetch_gift("nonexistent-instance")
    assert result is None


# ===== 5. receive_gift =====


async def test_receive_gift(clean_gift_service, two_instances_keys):
    """receive_gift 应正确解密并返回技能信息"""
    manifest = SkillManifest(
        name="receive-test",
        version="2.5.0",
        description="a received skill",
    )
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    result = await clean_gift_service.receive_gift(
        envelope,
        session_key=two_instances_keys["session_key"],
        auto_install=False,
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["skill_name"] == "receive-test"
    assert data["skill_version"] == "2.5.0"
    assert data["from_instance"] == "A"
    assert data["installed"] is False
    assert data["checksum_valid"] is True
    assert "received_at" in data


# ===== 6. auto_install =====


async def test_receive_gift_auto_install(clean_gift_service, two_instances_keys, tmp_path):
    """auto_install=True 应安装到指定目录"""
    code = b"def handler():\n    return 'installed'\n"
    manifest = SkillManifest(name="auto-install-skill", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=code,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    result = await clean_gift_service.receive_gift(
        envelope,
        session_key=two_instances_keys["session_key"],
        auto_install=True,
        target_dir=tmp_path,
    )
    assert result["ok"] is True
    assert result["data"]["installed"] is True
    # 文件应存在
    assert (tmp_path / "auto-install-skill.skill").exists()
    assert (tmp_path / "auto-install-skill.py").exists()


# ===== 7. 端到端流程 =====


async def test_end_to_end_gift_flow(clean_gift_service, two_instances_keys, tmp_path):
    """完整流程: A 创建 → A 发送 → B 拉取 → B 接收并安装"""
    # 实例 A: 创建 gift
    code = b"def handler():\n    return 'gifted'\n"
    manifest = SkillManifest(
        name="e2e-skill",
        version="3.1.0",
        description="end-to-end test",
        author="alice",
    )
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=code,
        from_instance="instance-A",
        to_instance="instance-B",
        session_key=two_instances_keys["session_key"],
    )

    # 实例 A: 发送到 B 的收件箱
    send_result = await clean_gift_service.send_gift(envelope)
    assert send_result["ok"] is True

    # 实例 B: 拉取
    fetched = await clean_gift_service.fetch_gift("instance-B")
    assert fetched is not None
    assert fetched["gift_id"] == envelope["gift_id"]

    # 实例 B: 接收并自动安装
    receive_result = await clean_gift_service.receive_gift(
        fetched,
        session_key=two_instances_keys["session_key"],
        auto_install=True,
        target_dir=tmp_path,
    )
    assert receive_result["ok"] is True
    assert receive_result["data"]["skill_name"] == "e2e-skill"
    assert receive_result["data"]["skill_version"] == "3.1.0"
    assert receive_result["data"]["installed"] is True

    # 验证安装的技能文件内容
    skill_file = tmp_path / "e2e-skill.skill"
    assert skill_file.exists()
    # 重新解包验证
    manifest_loaded, code_loaded = SkillPackager.unpack(skill_file.read_bytes())
    assert manifest_loaded.name == "e2e-skill"
    assert code_loaded == code


# ===== 8. 去重 =====


async def test_receive_gift_deduplication(clean_gift_service, two_instances_keys):
    """同一 gift_id 重复接收应被拒绝"""
    manifest = SkillManifest(name="dedup-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    # 第一次接收应成功
    r1 = await clean_gift_service.receive_gift(
        envelope, session_key=two_instances_keys["session_key"]
    )
    assert r1["ok"] is True

    # 第二次接收应失败(去重)
    r2 = await clean_gift_service.receive_gift(
        envelope, session_key=two_instances_keys["session_key"]
    )
    assert r2["ok"] is False
    assert "already received" in r2["error"]


# ===== 9. 协议版本不匹配 =====


async def test_receive_gift_wrong_version(clean_gift_service, two_instances_keys):
    """协议版本不匹配应被拒绝"""
    manifest = SkillManifest(name="ver-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )
    envelope["version"] = 999  # 未知版本

    result = await clean_gift_service.receive_gift(
        envelope, session_key=two_instances_keys["session_key"]
    )
    assert result["ok"] is False
    assert "version" in result["error"].lower()


# ===== 10. 错误的 session_key 解密失败 =====


async def test_receive_gift_wrong_key(clean_gift_service, two_instances_keys, crypto_available):
    """错误的 session_key 解密应失败"""
    crypto = crypto_available
    manifest = SkillManifest(name="wrong-key-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    # 用一个无关的密钥
    other_priv, other_pub = crypto.generate_device_keypair()
    fake_shared = crypto.compute_shared_secret(other_priv, two_instances_keys["b_pub"])
    wrong_key = crypto.derive_session_key(fake_shared, "instance-B")

    result = await clean_gift_service.receive_gift(
        envelope, session_key=wrong_key
    )
    assert result["ok"] is False
    assert "decrypt" in result["error"].lower()


# ===== 11. checksum 完整性 =====


async def test_receive_gift_checksum_tampered(clean_gift_service, two_instances_keys):
    """篡改 checksum 应使完整性校验失败"""
    manifest = SkillManifest(name="tamper-test", version="1.0.0")
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=None,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )
    # 篡改 checksum
    envelope["checksum"] = "0" * 64

    # 注意: 篡改 checksum 不影响解密,只影响 checksum_valid 字段
    result = await clean_gift_service.receive_gift(
        envelope, session_key=two_instances_keys["session_key"]
    )
    assert result["ok"] is True  # 仍然成功
    assert result["data"]["checksum_valid"] is False  # 但 checksum 不匹配


# ===== 12. E2EE 加密验证 =====


async def test_gift_payload_encrypted(clean_gift_service, two_instances_keys):
    """envelope 的 ciphertext 不应包含明文技能内容(加密验证)"""
    code = b"def handler():\n    return 'secret-content'\n"
    manifest = SkillManifest(
        name="encryption-test",
        version="1.0.0",
        description="secret description",
    )
    envelope = await clean_gift_service.create_gift_from_manifest(
        manifest=manifest,
        code_bytes=code,
        from_instance="A",
        to_instance="B",
        session_key=two_instances_keys["session_key"],
    )

    # 序列化为 JSON
    env_json = json.dumps(envelope)
    # ciphertext 应是 base64 字符串
    ciphertext = envelope["encrypted_payload"]["ciphertext"]

    # 明文中的敏感内容不应直接出现在 envelope JSON 中
    assert "secret-content" not in env_json
    assert "secret description" not in env_json  # description 在加密载荷内

    # skill_name 是明文 hint(用于展示),可以出现
    assert "encryption-test" in env_json

    # 但 ciphertext 解码后也不应直接包含明文(因 AES-GCM)
    cipher_bytes = base64.b64decode(ciphertext)
    assert b"secret-content" not in cipher_bytes
    assert b"secret description" not in cipher_bytes


# ===== 13. create_gift(从已安装技能) =====


async def test_create_gift_from_installed(clean_gift_service, two_instances_keys, tmp_path):
    """create_gift 应能从本地已安装的技能创建 envelope"""
    # 先安装一个技能到 tmp_path
    code = b"def handler():\n    return 'installed'\n"
    manifest = SkillManifest(
        name="installed-gift",
        version="1.0.0",
        code=base64.b64encode(code).decode(),
    )
    packed = SkillPackager.pack(manifest)
    installer = SkillInstaller(skills_dir=tmp_path)
    install_result = await installer.install(packed)
    assert install_result["ok"] is True

    # monkeypatch SkillInstaller 的默认目录,让 create_gift 能找到它
    import server.services.skill_gift as gift_mod

    original_installer_init = gift_mod.SkillInstaller.__init__
    gift_mod.SkillInstaller.__init__ = lambda self, skills_dir=None: original_installer_init(
        self, skills_dir=tmp_path
    )
    try:
        envelope = await clean_gift_service.create_gift(
            skill_name="installed-gift",
            from_instance="A",
            to_instance="B",
            session_key=two_instances_keys["session_key"],
        )
        assert envelope["skill_name"] == "installed-gift"
    finally:
        gift_mod.SkillInstaller.__init__ = original_installer_init


async def test_create_gift_not_installed(clean_gift_service, two_instances_keys):
    """create_gift 对未安装的技能应抛 FileNotFoundError"""
    with pytest.raises(FileNotFoundError):
        await clean_gift_service.create_gift(
            skill_name="nonexistent-skill",
            from_instance="A",
            to_instance="B",
            session_key=two_instances_keys["session_key"],
        )
