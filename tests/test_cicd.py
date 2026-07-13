"""P0-W7 CI/CD + 三平台构建 完整性校验测试 (v2.1.0 Phase 0)

验证 P0-W7 的代码结构和功能:
1. tauri-release.yml workflow 结构 (prepare → build → publish 三阶段)
2. swatinem/rust-cache 集成
3. security.yml 扩展 (cargo-audit + cargo-deny)
4. sync_version.py 版本号同步功能
5. 版本号一致性验证
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_TAURI = PROJECT_ROOT / "src-tauri"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"


# ----------------------------------------------------------------------
# 7.1 tauri-release.yml 三阶段结构
# ----------------------------------------------------------------------

def test_01_tauri_release_has_prepare_job():
    """tauri-release.yml 包含 prepare job (创建 draft release)"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "prepare:" in content, "prepare job missing"
    assert "draft: true" in content, "draft: true missing in prepare job"


def test_02_tauri_release_has_build_job_with_matrix():
    """tauri-release.yml build job 包含 4 平台矩阵"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "build:" in content, "build job missing"
    assert "needs: prepare" in content, "build job should depend on prepare"
    # 4 平台
    assert "windows-latest" in content, "Windows platform missing"
    assert "aarch64-apple-darwin" in content, "macOS ARM64 target missing"
    assert "x86_64-apple-darwin" in content, "macOS Intel target missing"
    assert "x86_64-unknown-linux-gnu" in content, "Linux target missing"


def test_03_tauri_release_has_publish_job():
    """tauri-release.yml 包含 publish job (draft → published)"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "publish:" in content, "publish job missing"
    assert "needs: [prepare, build]" in content, "publish should depend on prepare+build"
    assert "draft: false" in content, "draft: false missing in publish job"


def test_04_tauri_release_has_prerelease_detection():
    """tauri-release.yml 检测 alpha/beta/rc 预发布"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "alpha" in content, "alpha detection missing"
    assert "beta" in content, "beta detection missing"
    assert "rc" in content, "rc detection missing"


# ----------------------------------------------------------------------
# 7.2 swatinem/rust-cache 集成
# ----------------------------------------------------------------------

def test_05_tauri_release_uses_rust_cache():
    """tauri-release.yml 使用 swatinem/rust-cache"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "swatinem/rust-cache" in content, "swatinem/rust-cache action missing"
    assert "workspaces:" in content, "workspaces config missing"


def test_06_rust_cache_has_platform_key():
    """rust-cache 按平台分隔缓存 (key: matrix.target)"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "key: ${{ matrix.target }}" in content, "platform-specific cache key missing"


# ----------------------------------------------------------------------
# 7.3 security.yml 扩展
# ----------------------------------------------------------------------

def test_07_security_yml_has_cargo_audit():
    """security.yml 包含 cargo-audit job"""
    content = (WORKFLOWS_DIR / "security.yml").read_text(encoding="utf-8")
    assert "cargo-audit:" in content or "cargo audit" in content, "cargo-audit job missing"
    assert "cargo install cargo-audit" in content, "cargo-audit install step missing"
    assert "--deny warnings" in content, "--deny warnings flag missing"


def test_08_security_yml_has_cargo_deny():
    """security.yml 包含 cargo-deny job"""
    content = (WORKFLOWS_DIR / "security.yml").read_text(encoding="utf-8")
    assert "cargo-deny:" in content or "cargo deny" in content, "cargo-deny job missing"
    assert "cargo install cargo-deny" in content, "cargo-deny install step missing"
    assert "licenses" in content, "licenses check missing"
    assert "advisories" in content, "advisories check missing"
    assert "bans" in content, "bans check missing"


def test_09_security_yml_triggers_on_cargo_files():
    """security.yml 在 Cargo.toml/Cargo.lock 变更时触发"""
    content = (WORKFLOWS_DIR / "security.yml").read_text(encoding="utf-8")
    assert "src-tauri/Cargo.toml" in content, "Cargo.toml path trigger missing"
    assert "src-tauri/Cargo.lock" in content, "Cargo.lock path trigger missing"


# ----------------------------------------------------------------------
# 7.5 sync_version.py 版本号同步
# ----------------------------------------------------------------------

def test_10_sync_version_exists():
    """sync_version.py 文件存在"""
    assert (SCRIPTS_DIR / "sync_version.py").exists(), "sync_version.py not found"


def test_11_sync_version_has_tauri_as_source():
    """sync_version.py 使用 tauri.conf.json 作为单一真相源"""
    content = (SCRIPTS_DIR / "sync_version.py").read_text(encoding="utf-8")
    assert "tauri.conf.json" in content, "tauri.conf.json source missing"
    assert "read_tauri_version" in content, "read_tauri_version function missing"


def test_12_sync_version_syncs_4_files():
    """sync_version.py 同步 4 个目标文件"""
    content = (SCRIPTS_DIR / "sync_version.py").read_text(encoding="utf-8")
    assert "Cargo.toml" in content, "Cargo.toml sync missing"
    assert "pyproject.toml" in content, "pyproject.toml sync missing"
    assert "package.json" in content, "package.json sync missing"
    assert "launch.py" in content, "launch.py sync missing"


def test_13_sync_version_has_check_mode():
    """sync_version.py 支持 --check 模式 (CI 用)"""
    content = (SCRIPTS_DIR / "sync_version.py").read_text(encoding="utf-8")
    assert "--check" in content, "--check flag missing"
    assert "check_only" in content, "check_only parameter missing"


def test_14_sync_version_check_mode_works():
    """sync_version.py --check 模式正常工作"""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "sync_version.py"), "--check"],
        capture_output=True, text=True, timeout=30,
    )
    # 应该返回 0 (所有文件已同步)
    assert result.returncode == 0, f"sync_version --check failed: {result.stderr}\n{result.stdout}"


# ----------------------------------------------------------------------
# 版本号一致性验证
# ----------------------------------------------------------------------

def test_15_tauri_conf_version_is_210():
    """tauri.conf.json 版本号为 2.1.0"""
    content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    config = json.loads(content)
    assert config["version"] == "2.1.1", f"tauri.conf.json version: {config['version']}"


def test_16_cargo_toml_version_matches_tauri():
    """Cargo.toml 版本号与 tauri.conf.json 一致"""
    import re
    tauri_content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    tauri_version = json.loads(tauri_content)["version"]

    cargo_content = (SRC_TAURI / "Cargo.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', cargo_content, re.MULTILINE)
    assert match, "version field not found in Cargo.toml"
    assert match.group(1) == tauri_version, \
        f"Cargo.toml version {match.group(1)} ≠ tauri.conf.json {tauri_version}"


def test_17_pyproject_toml_version_matches_tauri():
    """pyproject.toml 版本号与 tauri.conf.json 一致"""
    import re
    tauri_content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    tauri_version = json.loads(tauri_content)["version"]

    pyproject_content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_content, re.MULTILINE)
    assert match, "version field not found in pyproject.toml"
    assert match.group(1) == tauri_version, \
        f"pyproject.toml version {match.group(1)} ≠ tauri.conf.json {tauri_version}"


def test_18_frontend_package_version_matches_tauri():
    """frontend/package.json 版本号与 tauri.conf.json 一致"""
    tauri_content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    tauri_version = json.loads(tauri_content)["version"]

    pkg_content = (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    pkg = json.loads(pkg_content)
    assert pkg["version"] == tauri_version, \
        f"frontend/package.json version {pkg['version']} ≠ tauri.conf.json {tauri_version}"


def test_19_launch_py_version_matches_tauri():
    """launch.py VERSION 变量与 tauri.conf.json 一致"""
    import re
    tauri_content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    tauri_version = json.loads(tauri_content)["version"]

    launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
    match = re.search(r'VERSION\s*=\s*"([^"]+)"', launch_content)
    assert match, "VERSION variable not found in launch.py"
    assert match.group(1) == tauri_version, \
        f"launch.py VERSION {match.group(1)} ≠ tauri.conf.json {tauri_version}"


# ----------------------------------------------------------------------
# 7.4 三平台构建配置验证
# ----------------------------------------------------------------------

def test_20_tauri_release_has_linux_webkitgtk_41():
    """tauri-release.yml Linux 安装 WebKitGTK 4.1 (非 4.0)"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "libwebkit2gtk-4.1" in content, "WebKitGTK 4.1 missing"
    assert "4.1-1" in content or "4.1-dev" in content, "WebKitGTK 4.1 package missing"


def test_21_tauri_release_has_webview2_bootstrapper():
    """tauri.conf.json 配置 WebView2 bootstrapper (Windows)"""
    content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    config = json.loads(content)
    webview = config["bundle"]["windows"].get("webviewInstallMode", {})
    assert webview.get("type") == "downloadBootstrapper", \
        "webviewInstallMode should be downloadBootstrapper"


def test_22_tauri_release_has_sidecar_build_step():
    """tauri-release.yml 包含 sidecar 构建步骤"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "build_sidecar.py" in content, "build_sidecar.py step missing"
    assert "gen_sidecar_hash.py" in content, "gen_sidecar_hash.py step missing"


def test_23_tauri_release_has_signing_env_vars():
    """tauri-release.yml 配置 updater 签名环境变量"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "TAURI_SIGNING_KEY" in content, "TAURI_SIGNING_KEY missing"
    assert "TAURI_SIGNING_KEY_PASSWORD" in content, "TAURI_SIGNING_KEY_PASSWORD missing"


def test_24_tauri_release_has_windows_cert_decoding():
    """tauri-release.yml 包含 Windows 证书解码步骤"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "WINDOWS_CERT_FILE" in content, "WINDOWS_CERT_FILE missing"
    assert "cert.pfx" in content, "cert.pfx decoding missing"
