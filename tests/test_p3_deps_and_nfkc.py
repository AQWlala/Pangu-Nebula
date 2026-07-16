# tests/test_p3_deps_and_nfkc.py
"""v2.2.1 P3 修复测试 — 路由级鉴权依赖 (deps.py) + Unicode NFKC 规范化

覆盖:
1. P3-1: server/api/deps.py 的 require_token 依赖
   - pywebview 模式 (sidecar_token 为空): 放行
   - tauri 模式 (sidecar_token 已设置): 校验 Bearer token
   - 缺失/畸形 Authorization 头: 401
   - 错误 token: 401
2. P3-2: command_guard / path_guard 的 NFKC 规范化
   - 全角字符 (ｒｍ / .ｅｎｖ) 规范化后被检测
   - 零宽字符移除后被检测
   - 正常命令/路径不受影响 (无回归)
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from server.api.deps import get_sidecar_token, require_token
from server.services.command_guard import check_command
from server.services.path_guard import PathGuard


# ---------------------------------------------------------------------------
# P3-1: require_token 鉴权依赖
# ---------------------------------------------------------------------------


def _make_request(headers: dict | None = None) -> MagicMock:
    """构造一个最小可用的 request mock, headers 行为与真实 Request 一致"""
    req = MagicMock()
    req.headers = headers or {}
    return req


def test_require_token_pywebview_no_token(monkeypatch):
    """pywebview 模式 (sidecar_token 为空): 任意请求放行, 不抛异常"""
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "", raising=False)

    # 无 Authorization 头: 放行
    require_token(_make_request(headers={}))
    # 有 Authorization 头但无 token 配置: 也放行 (pywebview 不校验)
    require_token(_make_request(headers={"Authorization": "Bearer anything"}))


def test_require_token_tauri_valid(monkeypatch):
    """tauri 模式: 携带正确 Bearer token 的请求放行"""
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "secret-token-abc", raising=False)

    # 不抛异常即通过
    require_token(_make_request(headers={"Authorization": "Bearer secret-token-abc"}))


def test_require_token_tauri_invalid(monkeypatch):
    """tauri 模式: 错误的 Bearer token 拒绝 (401)"""
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "secret-token-abc", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        require_token(_make_request(headers={"Authorization": "Bearer wrong-token"}))
    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail


def test_require_token_tauri_missing(monkeypatch):
    """tauri 模式: 缺失 Authorization 头拒绝 (401)"""
    from server.main import settings

    monkeypatch.setattr(settings, "sidecar_token", "secret-token-abc", raising=False)

    # 完全缺失 Authorization 头
    with pytest.raises(HTTPException) as exc_info:
        require_token(_make_request(headers={}))
    assert exc_info.value.status_code == 401
    assert "Authorization" in exc_info.value.detail

    # 畸形 Authorization (非 Bearer 前缀)
    with pytest.raises(HTTPException) as exc_info:
        require_token(
            _make_request(headers={"Authorization": "Basic secret-token-abc"})
        )
    assert exc_info.value.status_code == 401


def test_get_sidecar_token_returns_empty_when_settings_unavailable(monkeypatch):
    """get_sidecar_token 在 settings 不可用时返回空字符串 (pywebview 行为)"""
    # 模拟 import 失败: 让 ..main 模块的 settings 属性访问抛异常
    import server.main as main_mod

    # 暂时移除 settings 属性, 触发 getattr 默认路径
    monkeypatch.delattr(main_mod, "settings", raising=False)
    token = get_sidecar_token()
    # getattr(settings, "sidecar_token", "") 会抛 AttributeError 因 settings 不存在,
    # 外层 except 捕获后返回 ""
    assert token == ""


# ---------------------------------------------------------------------------
# P3-2: command_guard NFKC 规范化
# ---------------------------------------------------------------------------


def test_command_guard_nfkc_fullwidth():
    r"""全角字符 (ｒｍ) 经 NFKC 规范化后应被黑名单检测

    攻击场景: 用户输入 "ｒｍ -rf /", 字节级匹配会绕过 "\brm\s+..." 模式。
    NFKC 把 ｒｍ (U+FF52 U+FF4D) 规范化为 rm, 命中黑名单。
    """
    # 全角 ｒｍ + 半角空格 + -rf /
    fullwidth_cmd = "ｒｍ -rf /"
    ok, reason = check_command(fullwidth_cmd)
    assert not ok, f"全角 ｒｍ 应被 NFKC 规范化后拦截, got ok={ok}"
    assert "rm -rf" in reason or "递归删除根目录" in reason


def test_command_guard_nfkc_zero_width():
    """零宽字符 (U+200B) 移除后应被黑名单检测

    攻击场景: "r\\u200bm -rf /" 字符串看起来像 "rm -rf /", 但字节级匹配失败。
    显式移除零宽字符后, 命中黑名单。
    """
    # 在 r 和 m 之间插入零宽空格 U+200B
    zero_width_cmd = "r\u200bm -rf /"
    ok, reason = check_command(zero_width_cmd)
    assert not ok, f"零宽字符混淆的 rm 应被拦截, got ok={ok}"
    assert "rm -rf" in reason or "递归删除根目录" in reason

    # 其他零宽字符变体也应被拦截
    for zw in ("\u200c", "\u200d", "\ufeff"):
        cmd = f"r{zw}m -rf /"
        ok, reason = check_command(cmd)
        assert not ok, f"零宽字符 U+{ord(zw):04X} 混淆应被拦截"


def test_command_guard_nfkc_normal_pass():
    """正常命令不受 NFKC 规范化影响 (无回归)

    - 简单命令 (ls / echo) 应通过
    - 含中文/全角但非危险关键字的命令也应通过
    """
    # 简单 shell 命令
    ok, reason = check_command("ls -la")
    assert ok, f"ls -la 应通过, reason={reason}"
    assert reason == ""

    ok, reason = check_command("echo hello")
    assert ok, f"echo hello 应通过, reason={reason}"

    # 含中文字符的非危险命令 (NFKC 不会改变中文)
    ok, reason = check_command("echo 你好世界")
    assert ok, f"含中文的 echo 应通过, reason={reason}"

    # 含全角字符但非危险关键字 (ｅｃｈｏ 规范化为 echo)
    ok, reason = check_command("ｅｃｈｏ hello")
    assert ok, f"全角 ｅｃｈｏ 规范化为 echo 后应通过 (非危险), reason={reason}"

    # 空命令仍被拒绝 (回归)
    ok, reason = check_command("")
    assert not ok
    assert "空命令" in reason


def test_command_guard_nfkc_fullwidth_format_disk():
    """全角 format 命令也应被规范化后拦截 (额外回归)"""
    # 全角 ｆｏｒｍａｔ + 半角空格 + c:
    fullwidth_format = "ｆｏｒｍａｔ c:"
    ok, reason = check_command(fullwidth_format)
    assert not ok, f"全角 ｆｏｒｍａｔ 应被拦截, got ok={ok}"
    assert "format" in reason.lower() or "格式化" in reason


# ---------------------------------------------------------------------------
# P3-2: path_guard NFKC 规范化
# ---------------------------------------------------------------------------


def test_path_guard_nfkc_fullwidth(tmp_path):
    """全角路径字符 .ｅｎｖ 规范化为 .env 后被黑名单拦截

    攻击场景: 攻击者用全角文件名 ".ｅｎｖ" 试图绕过 .env 黑名单。
    NFKC 把 ｅｎｖ (U+FF45 U+FF4E U+FF56) 规范化为 env, 命中黑名单。
    """
    guard = PathGuard(allowed_paths=[str(tmp_path)])
    # 在白名单目录下用全角文件名 (path_guard 不要求文件存在)
    fullwidth_env = str(tmp_path / ".ｅｎｖ")
    ok, reason = guard.validate(fullwidth_env)
    assert not ok, f"全角 .ｅｎｖ 应被 NFKC 规范化为 .env 后被黑名单拦截, got ok={ok}"
    assert "黑名单" in reason or ".env" in reason


def test_path_guard_nfkc_fullwidth_id_rsa(tmp_path):
    """全角路径段 ID_ＲＳＡ 规范化为 ID_RSA 后命中黑名单 (大小写不敏感)"""
    guard = PathGuard(allowed_paths=[str(tmp_path)])
    fullwidth_id_rsa = str(tmp_path / "ID_ＲＳＡ")
    ok, reason = guard.validate(fullwidth_id_rsa)
    assert not ok, f"全角 ID_ＲＳＡ 应被规范化后拦截, got ok={ok}"
    assert "黑名单" in reason or "id_rsa" in reason.lower()


def test_path_guard_nfkc_normal_path_passes(tmp_path):
    """正常路径不受 NFKC 规范化影响 (无回归)"""
    guard = PathGuard(allowed_paths=[str(tmp_path)])
    # ASCII 路径
    safe_file = tmp_path / "read.txt"
    safe_file.write_text("ok", encoding="utf-8")
    ok, reason = guard.validate(str(safe_file))
    assert ok, f"ASCII 路径应通过, reason={reason}"
    assert "允许" in reason

    # 含中文的合法路径 (NFKC 不改变中文)
    cn_file = tmp_path / "笔记.txt"
    cn_file.write_text("note", encoding="utf-8")
    ok, reason = guard.validate(str(cn_file))
    assert ok, f"含中文的合法路径应通过, reason={reason}"


def test_path_guard_nfkc_fullwidth_pem_extension(tmp_path):
    """全角扩展名 .ＰＥＭ 规范化为 .PEM 后命中 *.pem 黑名单"""
    guard = PathGuard(allowed_paths=[str(tmp_path)])
    fullwidth_pem = str(tmp_path / "cert.ＰＥＭ")
    ok, reason = guard.validate(fullwidth_pem)
    assert not ok, f"全角 .ＰＥＭ 应被规范化后拦截, got ok={ok}"
    assert "黑名单" in reason or "pem" in reason.lower()
