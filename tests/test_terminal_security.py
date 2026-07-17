"""F2+F3 安全测试 — terminal 路由鉴权 + shell 白名单

覆盖:
1. _validate_shell 白名单校验 (F3)
   - 允许 bash / powershell.exe
   - 拒绝任意可执行文件 (calc.exe / evil.sh)
   - 拒绝路径遍历 (../bin/evil)
   - 通过 shutil.which 解析完整路径后校验 basename
2. terminal 路由鉴权 (F2)
   - 无 Bearer token 请求被拒 (401)
   - 有效 Bearer token 请求通过 (200)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server.services.terminal_service import _validate_shell


# ===== F3: _validate_shell 白名单校验 =====


def test_validate_shell_allows_bash():
    """bash 在 Linux 白名单内应通过"""
    with patch("shutil.which", return_value="/usr/bin/bash"), patch.object(
        sys, "platform", "linux"
    ):
        ok, resolved = _validate_shell("bash")
        assert ok is True
        assert resolved == "/usr/bin/bash"


def test_validate_shell_allows_powershell():
    """powershell.exe 在 Windows 白名单内应通过"""
    fake_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    with patch("shutil.which", return_value=fake_path), patch.object(
        sys, "platform", "win32"
    ):
        ok, resolved = _validate_shell("powershell")
        assert ok is True
        assert resolved == fake_path
        # basename 应为 powershell.exe (v2.2.2: 跨平台提取, Linux 上 os.path.basename 不认 \)
        import os

        assert os.path.basename(resolved.replace("\\", "/")).lower() == "powershell.exe"


def test_validate_shell_denies_arbitrary():
    """calc.exe / evil.sh 不在白名单应拒绝"""
    # calc.exe 存在于 Windows 但不在白名单
    with patch(
        "shutil.which", return_value=r"C:\Windows\System32\calc.exe"
    ), patch.object(sys, "platform", "win32"):
        ok, msg = _validate_shell("calc.exe")
        assert ok is False
        assert "not allowed" in msg.lower()

    # evil.sh 不存在 (shutil.which 返回 None)
    with patch("shutil.which", return_value=None):
        ok, msg = _validate_shell("evil.sh")
        assert ok is False
        assert "not found" in msg.lower()


def test_validate_shell_denies_path_traversal():
    """../bin/evil 解析后 basename 不在白名单应拒绝"""
    with patch("shutil.which", return_value="/bin/evil"), patch.object(
        sys, "platform", "linux"
    ):
        ok, msg = _validate_shell("../bin/evil")
        assert ok is False
        assert "not allowed" in msg.lower()
        # 错误信息应包含解析后的路径
        assert "/bin/evil" in msg


def test_validate_shell_resolves_which():
    """用 shutil.which 解析完整路径后校验 basename

    输入 'powershell' (无 .exe) 应解析为 powershell.exe 并通过白名单。
    输入 'cmd' (无 .exe) 应解析为 cmd.exe 并通过白名单。
    """
    # powershell -> powershell.exe
    ps_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    with patch("shutil.which", return_value=ps_path), patch.object(
        sys, "platform", "win32"
    ):
        ok, resolved = _validate_shell("powershell")
        assert ok is True
        # resolved 应为完整路径(而非原始输入 'powershell')
        assert resolved == ps_path
        assert "powershell.exe" in resolved.lower()

    # cmd -> cmd.exe
    cmd_path = r"C:\Windows\System32\cmd.exe"
    with patch("shutil.which", return_value=cmd_path), patch.object(
        sys, "platform", "win32"
    ):
        ok, resolved = _validate_shell("cmd")
        assert ok is True
        assert resolved == cmd_path


# ===== F2: terminal 路由鉴权 =====


def test_terminal_route_requires_token(test_client: TestClient, monkeypatch):
    """无 Bearer token 请求应被拒 (401)"""
    from server.main import settings

    # 设置 sidecar_token,启用鉴权
    monkeypatch.setattr(settings, "sidecar_token", "test-secret-token-123", raising=False)

    # 无 Authorization 头 -> 401
    response = test_client.get("/terminal/status")
    assert response.status_code == 401

    # 错误的 token -> 401
    response = test_client.get(
        "/terminal/status",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401

    # 畸形 Authorization 头 -> 401
    response = test_client.get(
        "/terminal/status",
        headers={"Authorization": "NotBearer test-secret-token-123"},
    )
    assert response.status_code == 401


def test_terminal_route_accepts_valid_token(test_client: TestClient, monkeypatch):
    """有效 Bearer token 请求应通过 (200)"""
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "test-secret-token-123", raising=False)

    # 正确 token -> 200
    response = test_client.get(
        "/terminal/status",
        headers={"Authorization": "Bearer test-secret-token-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "available" in data["data"]
    assert "mode" in data["data"]


# ===== 额外: verify_terminal_access 直接单元测试 (纵深防御验证) =====


def test_verify_terminal_access_allows_when_no_token(monkeypatch):
    """pywebview 模式 (sidecar_token 为空) 应允许访问"""
    from server.api.terminal import verify_terminal_access
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "", raising=False)
    request = MagicMock()
    request.headers = {}
    # 不应抛出异常
    verify_terminal_access(request)


def test_verify_terminal_access_rejects_missing_bearer(monkeypatch):
    """tauri 模式下无 Bearer token 应抛出 401"""
    from server.api.terminal import verify_terminal_access
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "secret", raising=False)
    request = MagicMock()
    request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        verify_terminal_access(request)
    assert exc_info.value.status_code == 401


def test_verify_terminal_access_accepts_valid_bearer(monkeypatch):
    """tauri 模式下有效 Bearer token 应通过"""
    from server.api.terminal import verify_terminal_access
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "secret-token", raising=False)
    request = MagicMock()
    request.headers = {"Authorization": "Bearer secret-token"}
    # 不应抛出异常
    verify_terminal_access(request)
