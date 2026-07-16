"""P0-W4 窗口/托盘 + 核心页面验证测试 (v2.1.0 Phase 0)

验证 P0-W4 的代码结构和 sidecar 行为:
1. tauri.conf.json 窗口配置 (minWidth/minHeight/visible)
2. tray.rs 文件结构 (setup_tray 函数)
3. lib.rs 集成 (single-instance + CloseRequested 拦截 + sidecar 就绪后 show)
4. 前端 3 核心页面组件存在
5. sidecar 在窗口隐藏场景下正常启动 (visible:false 模拟)

由于 Tauri 窗口/托盘需要 GUI 环境, 本测试验证代码结构 + sidecar 行为。
"""

import pytest

# uvicorn 是可选依赖（sidecar 启动需要），未安装时跳过
pytest.importorskip("uvicorn")

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_TAURI = PROJECT_ROOT / "src-tauri"
FRONTEND_COMPONENTS = PROJECT_ROOT / "frontend" / "src" / "components"


# ----------------------------------------------------------------------
# 4.1 窗口配置验证 (tauri.conf.json)
# ----------------------------------------------------------------------

def test_01_window_config_min_size():
    """tauri.conf.json 窗口 minWidth/minHeight = 800x600"""
    conf = json.loads((SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    win = conf["app"]["windows"][0]
    assert win["minWidth"] == 800, f"Expected minWidth=800, got {win['minWidth']}"
    assert win["minHeight"] == 600, f"Expected minHeight=600, got {win['minHeight']}"


def test_02_window_config_visible():
    """tauri.conf.json 窗口 visible 配置

    v2.1.7: 借鉴 nomifun 设计,窗口默认可见 (visible:true 或缺省),
    避免 sidecar 启动竞态 (窗口隐藏→sidecar 就绪→显示窗口 的顺序依赖)。
    窗口立即可见,sidecar 在后台异步启动,前端通过 waitForSidecar 门控。
    """
    conf = json.loads((SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    win = conf["app"]["windows"][0]
    # v2.1.7+: visible 可为 true 或缺省 (缺省=true),不再要求 false
    assert win.get("visible", True) is not False, "Window should be visible on startup (v2.1.7+)"


def test_03_window_config_center_and_title():
    """tauri.conf.json 窗口 center=true + title="Pangu Nebula" """
    conf = json.loads((SRC_TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    win = conf["app"]["windows"][0]
    assert win["center"] is True
    assert win["title"] == "Pangu Nebula"


# ----------------------------------------------------------------------
# 4.2 托盘文件结构验证
# ----------------------------------------------------------------------

def test_04_tray_rs_exists():
    """tray.rs 文件存在"""
    assert (SRC_TAURI / "src" / "tray.rs").exists(), "src-tauri/src/tray.rs not found"


def test_05_tray_rs_has_setup_tray():
    """tray.rs 包含 setup_tray 函数 + 菜单项 + 事件处理"""
    content = (SRC_TAURI / "src" / "tray.rs").read_text(encoding="utf-8")
    assert "pub fn setup_tray" in content, "setup_tray function missing"
    assert "TrayIconBuilder" in content, "TrayIconBuilder missing"
    assert "MenuItem" in content, "MenuItem missing"
    assert "MENU_SHOW" in content or "显示主窗口" in content, "Show menu item missing"
    assert "MENU_QUIT" in content or "退出" in content, "Quit menu item missing"
    assert "on_tray_icon_event" in content, "Tray icon event handler missing"
    assert "on_menu_event" in content, "Menu event handler missing"


# ----------------------------------------------------------------------
# 4.3 lib.rs 集成验证
# ----------------------------------------------------------------------

def test_06_lib_rs_single_instance_plugin():
    """lib.rs 注册 tauri-plugin-single-instance"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "tauri_plugin_single_instance" in content, "single-instance plugin not registered"
    assert "get_webview_window" in content, "single-instance callback missing get_webview_window"


def test_07_lib_rs_close_requested_intercept():
    """lib.rs 拦截 CloseRequested 事件 (最小化到托盘)"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "CloseRequested" in content, "CloseRequested event not handled"
    assert "prevent_close" in content, "prevent_close missing (should hide instead of close)"


def test_08_lib_rs_show_window_on_sidecar_ready():
    """lib.rs sidecar 就绪后显示窗口"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "window.show()" in content or "window.show()" in content, "window.show() missing"
    assert "get_webview_window(\"main\")" in content, "get_webview_window('main') missing"


def test_09_cargo_toml_single_instance_dep():
    """Cargo.toml 包含 tauri-plugin-single-instance 依赖"""
    content = (SRC_TAURI / "Cargo.toml").read_text(encoding="utf-8")
    assert "tauri-plugin-single-instance" in content, "single-instance dependency missing"


# ----------------------------------------------------------------------
# 4.4 核心页面组件验证
# ----------------------------------------------------------------------

def test_10_dashboard_component_exists():
    """Dashboard 组件存在"""
    assert (FRONTEND_COMPONENTS / "Dashboard.tsx").exists(), "Dashboard.tsx not found"


def test_11_memory_graph_component_exists():
    """MemoryGraph 组件存在"""
    assert (FRONTEND_COMPONENTS / "MemoryGraph.tsx").exists(), "MemoryGraph.tsx not found"


def test_12_skill_marketplace_component_exists():
    """SkillMarketplace 组件存在"""
    assert (FRONTEND_COMPONENTS / "SkillMarketplace.tsx").exists(), "SkillMarketplace.tsx not found"


# ----------------------------------------------------------------------
# 4.5 sidecar 行为验证 (窗口隐藏场景)
# ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def sidecar():
    """启动 sidecar (模拟窗口隐藏场景: NEBULA_SHELL=tauri)"""
    env = os.environ.copy()
    env["NEBULA_SHELL"] = "tauri"

    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "launch.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    port = None
    token = None
    ready = False
    start = time.time()

    for line in iter(proc.stdout.readline, b""):
        s = line.decode("utf-8", errors="replace").strip()
        if s.startswith("PORT="):
            port = int(s[5:])
        elif s.startswith("TOKEN="):
            token = s[6:]
        elif s == "READY":
            ready = True
            break
        if time.time() - start > 30:
            proc.kill()
            pytest.fail("Sidecar handshake timeout")

    assert ready and port and token
    yield {"port": port, "token": token, "process": proc}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_13_sidecar_starts_in_window_hidden_mode(sidecar):
    """sidecar 在窗口隐藏场景下正常启动 (visible:false 模拟)

    Tauri 启动时窗口隐藏, sidecar 在后台 spawn。
    sidecar 就绪后 Tauri 才显示窗口。
    """
    assert sidecar["port"] > 0
    assert len(sidecar["token"]) == 64


def test_14_sidecar_health_ready_for_window_show(sidecar):
    """/health/ready 就绪 (窗口显示前置条件)

    lib.rs 中 sidecar 就绪后调用 window.show()。
    本测试验证 /health/ready 在窗口显示前已就绪。
    """
    url = f"http://127.0.0.1:{sidecar['port']}/health/ready"
    start = time.time()
    while time.time() - start < 15:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.2)
    pytest.fail("/health/ready not ready within 15s")


def test_15_sidecar_shutdown_on_window_destroy(sidecar):
    """POST /shutdown 优雅关闭 (窗口销毁时触发)

    lib.rs 中 WindowEvent::Destroyed 调用 shutdown_sidecar()。
    本测试验证 /shutdown 端点可正常关闭 sidecar。
    """
    url = f"http://127.0.0.1:{sidecar['port']}/shutdown"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {sidecar['token']}")
    with urllib.request.urlopen(req, timeout=2) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    assert data["ok"] is True
    assert data["data"]["shutting_down"] is True

    # 等待进程退出
    try:
        sidecar["process"].wait(timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail("Sidecar did not exit within 5s after POST /shutdown")
