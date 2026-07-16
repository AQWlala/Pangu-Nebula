# tests/test_path_guard.py
"""PathGuard 单元测试与 file_read/file_write 集成测试。

覆盖 v2.2.1 安全修复 F1: 路径白名单 / 黑名单 / 软链接逃逸 / write 系统目录 / 大小写。
"""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.services.path_guard import PathGuard
from server.tools.builtin_tools import FileReadTool, FileWriteTool


# ---------------------------------------------------------------------------
# PathGuard 单元测试
# ---------------------------------------------------------------------------


def test_allows_path_in_whitelist(tmp_path):
    """白名单内路径允许访问。"""
    safe = tmp_path / "safe.txt"
    safe.write_text("ok", encoding="utf-8")
    guard = PathGuard(allowed_paths=[str(tmp_path)])
    ok, reason = guard.validate(str(safe), write=False)
    assert ok, reason
    assert "允许" in reason


def test_denies_path_outside_whitelist(tmp_path):
    """白名单外路径被拒绝。"""
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    guard = PathGuard(allowed_paths=[str(other_dir)])
    ok, reason = guard.validate(str(outside), write=False)
    assert not ok
    assert "白名单" in reason


def test_denies_sensitive_files(tmp_path):
    """敏感文件 (.env / .ssh/id_rsa / credentials / *.pem) 一律拒绝。"""
    guard = PathGuard(
        allowed_paths=[str(tmp_path)],
        denied_paths=PathGuard.default_denied_paths(),
    )

    env = tmp_path / ".env"
    env.write_text("SECRET=1", encoding="utf-8")
    ok, _ = guard.validate(str(env))
    assert not ok, ".env 应被拒绝"

    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    id_rsa = ssh_dir / "id_rsa"
    id_rsa.write_text("private", encoding="utf-8")
    ok, _ = guard.validate(str(id_rsa))
    assert not ok, "id_rsa 应被拒绝"

    cred = tmp_path / "credentials"
    cred.write_text("cred", encoding="utf-8")
    ok, _ = guard.validate(str(cred))
    assert not ok, "credentials 应被拒绝"

    pem = tmp_path / "server.pem"
    pem.write_text("cert", encoding="utf-8")
    ok, _ = guard.validate(str(pem))
    assert not ok, "*.pem 应被拒绝"

    key = tmp_path / "ca.key"
    key.write_text("key", encoding="utf-8")
    ok, _ = guard.validate(str(key))
    assert not ok, "*.key 应被拒绝"


def test_denies_symlink_escape(tmp_path):
    """软链接逃逸: 白名单内软链接指向白名单外目标, 应被拒绝。"""
    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = safe_dir / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前平台不支持创建软链接 (可能需要管理员/开发者模式)")

    guard = PathGuard(allowed_paths=[str(safe_dir)])
    ok, reason = guard.validate(str(link), write=False)
    assert not ok, "软链接逃逸应被 resolve 后的白名单校验拒绝"
    assert "白名单" in reason


def test_write_denies_system_dirs():
    """write 模式额外拒绝系统目录 (etc/usr/windows 等), read 模式不拒绝。"""
    # 白名单设为盘符根, 使路径能通过白名单, 从而隔离测试 write 系统目录逻辑
    root = Path("/").resolve()  # POSIX: / ; Windows: 当前盘符根 D:\
    target = root / "etc" / "somefile"

    guard = PathGuard(allowed_paths=[str(root)])
    ok, reason = guard.validate(str(target), write=True)
    assert not ok, "write 模式应拒绝写入系统目录 etc"
    assert "系统目录" in reason

    # read 模式: 在白名单内且 somefile 不在黑名单, 应允许
    ok2, _ = guard.validate(str(target), write=False)
    assert ok2, "read 模式应允许访问白名单内的非敏感路径"


def test_default_allowed_paths():
    """默认白名单包含当前工作目录。"""
    paths = PathGuard.default_allowed_paths()
    assert str(Path.cwd().resolve()) in paths
    # KB 文档目录也应包含
    assert any(p.endswith("kb") for p in paths)


def test_case_insensitive_denied(tmp_path):
    """黑名单不区分大小写匹配。"""
    guard = PathGuard(allowed_paths=[str(tmp_path)])

    env = tmp_path / ".ENV"
    env.write_text("x", encoding="utf-8")
    ok, _ = guard.validate(str(env))
    assert not ok, ".ENV (大写) 应被拒绝"

    ssh = tmp_path / ".SSH"
    ssh.mkdir()
    key = ssh / "ID_RSA"
    key.write_text("x", encoding="utf-8")
    ok, _ = guard.validate(str(key))
    assert not ok, "ID_RSA (大写) 应被拒绝"

    pem = tmp_path / "CERT.PEM"
    pem.write_text("x", encoding="utf-8")
    ok, _ = guard.validate(str(pem))
    assert not ok, "CERT.PEM (大写扩展名) 应被拒绝"


def test_denies_etc_passwd_pattern(tmp_path):
    """黑名单 /etc/passwd 按路径段精确匹配, 不误伤同名子串。"""
    guard = PathGuard(
        allowed_paths=[str(Path("/").resolve())],
        denied_paths=PathGuard.default_denied_paths(),
    )
    # /etc/passwd 命中
    ok, _ = guard.validate(str(Path("/etc/passwd").resolve()))
    assert not ok, "/etc/passwd 应被拒绝"
    # /etc/passwd_backup 不应命中 (精确段匹配)
    ok2, _ = guard.validate(str(Path("/etc/passwd_backup").resolve()))
    assert ok2, "/etc/passwd_backup 不应被 /etc/passwd 模式误伤"


# ---------------------------------------------------------------------------
# file_read / file_write 工具集成测试
# ---------------------------------------------------------------------------


async def test_file_read_tool_integration(tmp_path):
    """file_read 工具集成: persona 白名单内路径可读, 黑名单与白名单外被拒。"""
    target = tmp_path / "read.txt"
    target.write_text("hello", encoding="utf-8")

    persona = SimpleNamespace(allowed_paths=[str(tmp_path)])
    tool = FileReadTool()

    # 白名单内: 成功读取
    result = await tool.execute(path=str(target), persona=persona)
    assert result.success, result.error
    assert result.output == "hello"

    # 黑名单: 读 .env 被拒
    env = tmp_path / ".env"
    env.write_text("SECRET=1", encoding="utf-8")
    result = await tool.execute(path=str(env), persona=persona)
    assert not result.success
    assert "PathGuard" in result.error

    # 白名单外: 被拒 (PathGuard 在 open 前拦截, 路径无需真实存在)
    outside = tmp_path.parent / "nebula_f1_outside.txt"
    result = await tool.execute(path=str(outside), persona=persona)
    assert not result.success
    assert "PathGuard" in result.error


async def test_file_write_tool_integration(tmp_path):
    """file_write 工具集成: 白名单内可写, 黑名单/系统目录被拒。"""
    persona = SimpleNamespace(allowed_paths=[str(tmp_path)])
    tool = FileWriteTool()

    # 白名单内: 成功写入
    target = tmp_path / "out.txt"
    result = await tool.execute(path=str(target), content="data", persona=persona)
    assert result.success, result.error
    assert target.read_text(encoding="utf-8") == "data"

    # 黑名单: 写 .env 被拒
    env = tmp_path / ".env"
    result = await tool.execute(path=str(env), content="x", persona=persona)
    assert not result.success
    assert "PathGuard" in result.error
    assert not env.exists(), "被拒路径不应被写入"

    # write 系统目录: 被拒 (白名单设为根以隔离测试)
    root_persona = SimpleNamespace(allowed_paths=[str(Path("/").resolve())])
    sys_target = Path("/").resolve() / "etc" / "nebula_f1_test"
    result = await tool.execute(
        path=str(sys_target), content="x", persona=root_persona
    )
    assert not result.success
    assert "PathGuard" in result.error
    assert "系统目录" in result.error


async def test_file_tools_default_whitelist_without_persona(tmp_path, monkeypatch):
    """无 persona 时回退默认白名单, 仍可访问工作目录内文件 (向后兼容)。"""
    # 把 cwd 切到 tmp_path, 使默认白名单覆盖目标文件
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "compat.txt"
    target.write_text("ok", encoding="utf-8")

    read_tool = FileReadTool()
    result = await read_tool.execute(path=str(target))  # 不传 persona
    assert result.success, result.error
    assert result.output == "ok"
