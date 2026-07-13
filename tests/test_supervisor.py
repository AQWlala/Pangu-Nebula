"""P0-W5 Sidecar Supervisor 完整性校验测试 (v2.1.0 Phase 0)

验证 P0-W5 的代码结构和功能:
1. supervisor.rs 文件结构 (崩溃检测 + 指数退避重启 + 优雅关闭)
2. integrity.rs 文件结构 (SHA-256 完整性校验)
3. gen_sidecar_hash.py 哈希清单生成功能
4. lib.rs 集成 (supervisor + integrity + graceful_shutdown)
5. DegradedUI.tsx 降级 UI 组件
6. Cargo.toml 依赖 (sha2)
7. sidecar 优雅关闭端点 (/shutdown)

由于 Tauri supervisor 需要 GUI 环境, 本测试验证代码结构 + Python 脚本功能 + sidecar 行为。
"""

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
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


# ----------------------------------------------------------------------
# 5.1 supervisor.rs 文件结构验证
# ----------------------------------------------------------------------

def test_01_supervisor_rs_exists():
    """supervisor.rs 文件存在"""
    assert (SRC_TAURI / "src" / "supervisor.rs").exists(), "src-tauri/src/supervisor.rs not found"


def test_02_supervisor_rs_has_supervisor_state():
    """supervisor.rs 包含 SupervisorState 结构体 (retry_count + shutting_down)"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "pub struct SupervisorState" in content, "SupervisorState struct missing"
    assert "retry_count" in content, "retry_count field missing"
    assert "shutting_down" in content, "shutting_down field missing"
    assert "impl Default for SupervisorState" in content, "Default impl missing"


def test_03_supervisor_rs_has_start_supervisor():
    """supervisor.rs 包含 start_supervisor 函数 (崩溃检测 + 健康检查)"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "pub fn start_supervisor" in content, "start_supervisor function missing"
    assert "CRASH_CHECK_INTERVAL" in content, "crash check interval constant missing"
    assert "HEALTH_CHECK_INTERVAL" in content, "health check interval constant missing"
    assert "try_wait" in content, "try_wait (child process check) missing"
    assert "tokio::time::sleep" in content, "sleep (polling interval) missing"


def test_04_supervisor_rs_has_restart_with_backoff():
    """supervisor.rs 包含 restart_with_backoff (指数退避 1s→2s→4s, 上限 3 次)"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "restart_with_backoff" in content, "restart_with_backoff function missing"
    assert "MAX_RESTART_RETRIES" in content, "MAX_RESTART_RETRIES constant missing"
    assert "2u64.pow" in content, "exponential backoff (2^retry_count) missing"
    # 验证上限为 3
    assert "MAX_RESTART_RETRIES: u32 = 3" in content, "Max retries should be 3"


def test_05_supervisor_rs_has_graceful_shutdown():
    """supervisor.rs 包含 graceful_shutdown (POST /shutdown → 5s → kill)"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "pub async fn graceful_shutdown" in content, "graceful_shutdown function missing"
    assert "GRACEFUL_SHUTDOWN_TIMEOUT" in content, "graceful shutdown timeout constant missing"
    assert "/shutdown" in content, "POST /shutdown endpoint missing"
    assert "Bearer" in content, "Bearer token auth in shutdown missing"
    assert "child.kill()" in content, "kill fallback missing"


def test_06_supervisor_rs_has_degraded_emit():
    """supervisor.rs 重启超限时 emit "sidecar-degraded" 事件"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "sidecar-degraded" in content, "sidecar-degraded event missing"
    assert "emit" in content, "emit function missing"


def test_07_supervisor_rs_has_health_check():
    """supervisor.rs 包含 check_sidecar_health (/health/ready 轮询)"""
    content = (SRC_TAURI / "src" / "supervisor.rs").read_text(encoding="utf-8")
    assert "fn check_sidecar_health" in content, "check_sidecar_health function missing"
    assert "/health/ready" in content, "/health/ready endpoint missing"


# ----------------------------------------------------------------------
# 5.2 integrity.rs 文件结构验证
# ----------------------------------------------------------------------

def test_08_integrity_rs_exists():
    """integrity.rs 文件存在"""
    assert (SRC_TAURI / "src" / "integrity.rs").exists(), "src-tauri/src/integrity.rs not found"


def test_09_integrity_rs_has_verify_function():
    """integrity.rs 包含 verify_integrity 函数"""
    content = (SRC_TAURI / "src" / "integrity.rs").read_text(encoding="utf-8")
    assert "pub fn verify_integrity" in content, "verify_integrity function missing"
    assert "pub fn check_and_emit" in content, "check_and_emit function missing"
    assert "IntegrityReport" in content, "IntegrityReport struct missing"
    assert "IntegrityMismatch" in content, "IntegrityMismatch struct missing"


def test_10_integrity_rs_uses_sha256():
    """integrity.rs 使用 sha2 crate 计算 SHA-256"""
    content = (SRC_TAURI / "src" / "integrity.rs").read_text(encoding="utf-8")
    assert "use sha2::" in content, "sha2 import missing"
    assert "Sha256" in content, "Sha256 hasher missing"
    assert "hasher.update" in content or "hasher.finalize" in content, "SHA-256 hashing logic missing"


def test_11_integrity_rs_has_manifest_parsing():
    """integrity.rs 包含清单解析逻辑 (sha256sum 兼容格式)"""
    content = (SRC_TAURI / "src" / "integrity.rs").read_text(encoding="utf-8")
    assert "parse_manifest" in content, "parse_manifest function missing"
    assert "sidecar.sha256" in content, "manifest filename missing"
    assert "find_manifest" in content, "find_manifest function missing"


def test_12_integrity_rs_emits_on_failure():
    """integrity.rs 校验失败时 emit "sidecar-integrity-failed" 事件"""
    content = (SRC_TAURI / "src" / "integrity.rs").read_text(encoding="utf-8")
    assert "sidecar-integrity-failed" in content, "sidecar-integrity-failed event missing"
    assert "mismatches" in content, "mismatches field in event payload missing"
    assert "missing" in content, "missing field in event payload missing"


# ----------------------------------------------------------------------
# 5.3 gen_sidecar_hash.py 功能验证
# ----------------------------------------------------------------------

def test_13_gen_sidecar_hash_script_exists():
    """scripts/gen_sidecar_hash.py 文件存在"""
    assert (SCRIPTS_DIR / "gen_sidecar_hash.py").exists(), "scripts/gen_sidecar_hash.py not found"


def test_14_gen_sidecar_hash_script_runs(tmp_path):
    """gen_sidecar_hash.py 可正常执行并生成清单"""
    output_file = tmp_path / "sidecar.sha256"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gen_sidecar_hash.py"),
         "--output", str(output_file), "--root", str(PROJECT_ROOT)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"gen_sidecar_hash.py failed: {result.stderr}"
    assert output_file.exists(), "Output manifest file not created"

    content = output_file.read_text(encoding="utf-8")
    # 验证清单格式 (sha256sum 兼容)
    lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
    assert len(lines) > 0, "Manifest should contain at least one file entry"

    # 验证每行格式: <64 hex>  <path>
    for line in lines:
        parts = line.split(None, 1)
        assert len(parts) == 2, f"Invalid manifest line format: {line}"
        hash_hex, path = parts
        assert len(hash_hex) == 64, f"Invalid hash length: {len(hash_hex)} (expected 64)"
        assert all(c in "0123456789abcdef" for c in hash_hex), f"Invalid hex hash: {hash_hex}"
        assert "/" in path or path.endswith(".py"), f"Path should be a Python file: {path}"


def test_15_gen_sidecar_hash_includes_launch_py(tmp_path):
    """生成的清单包含 launch.py"""
    output_file = tmp_path / "sidecar.sha256"
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gen_sidecar_hash.py"),
         "--output", str(output_file), "--root", str(PROJECT_ROOT)],
        capture_output=True, timeout=30,
    )
    content = output_file.read_text(encoding="utf-8")
    assert "launch.py" in content, "Manifest should include launch.py"
    assert "server/main.py" in content, "Manifest should include server/main.py"


# ----------------------------------------------------------------------
# 5.4 lib.rs 集成验证
# ----------------------------------------------------------------------

def test_16_lib_rs_has_supervisor_module():
    """lib.rs 声明 mod supervisor + mod integrity"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "mod supervisor;" in content, "mod supervisor missing"
    assert "mod integrity;" in content, "mod integrity missing"


def test_17_lib_rs_manages_supervisor_state():
    """lib.rs 注册 SupervisorState 到 Tauri manage"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "SupervisorState::default()" in content, ".manage(SupervisorState::default()) missing"
    assert "start_supervisor" in content, "start_supervisor call missing"
    assert "graceful_shutdown" in content, "graceful_shutdown call missing"


def test_18_lib_rs_calls_integrity_check():
    """lib.rs 在 spawn sidecar 之前调用 integrity::check_and_emit"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "integrity::check_and_emit" in content, "integrity check call missing"
    # 验证完整性校验在 spawn 调用之前
    # 注意: spawn_and_wait_ready 在 use 语句中首次出现 (导入), 实际调用在 setup 钩子中
    # 需要找到实际调用位置 (match spawn_and_wait_ready), 而非导入位置
    integrity_pos = content.find("integrity::check_and_emit")
    # 找 setup 钩子中的实际调用 (match 语句中)
    spawn_call_pos = content.find("match spawn_and_wait_ready")
    assert spawn_call_pos != -1, "spawn_and_wait_ready call not found"
    assert integrity_pos < spawn_call_pos, (
        f"Integrity check (pos {integrity_pos}) should be before spawn call (pos {spawn_call_pos})"
    )


def test_19_lib_rs_graceful_shutdown_in_destroyed():
    """lib.rs WindowEvent::Destroyed 使用 graceful_shutdown (异步)"""
    content = (SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "WindowEvent::Destroyed" in content, "Destroyed event handler missing"
    assert "graceful_shutdown" in content, "graceful_shutdown in Destroyed handler missing"
    # 验证异步调用
    assert "tauri::async_runtime::spawn" in content, "async spawn for graceful_shutdown missing"


# ----------------------------------------------------------------------
# 5.5 DegradedUI.tsx 组件验证
# ----------------------------------------------------------------------

def test_20_degraded_ui_exists():
    """DegradedUI.tsx 文件存在"""
    assert (FRONTEND_COMPONENTS / "DegradedUI.tsx").exists(), "DegradedUI.tsx not found"


def test_21_degraded_ui_listens_events():
    """DegradedUI.tsx 监听 sidecar-degraded + sidecar-integrity-failed 事件"""
    content = (FRONTEND_COMPONENTS / "DegradedUI.tsx").read_text(encoding="utf-8")
    assert "sidecar-degraded" in content, "sidecar-degraded event listener missing"
    assert "sidecar-integrity-failed" in content, "sidecar-integrity-failed event listener missing"
    assert "sidecar-error" in content, "sidecar-error event listener missing"
    assert "listen" in content, "Tauri listen function missing"


def test_22_degraded_ui_has_retry_button():
    """DegradedUI.tsx 包含重试按钮"""
    content = (FRONTEND_COMPONENTS / "DegradedUI.tsx").read_text(encoding="utf-8")
    assert "重试" in content, "Retry button missing"
    assert "handleRetry" in content, "handleRetry function missing"
    assert "window.location.reload" in content, "reload on retry missing"


def test_23_degraded_ui_integrated_in_app():
    """app.tsx 导入并渲染 DegradedUI"""
    content = (PROJECT_ROOT / "frontend" / "src" / "app.tsx").read_text(encoding="utf-8")
    assert "import DegradedUI" in content, "DegradedUI import missing"
    assert "<DegradedUI" in content, "DegradedUI component not rendered"


# ----------------------------------------------------------------------
# 5.6 Cargo.toml 依赖验证
# ----------------------------------------------------------------------

def test_24_cargo_toml_has_sha2():
    """Cargo.toml 包含 sha2 依赖 (完整性校验)"""
    content = (SRC_TAURI / "Cargo.toml").read_text(encoding="utf-8")
    assert 'sha2 = ' in content, "sha2 dependency missing in Cargo.toml"


# ----------------------------------------------------------------------
# 5.7 sidecar 优雅关闭端点验证 (集成测试)
# ----------------------------------------------------------------------

def _start_sidecar(timeout: float = 15.0):
    """启动 sidecar 并返回 (process, port, token)"""
    env = os.environ.copy()
    env["NEBULA_SHELL"] = "tauri"
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "launch.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    port = None
    token = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                stderr = proc.stderr.read()
                raise RuntimeError(f"Sidecar exited early: {stderr}")
            continue
        line = line.strip()
        if line.startswith("PORT="):
            port = int(line[5:])
        elif line.startswith("TOKEN="):
            token = line[6:]
        elif line == "READY":
            break
    if not port or not token:
        proc.kill()
        raise RuntimeError("Failed to get PORT/TOKEN from sidecar")
    return proc, port, token


def _http_get(url: str, token: str = None, timeout: float = 5.0):
    """带 Bearer token 的 GET 请求"""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""


def _http_post(url: str, token: str = None, timeout: float = 5.0):
    """带 Bearer token 的 POST 请求"""
    req = urllib.request.Request(url, method="POST")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Sidecar integration test skipped in CI (requires Python launch.py)",
)
def test_25_sidecar_shutdown_endpoint():
    """sidecar /shutdown 端点可正常关闭 (优雅关闭验证)"""
    proc, port, token = _start_sidecar()

    try:
        # 等待 sidecar 就绪
        time.sleep(2)

        # 验证 /health/ready 返回 200
        status, _ = _http_get(f"http://127.0.0.1:{port}/health/ready", token=token)
        assert status == 200, f"/health/ready should return 200, got {status}"

        # POST /shutdown (带 Bearer token)
        status, _ = _http_post(f"http://127.0.0.1:{port}/shutdown", token=token)
        assert status in (200, 200), f"/shutdown should return 200, got {status}"

        # 等待 sidecar 退出 (最多 5s,验证优雅关闭)
        deadline = time.time() + 5
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.2)

        # 验证 sidecar 已退出
        assert proc.poll() is not None, "Sidecar should exit after /shutdown"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_26_sidecar_shutdown_whitelisted():
    """/shutdown 端点在认证白名单中 (Tauri 需要在无 token 时也能关闭 sidecar)"""
    proc, port, token = _start_sidecar()

    try:
        time.sleep(2)

        # /shutdown 在白名单中,无 token 也能访问 (设计如此)
        # 参考 server/main.py: unauthenticated_paths = {"/health/ready", "/health", "/shutdown"}
        status, _ = _http_post(f"http://127.0.0.1:{port}/shutdown", token=None)
        assert status == 200, f"/shutdown without token should return 200 (whitelisted), got {status}"
    finally:
        # 清理: sidecar 已被 /shutdown 关闭
        if proc.poll() is None:
            proc.kill()
            proc.wait()
