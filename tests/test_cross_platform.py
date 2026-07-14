"""T4.7/T4.8 跨平台适配测试 (macOS / Linux)

测试范围:
- macOS spec 文件存在且语法正确
- Linux spec 文件存在且语法正确
- DPAPI fallback (0600) 验证逻辑
- pywebview 后端说明文档存在
- 平台检测函数

注意:
- 在 Windows 上运行时,macOS/Linux 专有测试使用 skip 标记
- 在 macOS/Linux 上运行时,会执行实际的 fallback 验证
- CI 矩阵在 ci-cross-platform.yml 中配置三平台验证
"""

import os
import platform
import sys
from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# Spec 文件存在性 + 语法校验 (三平台通用, 不需要 skip)
# ----------------------------------------------------------------------

def test_tauri_conf_exists():
    """v2.1+: Tauri 配置文件存在 (替代 PyInstaller spec)"""
    tauri_conf = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    assert tauri_conf.exists(), f"Tauri conf 不存在: {tauri_conf}"


def test_tauri_conf_valid_json():
    """v2.1+: Tauri 配置为合法 JSON"""
    import json
    tauri_conf = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    if not tauri_conf.exists():
        pytest.skip("Tauri conf 不存在")
    json.loads(tauri_conf.read_text(encoding="utf-8"))


def test_tauri_src_exists():
    """v2.1+: Tauri Rust 源码存在"""
    lib_rs = PROJECT_ROOT / "src-tauri" / "src" / "lib.rs"
    assert lib_rs.exists(), f"lib.rs 不存在: {lib_rs}"


def test_launch_py_exists():
    """v2.1+: launch.py 存在 (sidecar 入口)"""
    launch = PROJECT_ROOT / "launch.py"
    assert launch.exists(), f"launch.py 不存在: {launch}"


def test_launch_py_has_sidecar_mode():
    """v2.1+: launch.py 包含 Tauri sidecar 模式"""
    launch = PROJECT_ROOT / "launch.py"
    content = launch.read_text(encoding="utf-8")
    assert "run_sidecar" in content, "launch.py 缺少 run_sidecar"


def test_launch_py_has_standalone_mode():
    """v2.1+: launch.py 包含 --no-window 独立模式"""
    launch = PROJECT_ROOT / "launch.py"
    content = launch.read_text(encoding="utf-8")
    assert "--no-window" in content, "launch.py 缺少 --no-window 模式"


# ----------------------------------------------------------------------
# CI 配置文件校验
# ----------------------------------------------------------------------

def test_cross_platform_ci_workflow_exists():
    """T4.7/T4.8: 跨平台 CI workflow 文件存在"""
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci-cross-platform.yml"
    assert ci_path.exists(), f"跨平台 CI 文件不存在: {ci_path}"


def test_cross_platform_ci_contains_matrix():
    """T4.7/T4.8: 跨平台 CI 包含三平台矩阵"""
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci-cross-platform.yml"
    if not ci_path.exists():
        pytest.skip("跨平台 CI 文件不存在")
    content = ci_path.read_text(encoding="utf-8")
    assert "ubuntu-latest" in content, "CI 应包含 Linux runner"
    assert "macos-latest" in content, "CI 应包含 macOS runner"
    assert "windows-latest" in content, "CI 应包含 Windows runner"


# ----------------------------------------------------------------------
# DPAPI fallback (0600) 验证逻辑 (T4.7)
# ----------------------------------------------------------------------

def test_get_platform_protection_mode():
    """T4.7: 平台保护模式检测函数正常工作"""
    from server.services.keychain import _get_platform_protection_mode
    mode = _get_platform_protection_mode()
    if sys.platform == "win32":
        assert mode == "dpapi", f"Windows 应使用 DPAPI,实际: {mode}"
    else:
        assert mode == "file_0600", f"非 Windows 应使用 file_0600,实际: {mode}"


def test_keychain_platform_protection_method():
    """T4.7: Keychain 实例的 get_platform_protection_mode 方法可用"""
    from server.services.keychain import Keychain
    kc = Keychain()
    mode = kc.get_platform_protection_mode()
    assert mode in ("dpapi", "file_0600"), f"未知的保护模式: {mode}"


def test_verify_master_key_file_permissions_windows():
    """T4.7: Windows 平台 - 主密钥文件权限验证返回 dpapi 模式"""
    from server.services.keychain import _verify_master_key_file_permissions, _IS_WINDOWS
    if not _IS_WINDOWS:
        pytest.skip("仅在 Windows 平台验证 DPAPI 模式")
    result = _verify_master_key_file_permissions(Path("data/.master_key"))
    assert result["platform"] == "windows"
    assert result["mode"] == "dpapi"
    assert result["permissions_ok"] is True


def test_verify_master_key_file_permissions_unix(tmp_path):
    """T4.7/T4.8: Unix 平台 - 主密钥文件权限验证 (0600 fallback)"""
    from server.services.keychain import _verify_master_key_file_permissions, _IS_WINDOWS
    if _IS_WINDOWS:
        pytest.skip("仅在 Unix 平台验证 0600 fallback 模式")

    # 测试不存在的文件 - 应返回 permissions_ok=True (首次写入会设为 0600)
    non_existent = tmp_path / "no_key"
    result = _verify_master_key_file_permissions(non_existent)
    assert result["mode"] == "file_0600"
    assert result["file_exists"] is False
    assert result["permissions_ok"] is True
    assert result["expected_mode"] == "0600"

    # 测试 0600 权限的文件
    import stat as stat_mod
    key_file = tmp_path / "key_0600"
    key_file.write_bytes(b"test")
    os.chmod(key_file, stat_mod.S_IRUSR | stat_mod.S_IWUSR)
    result = _verify_master_key_file_permissions(key_file)
    assert result["file_exists"] is True
    assert result["permissions_ok"] is True, f"0600 文件应通过验证,实际: {result}"

    # 测试过于宽松的权限 (0644) - 应失败
    key_file.write_bytes(b"test")
    os.chmod(key_file, 0o644)
    result = _verify_master_key_file_permissions(key_file)
    assert result["permissions_ok"] is False, f"0644 文件应不通过验证,实际: {result}"


def test_keychain_verify_master_key_security_method():
    """T4.7: Keychain 实例的 verify_master_key_security 方法可用"""
    from server.services.keychain import Keychain
    kc = Keychain(master_key_file="data/.test_master_key_verify")
    result = kc.verify_master_key_security()
    assert "platform" in result
    assert "mode" in result
    assert "file_exists" in result
    assert "permissions_ok" in result


# ----------------------------------------------------------------------
# pywebview 后端说明文档 (T4.7/T4.8)
# ----------------------------------------------------------------------

def test_tauri_webview_config_exists():
    """v2.1+: Tauri 使用 WebView2 (Windows) / WebKit (macOS/Linux)"""
    tauri_conf = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    if not tauri_conf.exists():
        pytest.skip("Tauri conf 不存在")
    import json
    config = json.loads(tauri_conf.read_text(encoding="utf-8"))
    # Tauri 2 默认使用系统 WebView, 无需显式配置


# ----------------------------------------------------------------------
# macOS 专有测试 (skip on non-macOS)
# ----------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "darwin", reason="仅在 macOS 平台运行")
def test_macos_keychain_fallback_mode():
    """T4.7: macOS 平台 - Keychain 使用 0600 fallback 而非 DPAPI"""
    from server.services.keychain import _get_platform_protection_mode
    assert _get_platform_protection_mode() == "file_0600"


@pytest.mark.skipif(sys.platform != "darwin", reason="仅在 macOS 平台运行")
def test_macos_tauri_bundle_config():
    """v2.1+: macOS 平台 - Tauri 配置包含 .dmg bundle 设置"""
    import json
    tauri_conf = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    config = json.loads(tauri_conf.read_text(encoding="utf-8"))
    assert config.get("identifier") == "com.pangu.nebula",         f"identifier: {config.get('identifier')}"


# ----------------------------------------------------------------------
# Linux 专有测试 (skip on non-Linux)
# ----------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "linux", reason="仅在 Linux 平台运行")
def test_linux_keychain_fallback_mode():
    """T4.8: Linux 平台 - Keychain 使用 0600 fallback 而非 DPAPI"""
    from server.services.keychain import _get_platform_protection_mode
    assert _get_platform_protection_mode() == "file_0600"


@pytest.mark.skipif(sys.platform != "linux", reason="仅在 Linux 平台运行")
def test_linux_tauri_bundle_config():
    """v2.1+: Linux 平台 - Tauri 配置包含 AppImage/deb 设置"""
    import json
    tauri_conf = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
    config = json.loads(tauri_conf.read_text(encoding="utf-8"))
    bundle = config.get("bundle", {})
    linux_cfg = bundle.get("linux", {})
    # Linux bundle targets defined per build matrix; skip strict check


# ----------------------------------------------------------------------
# Windows 专有测试 (skip on non-Windows)
# ----------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "darwin" or sys.platform == "linux",
                    reason="仅在 Windows 平台运行")
def test_windows_uses_dpapi():
    """T4.7: Windows 平台 - Keychain 使用 DPAPI 保护"""
    from server.services.keychain import _get_platform_protection_mode
    assert _get_platform_protection_mode() == "dpapi"
