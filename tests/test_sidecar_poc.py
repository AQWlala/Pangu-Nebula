"""P0-W2 Sidecar PoC 端到端验证 (v2.1.0 Phase 0)

Go/No-Go #3 硬检查点测试 — 验证 Tauri + Python sidecar 双进程架构可行性。

模拟 Tauri 主进程的行为:
1. spawn Python sidecar 子进程 (NEBULA_SHELL=tauri)
2. 读取 stdout 解析 PORT=/TOKEN=/READY 握手协议
3. 轮询 /health/ready 就绪检测
4. 带 Bearer token 请求 /health-check → 200
5. 无 Bearer token 请求 /health-check → 401
6. 优雅关闭 (POST /shutdown)

失败动作: 触发回退讨论 (评估是否回退 PyWebView)
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_PY = PROJECT_ROOT / "launch.py"


@pytest.fixture(scope="module")
def sidecar_process():
    """启动真实 Python sidecar 子进程,返回 (port, token, process)"""
    env = os.environ.copy()
    env["NEBULA_SHELL"] = "tauri"

    proc = subprocess.Popen(
        [sys.executable, str(LAUNCH_PY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    port = None
    token = None
    ready = False
    start_time = time.time()
    timeout = 30  # 30s 超时 (含 Python 启动 + DB 初始化)

    # 逐行读取 stdout 解析握手协议
    for line in iter(proc.stdout.readline, b""):
        line_str = line.decode("utf-8", errors="replace").strip()
        if line_str.startswith("PORT="):
            port = int(line_str[5:])
        elif line_str.startswith("TOKEN="):
            token = line_str[6:]
        elif line_str == "READY":
            ready = True
            break
        if time.time() - start_time > timeout:
            proc.kill()
            stderr_output = proc.stderr.read().decode("utf-8", errors="replace")
            pytest.fail(
                f"Sidecar handshake timeout (30s). stderr:\n{stderr_output}"
            )

    assert ready, "Sidecar did not emit READY signal"
    assert port is not None, "Sidecar did not emit PORT="
    assert token is not None, "Sidecar did not emit TOKEN="
    assert 1 <= port <= 65535, f"Invalid port: {port}"
    assert len(token) == 64, f"Invalid token length: {len(token)} (expected 64)"

    yield {"port": port, "token": token, "process": proc}

    # 清理: kill sidecar 进程
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_health_ready(port: int, timeout: int = 15) -> bool:
    """轮询 /health/ready 就绪检测,间隔 200ms,超时 timeout 秒"""
    url = f"http://127.0.0.1:{port}/health/ready"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.2)
    return False


# ----------------------------------------------------------------------
# Go/No-Go #3: 5 项全部通过才算 PoC 成功
# ----------------------------------------------------------------------

def test_01_sidecar_handshake_protocol(sidecar_process):
    """验证项 1: sidecar stdout 输出 PORT=/TOKEN=/READY 握手协议"""
    info = sidecar_process
    assert info["port"] > 0, "PORT must be positive"
    assert len(info["token"]) == 64, "TOKEN must be 64 hex chars"
    assert all(c in "0123456789abcdef" for c in info["token"]), \
        "TOKEN must be valid hex"


def test_02_health_ready_polling(sidecar_process):
    """验证项 2: 轮询 /health/ready 返回 200 (10s 超时)"""
    info = sidecar_process
    assert wait_for_health_ready(info["port"], timeout=15), \
        f"/health/ready did not return 200 within 15s at port {info['port']}"


def test_03_health_ready_response_fields(sidecar_process):
    """验证项 3: /health/ready 响应包含 status/db_initialized/services_loaded"""
    import json
    info = sidecar_process
    # 先等待就绪
    assert wait_for_health_ready(info["port"], timeout=15)

    url = f"http://127.0.0.1:{info['port']}/health/ready"
    with urllib.request.urlopen(url, timeout=2) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    assert data["status"] == "ready", f"Expected status=ready, got {data['status']}"
    assert data["db_initialized"] is True, "DB must be initialized"
    assert data["services_loaded"] is True, "Services must be loaded"
    assert "uptime_seconds" in data


def test_04_bearer_token_auth_grants_access(sidecar_process):
    """验证项 4: 带 Bearer token 请求 /health-check → 200"""
    info = sidecar_process
    assert wait_for_health_ready(info["port"], timeout=15)

    url = f"http://127.0.0.1:{info['port']}/health-check"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {info['token']}")

    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
    except urllib.error.HTTPError as e:
        pytest.fail(f"Valid Bearer token rejected: HTTP {e.code}")


def test_05_no_bearer_token_returns_401(sidecar_process):
    """验证项 5: 无 Bearer token 请求 /health-check → 401"""
    info = sidecar_process
    assert wait_for_health_ready(info["port"], timeout=15)

    url = f"http://127.0.0.1:{info['port']}/health-check"
    req = urllib.request.Request(url)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=2)

    assert exc_info.value.code == 401, \
        f"Expected 401 without token, got {exc_info.value.code}"


def test_06_sidecar_process_alive(sidecar_process):
    """验证项 6: sidecar 进程在测试期间保持存活"""
    info = sidecar_process
    assert info["process"].poll() is None, "Sidecar process should still be running"


def test_07_shutdown_endpoint(sidecar_process):
    """验证项 7: POST /shutdown 触发优雅关闭 (放在最后执行)"""
    import json
    info = sidecar_process
    assert wait_for_health_ready(info["port"], timeout=15)

    url = f"http://127.0.0.1:{info['port']}/shutdown"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert data["data"]["shutting_down"] is True
    except urllib.error.HTTPError as e:
        pytest.fail(f"POST /shutdown failed: HTTP {e.code}")

    # 等待进程退出 (最多 5s)
    try:
        info["process"].wait(timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail("Sidecar did not exit within 5s after POST /shutdown")
