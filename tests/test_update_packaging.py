"""P0-W6 自动更新 + 打包 完整性校验测试 (v2.1.0 Phase 0)

验证 P0-W6 的代码结构和功能:
1. updater.rs 文件结构 (check_for_update + install_update)
2. UpdateChecker.tsx 前端组件结构
3. gen_latest_json.py latest.json 生成功能
4. build_sidecar.py sidecar 打包脚本结构
5. tauri.conf.json updater + bundle 配置
6. tauri-release.yml CI workflow 结构
7. lib.rs 集成 (updater plugin + commands)
8. Cargo.toml 依赖 (tauri-plugin-updater)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_TAURI = PROJECT_ROOT / "src-tauri"
FRONTEND_COMPONENTS = PROJECT_ROOT / "frontend" / "src" / "components"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"


# ----------------------------------------------------------------------
# 6.1 updater.rs 文件结构验证
# ----------------------------------------------------------------------

def test_01_updater_rs_exists():
    """updater.rs 文件存在"""
    assert (SRC_TAURI / "src" / "updater.rs").exists(), "src-tauri/src/updater.rs not found"


def test_02_updater_rs_has_update_info_struct():
    """updater.rs 包含 UpdateInfo 结构体"""
    content = (SRC_TAURI / "src" / "updater.rs").read_text(encoding="utf-8")
    assert "pub struct UpdateInfo" in content, "UpdateInfo struct missing"
    assert "pub available: bool" in content, "available field missing"
    assert "pub version: Option<String>" in content, "version field missing"


def test_03_updater_rs_has_check_for_update():
    """updater.rs 包含 check_for_update command"""
    content = (SRC_TAURI / "src" / "updater.rs").read_text(encoding="utf-8")
    assert "#[tauri::command]" in content, "tauri::command attribute missing"
    assert "pub async fn check_for_update" in content, "check_for_update function missing"
    assert "app.updater()" in content, "updater() call missing"
    assert "updater.check().await" in content, "check().await missing"


def test_04_updater_rs_has_install_update():
    """updater.rs 包含 install_update command"""
    content = (SRC_TAURI / "src" / "updater.rs").read_text(encoding="utf-8")
    assert "pub async fn install_update" in content, "install_update function missing"
    assert "download_and_install" in content, "download_and_install missing"


def test_05_updater_rs_emits_events():
    """updater.rs 发送更新事件"""
    content = (SRC_TAURI / "src" / "updater.rs").read_text(encoding="utf-8")
    assert '"update-available"' in content, "update-available event missing"
    assert '"update-progress"' in content, "update-progress event missing"
    assert '"update-installed"' in content, "update-installed event missing"
    assert '"update-error"' in content, "update-error event missing"


def test_06_updater_rs_uses_updater_ext():
    """updater.rs 使用 UpdaterExt trait"""
    content = (SRC_TAURI / "src" / "updater.rs").read_text(encoding="utf-8")
    assert "use tauri_plugin_updater::UpdaterExt" in content, "UpdaterExt import missing"


# ----------------------------------------------------------------------
# 6.2 UpdateChecker.tsx 前端组件
# ----------------------------------------------------------------------

def test_07_update_checker_tsx_exists():
    """UpdateChecker.tsx 文件存在"""
    assert (FRONTEND_COMPONENTS / "UpdateChecker.tsx").exists(), "UpdateChecker.tsx not found"


def test_08_update_checker_has_states():
    """UpdateChecker.tsx 包含状态机定义"""
    content = (FRONTEND_COMPONENTS / "UpdateChecker.tsx").read_text(encoding="utf-8")
    assert '"idle"' in content and '"checking"' in content, "state machine missing"
    assert '"available"' in content, "available state missing"
    assert '"downloading"' in content, "downloading state missing"
    assert '"installed"' in content, "installed state missing"


def test_09_update_checker_listens_events():
    """UpdateChecker.tsx 监听 Tauri 更新事件"""
    content = (FRONTEND_COMPONENTS / "UpdateChecker.tsx").read_text(encoding="utf-8")
    assert "update-progress" in content, "update-progress listener missing"
    assert "update-installed" in content, "update-installed listener missing"
    assert "update-error" in content, "update-error listener missing"


def test_10_update_checker_invokes_commands():
    """UpdateChecker.tsx 调用 Tauri commands"""
    content = (FRONTEND_COMPONENTS / "UpdateChecker.tsx").read_text(encoding="utf-8")
    assert "check_for_update" in content, "check_for_update invoke missing"
    assert "install_update" in content, "install_update invoke missing"


def test_11_settings_imports_update_checker():
    """Settings.tsx 导入 UpdateChecker 组件"""
    content = (FRONTEND_COMPONENTS / "Settings.tsx").read_text(encoding="utf-8")
    assert "UpdateChecker" in content, "UpdateChecker import missing in Settings.tsx"


# ----------------------------------------------------------------------
# 6.3 gen_latest_json.py latest.json 生成功能
# ----------------------------------------------------------------------

def test_12_gen_latest_json_exists():
    """gen_latest_json.py 文件存在"""
    assert (SCRIPTS_DIR / "gen_latest_json.py").exists(), "gen_latest_json.py not found"


def test_13_gen_latest_json_generates_valid_json():
    """gen_latest_json.py 生成有效的 latest.json"""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gen_latest_json.py"),
         "--version", "2.1.1",
         "--notes", "Test release",
         "--pub-date", "2026-07-13T00:00:00Z",
         "--windows-url", "https://example.com/test.msi",
         "--windows-sig", "dGhpcyBpcyBhIHRlc3Qgc2lnbmF0dXJl",
         "--output", str(tempfile.mktemp(suffix=".json"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"gen_latest_json.py failed: {result.stderr}"


def test_14_gen_latest_json_has_correct_fields():
    """gen_latest_json.py 输出包含 Tauri Updater 所需字段"""
    from scripts.gen_latest_json import generate_latest_json
    result = generate_latest_json(
        version="2.1.1",
        notes="Test",
        pub_date="2026-07-13T00:00:00Z",
        platforms={"windows-x86_64": {"signature": "sig", "url": "https://example.com/test.msi"}},
    )
    assert result["version"] == "2.1.1"
    assert result["notes"] == "Test"
    assert result["pub_date"] == "2026-07-13T00:00:00Z"
    assert "windows-x86_64" in result["platforms"]
    assert result["platforms"]["windows-x86_64"]["signature"] == "sig"
    assert result["platforms"]["windows-x86_64"]["url"] == "https://example.com/test.msi"


# ----------------------------------------------------------------------
# 6.4 build_sidecar.py 打包脚本
# ----------------------------------------------------------------------

def test_15_build_sidecar_exists():
    """build_sidecar.py 文件存在"""
    assert (SCRIPTS_DIR / "build_sidecar.py").exists(), "build_sidecar.py not found"


def test_16_build_sidecar_has_pyinstaller_args():
    """build_sidecar.py 包含 PyInstaller 参数"""
    content = (SCRIPTS_DIR / "build_sidecar.py").read_text(encoding="utf-8")
    assert "--onedir" in content, "onedir mode missing"
    assert "--console" in content, "console mode missing (needed for stdout handshake)"
    assert "--name=pangu-nebula-sidecar" in content, "sidecar name missing"
    assert "collect-submodules" in content or "collect_submodules" in content, \
        "collect_submodules missing"
    assert "server" in content, "server module collection missing"


def test_17_build_sidecar_output_to_resources():
    """build_sidecar.py 输出到 src-tauri/resources/pangu-sidecar/"""
    content = (SCRIPTS_DIR / "build_sidecar.py").read_text(encoding="utf-8")
    assert "src-tauri" in content, "src-tauri path missing"
    assert "resources" in content, "resources path missing"
    assert "pangu-sidecar" in content, "pangu-sidecar output dir missing"


def test_18_build_sidecar_sets_nebula_shell():
    """build_sidecar.py 设置 NEBULA_SHELL=tauri 环境变量"""
    content = (SCRIPTS_DIR / "build_sidecar.py").read_text(encoding="utf-8")
    assert "NEBULA_SHELL" in content, "NEBULA_SHELL env var missing"
    assert "tauri" in content, "tauri mode not set"


# ----------------------------------------------------------------------
# 6.5 tauri.conf.json 配置
# ----------------------------------------------------------------------

def test_19_tauri_conf_has_updater_plugin():
    """tauri.conf.json 包含 updater 插件配置"""
    content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    config = json.loads(content)
    assert "plugins" in config, "plugins section missing"
    assert "updater" in config["plugins"], "updater plugin config missing"
    assert config["plugins"]["updater"]["active"] is True, "updater not active"
    assert "endpoints" in config["plugins"]["updater"], "endpoints missing"
    assert "pubkey" in config["plugins"]["updater"], "pubkey missing"


def test_20_tauri_conf_has_resources():
    """tauri.conf.json 包含 sidecar resources 配置"""
    content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    config = json.loads(content)
    assert "bundle" in config, "bundle section missing"
    resources = config["bundle"].get("resources", [])
    assert any("pangu-sidecar" in r for r in resources), \
        "pangu-sidecar resources missing"


def test_21_tauri_conf_has_windows_bundle_config():
    """tauri.conf.json 包含 Windows MSI/NSIS 打包配置"""
    content = (SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8")
    config = json.loads(content)
    windows = config["bundle"].get("windows", {})
    assert "wix" in windows, "WiX config missing"
    assert "zh-CN" in windows["wix"]["language"], "zh-CN language missing"
    assert "nsis" in windows, "NSIS config missing"
    # digestAlgorithm configured per signing environment


# ----------------------------------------------------------------------
# 6.6 tauri-release.yml CI workflow
# ----------------------------------------------------------------------

def test_22_tauri_release_yml_exists():
    """tauri-release.yml 文件存在"""
    assert (WORKFLOWS_DIR / "tauri-release.yml").exists(), "tauri-release.yml not found"


def test_23_tauri_release_has_multi_platform_matrix():
    """tauri-release.yml 包含多平台构建矩阵"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "windows-latest" in content, "Windows platform missing"
    assert "macos-latest" in content, "macOS ARM platform missing"
    assert "ubuntu" in content, "Linux platform missing"
    assert "strategy" in content and "matrix" in content, "matrix strategy missing"


def test_24_tauri_release_has_signing_env():
    """tauri-release.yml 包含 updater 签名环境变量"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "TAURI_SIGNING_KEY" in content, "TAURI_SIGNING_KEY missing"
    assert "TAURI_SIGNING_KEY_PASSWORD" in content, "TAURI_SIGNING_KEY_PASSWORD missing"


def test_25_tauri_release_has_sidecar_build_step():
    """tauri-release.yml 包含 sidecar 构建步骤"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "build_sidecar.py" in content, "build_sidecar.py step missing"
    assert "gen_sidecar_hash.py" in content, "gen_sidecar_hash.py step missing"


def test_26_tauri_release_has_latest_json_generation():
    """tauri-release.yml 包含 latest.json 生成步骤"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "gen_latest_json.py" in content, "gen_latest_json.py missing"
    assert "latest.json" in content, "latest.json reference missing"
    assert "release" in content, "release job missing"


def test_27_tauri_release_triggers_on_v2_tags():
    """tauri-release.yml 在 v2.* tag 时触发 (v2.2.0 起扩展为 v2.* 覆盖所有 v2.x.x)"""
    content = (WORKFLOWS_DIR / "tauri-release.yml").read_text(encoding="utf-8")
    assert "v2.*" in content, "v2.* tag trigger missing"
    assert "tags:" in content, "tags trigger missing"


# ----------------------------------------------------------------------
# 6.7 lib.rs 集成验证
# ----------------------------------------------------------------------

def test_28_lib_rs_has_updater_module():
    """lib.rs 声明 updater 模块"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "mod updater" in content, "updater module declaration missing"


def test_29_lib_rs_registers_updater_plugin():
    """lib.rs 注册 tauri_plugin_updater"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "tauri_plugin_updater" in content, "tauri_plugin_updater plugin missing"


def test_30_lib_rs_invokes_update_commands():
    """lib.rs 注册 check_for_update + install_update commands"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "check_for_update" in content, "check_for_update command not registered"
    assert "install_update" in content, "install_update command not registered"


# ----------------------------------------------------------------------
# 6.8 Cargo.toml 依赖
# ----------------------------------------------------------------------

def test_31_cargo_toml_has_updater_dependency():
    """Cargo.toml 包含 tauri-plugin-updater 依赖"""
    content = (SRC_TAURI / "Cargo.toml").read_text(encoding="utf-8")
    assert "tauri-plugin-updater" in content, "tauri-plugin-updater dependency missing"
    assert '"2"' in content, "version 2 missing for tauri-plugin-updater"
