"""技能包 (.skill) 与终端模式 (Terminal) 测试

覆盖:
1. SkillManifest 创建
2. SkillPackager.pack/unpack 往返
3. SkillPackager.validate 验证有效/无效
4. SkillPackager.calculate_checksum
5. SkillInstaller install/uninstall 往返
6. SkillInstaller list_installed / export
7. TerminalService 可实例化且状态正确
8. TerminalService create_session (mock)
9. TerminalService write/read (mock)
10. TerminalService resize (mock)
11. TerminalService close_session
12. TerminalService 会话隔离(不存在的 session_id 返回错误)
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from server.services.skill_package import (
    SkillManifest,
    SkillPackager,
    SkillInstaller,
)
from server.services.terminal_service import TerminalService


# ===== 1. SkillManifest 创建 =====


def test_skill_manifest_creation():
    """SkillManifest 默认值与自定义字段"""
    m = SkillManifest(name="my-skill")
    assert m.name == "my-skill"
    assert m.version == "1.0.0"
    assert m.description == ""
    assert m.author == ""
    assert m.dependencies == []
    assert m.capabilities == ["text"]
    assert m.config == {}
    assert m.entry_point == "main.handler"
    assert m.code == ""
    assert m.checksum == ""

    # 带完整字段
    m2 = SkillManifest(
        name="vision-skill",
        version="2.3.1",
        description="A vision skill",
        author="tester",
        dependencies=["base@1.0.0", "utils@2.0.0"],
        capabilities=["text", "vision"],
        config={"timeout": 30},
        entry_point="custom.run",
        code=base64.b64encode(b"print('hi')").decode(),
        checksum="abc123",
    )
    assert m2.name == "vision-skill"
    assert m2.version == "2.3.1"
    assert m2.capabilities == ["text", "vision"]
    assert m2.config == {"timeout": 30}
    assert m2.entry_point == "custom.run"


# ===== 2. SkillPackager pack/unpack 往返 =====


def test_packager_pack_unpack_roundtrip():
    """打包后解包应还原为相同的 manifest"""
    original = SkillManifest(
        name="roundtrip-skill",
        version="1.2.0",
        description="roundtrip test",
        author="pytest",
        dependencies=["dep-a@1.0.0"],
        capabilities=["text"],
        config={"key": "value"},
        entry_point="main.handler",
    )
    packed = SkillPackager.pack(original)
    assert isinstance(packed, bytes)

    # JSON 可解析
    payload = json.loads(packed.decode("utf-8"))
    assert payload["name"] == "roundtrip-skill"
    assert payload["version"] == "1.2.0"
    # 打包后应包含 checksum
    assert payload["checksum"]
    assert payload["checksum"] != ""

    # 解包
    manifest, code_bytes = SkillPackager.unpack(packed)
    assert manifest.name == original.name
    assert manifest.version == original.version
    assert manifest.description == original.description
    assert manifest.author == original.author
    assert manifest.dependencies == original.dependencies
    assert manifest.capabilities == original.capabilities
    assert manifest.config == original.config
    assert manifest.entry_point == original.entry_point
    # 无 code 时 code_bytes 应为 None
    assert code_bytes is None
    # checksum 应被还原
    assert manifest.checksum == payload["checksum"]


def test_packager_pack_with_code(tmp_path: Path):
    """打包时通过 code_path 注入代码,解包应能还原"""
    code_file = tmp_path / "main.py"
    code_file.write_text("def handler():\n    return 42\n", encoding="utf-8")

    manifest = SkillManifest(name="code-skill", version="1.0.0")
    packed = SkillPackager.pack(manifest, code_path=code_file)

    m2, code_bytes = SkillPackager.unpack(packed)
    assert code_bytes is not None
    assert code_bytes == code_file.read_bytes()


def test_packager_pack_with_inline_code():
    """打包时直接使用 manifest.code (base64),解包应能还原"""
    code = b"print('hello world')"
    manifest = SkillManifest(
        name="inline-code-skill",
        code=base64.b64encode(code).decode(),
    )
    packed = SkillPackager.pack(manifest)
    m2, code_bytes = SkillPackager.unpack(packed)
    assert code_bytes == code


# ===== 3. SkillPackager.validate =====


def test_packager_validate_valid():
    """有效的 manifest 应通过验证"""
    m = SkillManifest(
        name="valid-skill",
        version="1.0.0",
        dependencies=["other@1.0.0", "no-version"],
        capabilities=["text", "vision"],
    )
    valid, err = SkillPackager.validate(m)
    assert valid is True
    assert err == ""


def test_packager_validate_invalid_name():
    """无效的技能名应拒绝"""
    # 空名
    m = SkillManifest(name="")
    valid, err = SkillPackager.validate(m)
    assert valid is False
    assert "name" in err.lower()

    # 含非法字符
    m2 = SkillManifest(name="bad/name")
    valid2, err2 = SkillPackager.validate(m2)
    assert valid2 is False
    assert "name" in err2.lower()


def test_packager_validate_invalid_version():
    """无效的 version 应拒绝"""
    m = SkillManifest(name="bad-version", version="not-a-version")
    valid, err = SkillPackager.validate(m)
    assert valid is False
    assert "version" in err.lower()


def test_packager_validate_invalid_dependencies():
    """无效的依赖格式应拒绝"""
    m = SkillManifest(
        name="bad-deps",
        version="1.0.0",
        dependencies=["valid@1.0.0", "bad dep with space"],
    )
    valid, err = SkillPackager.validate(m)
    assert valid is False
    assert "depend" in err.lower() or "dep" in err.lower()


def test_packager_validate_empty_capabilities():
    """空 capabilities 应拒绝"""
    m = SkillManifest(name="no-cap", version="1.0.0", capabilities=[])
    valid, err = SkillPackager.validate(m)
    assert valid is False
    assert "capab" in err.lower()


# ===== 4. SkillPackager.calculate_checksum =====


def test_packager_calculate_checksum():
    """SHA256 校验和应稳定且与数据长度相关"""
    data = b"hello pangu nebula"
    checksum = SkillPackager.calculate_checksum(data)
    assert isinstance(checksum, str)
    assert len(checksum) == 64  # SHA256 hex 长度
    # 同样的输入应得到同样的输出
    assert SkillPackager.calculate_checksum(data) == checksum
    # 不同输入应得到不同输出
    assert SkillPackager.calculate_checksum(b"different") != checksum


# ===== 5. SkillInstaller install/uninstall 往返 =====


async def test_installer_install_and_uninstall(tmp_path: Path):
    """安装技能包后,应能列出并卸载"""
    installer = SkillInstaller(skills_dir=tmp_path)
    manifest = SkillManifest(
        name="installable-skill",
        version="0.9.0",
        description="install test",
        author="pytest",
        capabilities=["text"],
    )
    packed = SkillPackager.pack(manifest)

    # 安装
    result = await installer.install(packed)
    assert result["ok"] is True
    assert result["data"]["name"] == "installable-skill"
    assert result["data"]["version"] == "0.9.0"
    assert result["data"]["has_code"] is False
    assert result["error"] is None

    # 文件应存在
    assert (tmp_path / "installable-skill.skill").exists()

    # 列出已安装
    installed = await installer.list_installed()
    assert len(installed) == 1
    assert installed[0]["name"] == "installable-skill"
    assert installed[0]["version"] == "0.9.0"

    # 卸载
    un = await installer.uninstall("installable-skill")
    assert un["ok"] is True
    assert un["data"]["name"] == "installable-skill"
    assert not (tmp_path / "installable-skill.skill").exists()

    # 再次卸载应失败
    un2 = await installer.uninstall("installable-skill")
    assert un2["ok"] is False
    assert "not found" in un2["error"].lower()


async def test_installer_install_with_code(tmp_path: Path):
    """安装包含代码的技能包,应同时写入 .py 文件"""
    installer = SkillInstaller(skills_dir=tmp_path)
    code = b"def handler():\n    return 'ok'\n"
    manifest = SkillManifest(
        name="code-install",
        version="1.0.0",
        code=base64.b64encode(code).decode(),
    )
    packed = SkillPackager.pack(manifest)

    result = await installer.install(packed)
    assert result["ok"] is True
    assert result["data"]["has_code"] is True
    assert (tmp_path / "code-install.skill").exists()
    assert (tmp_path / "code-install.py").exists()
    assert (tmp_path / "code-install.py").read_bytes() == code


async def test_installer_install_invalid_rejected(tmp_path: Path):
    """无效的 manifest 应被拒绝安装"""
    installer = SkillInstaller(skills_dir=tmp_path)
    bad_manifest = SkillManifest(name="", version="1.0.0")
    packed = SkillPackager.pack(bad_manifest)

    result = await installer.install(packed)
    assert result["ok"] is False
    assert "validation" in result["error"].lower() or "name" in result["error"].lower()
    assert not (tmp_path / ".skill").exists()


# ===== 6. SkillInstaller export =====


async def test_installer_export(tmp_path: Path):
    """导出技能包应返回原始 bytes"""
    installer = SkillInstaller(skills_dir=tmp_path)
    manifest = SkillManifest(name="exportable", version="1.0.0")
    packed = SkillPackager.pack(manifest)

    await installer.install(packed)
    exported = await installer.export("exportable")
    assert exported == packed

    # 导出不存在的技能应抛 FileNotFoundError
    with pytest.raises(FileNotFoundError):
        await installer.export("does-not-exist")


# ===== 7. TerminalService 可实例化且状态正确 =====


def test_terminal_service_instantiable():
    """TerminalService 应可实例化,get_status 返回正确字段"""
    svc = TerminalService()
    status = svc.get_status()
    assert "available" in status
    assert "mode" in status
    assert "active_sessions" in status
    assert isinstance(status["available"], bool)
    assert status["mode"] in ("real", "mock")
    assert status["active_sessions"] == 0
    # mode 应与 available 一致
    assert (status["mode"] == "real") == status["available"]


# ===== 8. TerminalService create_session (mock) =====


async def test_terminal_create_session_mock():
    """create_session 在 mock 模式下应返回 mock- 前缀的 session_id"""
    svc = TerminalService()
    # 强制 mock 模式
    svc._available = False

    result = await svc.create_session(shell="powershell", cols=120, rows=40)
    assert result["ok"] is True
    assert result["error"] is None
    data = result["data"]
    assert data["mock"] is True
    assert data["session_id"].startswith("mock-")
    assert data["shell"] == "powershell"
    assert data["cols"] == 120
    assert data["rows"] == 40

    # 状态: 活跃会话数 = 1
    assert svc.get_status()["active_sessions"] == 1


# ===== 9. TerminalService write/read (mock) =====


async def test_terminal_write_read_mock():
    """mock 模式下 write 应返回占位输出,read 应返回 mock 数据"""
    svc = TerminalService()
    svc._available = False

    create = await svc.create_session()
    sid = create["data"]["session_id"]

    # write
    w = await svc.write(sid, "dir")
    assert w["ok"] is True
    assert w["data"]["mock"] is True
    assert "dir" in w["data"]["output"]

    # read
    r = await svc.read(sid)
    assert r["ok"] is True
    assert r["data"]["mock"] is True
    assert r["data"]["data"] == "mock terminal output"

    # 清理
    await svc.close_session(sid)


# ===== 10. TerminalService resize (mock) =====


async def test_terminal_resize_mock():
    """mock 模式下 resize 应更新会话尺寸"""
    svc = TerminalService()
    svc._available = False

    create = await svc.create_session(cols=80, rows=24)
    sid = create["data"]["session_id"]

    r = await svc.resize(sid, 200, 50)
    assert r["ok"] is True
    assert r["data"]["cols"] == 200
    assert r["data"]["rows"] == 50
    assert r["data"]["mock"] is True

    # 清理
    await svc.close_session(sid)


# ===== 11. TerminalService close_session =====


async def test_terminal_close_session():
    """close_session 应从会话表中移除会话"""
    svc = TerminalService()
    svc._available = False

    create = await svc.create_session()
    sid = create["data"]["session_id"]
    assert svc.get_status()["active_sessions"] == 1

    closed = await svc.close_session(sid)
    assert closed["ok"] is True
    assert closed["data"]["closed"] is True
    assert svc.get_status()["active_sessions"] == 0

    # 再次关闭应失败
    again = await svc.close_session(sid)
    assert again["ok"] is False
    assert "not found" in again["error"].lower()


# ===== 12. TerminalService 会话隔离 =====


async def test_terminal_session_isolation():
    """对不存在的 session_id 操作应返回错误"""
    svc = TerminalService()
    svc._available = False

    fake_id = "nonexistent-session"
    # write 到不存在的会话
    w = await svc.write(fake_id, "hello")
    assert w["ok"] is False
    assert "not found" in w["error"].lower()

    # read 不存在的会话
    r = await svc.read(fake_id)
    assert r["ok"] is False
    assert "not found" in r["error"].lower()

    # resize 不存在的会话
    rz = await svc.resize(fake_id, 80, 24)
    assert rz["ok"] is False
    assert "not found" in rz["error"].lower()

    # close 不存在的会话
    cl = await svc.close_session(fake_id)
    assert cl["ok"] is False
    assert "not found" in cl["error"].lower()


# ===== 13. list_sessions 应反映当前所有会话 =====


async def test_terminal_list_sessions():
    """list_sessions 返回所有活跃会话"""
    svc = TerminalService()
    svc._available = False

    # 初始为空
    assert await svc.list_sessions() == []

    c1 = await svc.create_session(shell="powershell")
    c2 = await svc.create_session(shell="cmd")
    sessions = await svc.list_sessions()
    assert len(sessions) == 2
    ids = {s["session_id"] for s in sessions}
    assert c1["data"]["session_id"] in ids
    assert c2["data"]["session_id"] in ids

    # 关闭一个
    await svc.close_session(c1["data"]["session_id"])
    sessions = await svc.list_sessions()
    assert len(sessions) == 1

    # 清理
    await svc.close_session(c2["data"]["session_id"])
