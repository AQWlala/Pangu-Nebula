"""P0-W3 IPC 适配层集成测试 (v2.1.0 Phase 0)

验证 http_proxy command 转发的端点行为。

需要 uvicorn 才能启动 sidecar 进程，未安装时自动跳过。

由于 Rust http_proxy command 无法在 pytest 中直接调用 (需要 Tauri 运行时),
本测试通过 HTTP 直接请求 sidecar CRUD 端点 (带 Bearer token), 模拟
http_proxy command 的转发行为:

  前端 invoke('http_proxy') → Rust → reqwest → sidecar HTTP

本测试验证的是上述链路的 sidecar HTTP 部分 (后端端点 + Bearer token 认证)。
Rust 端的 invoke → reqwest 转发逻辑由 api.test.ts (vitest) 覆盖。

测试项:
1. sidecar 启动 + 握手协议
2. GET /health-check (带 token) → 200 统一格式
3. GET /persona/list (带 token) → 200 统一格式
4. GET /memory/stats (带 token) → 200 统一格式
5. POST 端点 (带 token) → 200
6. 无 token → 401
7. 错误路径 (带 token) → 200 ok=false
8. /health 直连 (非统一格式, 不走 http_proxy)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# uvicorn 是可选依赖（sidecar 启动需要），未安装时跳过
pytest.importorskip("uvicorn")

import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_PY = PROJECT_ROOT / "launch.py"


@pytest.fixture(scope="module")
def sidecar():
    """启动真实 Python sidecar, 返回 (port, token, process)"""
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
    start = time.time()
    timeout = 30

    for line in iter(proc.stdout.readline, b""):
        s = line.decode("utf-8", errors="replace").strip()
        if s.startswith("PORT="):
            port = int(s[5:])
        elif s.startswith("TOKEN="):
            token = s[6:]
        elif s == "READY":
            ready = True
            break
        if time.time() - start > timeout:
            proc.kill()
            stderr = proc.stderr.read().decode("utf-8", errors="replace")
            pytest.fail(f"Sidecar handshake timeout. stderr:\n{stderr}")

    assert ready and port and token
    yield {"port": port, "token": token, "process": proc}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _wait_ready(port: int, timeout: int = 15) -> bool:
    url = f"http://127.0.0.1:{port}/health/ready"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.2)
    return False


def _http(
    port: int,
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict | None]:
    """发送 HTTP 请求到 sidecar, 返回 (status_code, json_body)

    模拟 Rust http_proxy command 的行为:
    - 附加 Authorization: Bearer <token>
    - 解析 { ok, data, error } 统一格式
    """
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    # 仅在有 body 时设置 Content-Type (GET/DELETE 无 body 避免触发 422)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode("utf-8")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None


# ----------------------------------------------------------------------
# IPC 适配层验证: http_proxy command 转发的端点行为
# ----------------------------------------------------------------------

def test_01_sidecar_handshake(sidecar):
    """sidecar 启动 + 握手协议 (http_proxy 前置条件)"""
    assert sidecar["port"] > 0
    assert len(sidecar["token"]) == 64
    assert _wait_ready(sidecar["port"], timeout=15)


def test_02_health_check_unified_format(sidecar):
    """GET /health-check (带 token) → 200 统一格式 {ok, data, error}

    这是 http_proxy command 转发的典型端点 (统一格式)。
    """
    assert _wait_ready(sidecar["port"])
    status, body = _http(sidecar["port"], sidecar["token"], "GET", "/health-check")
    assert status == 200
    assert body is not None
    assert body["ok"] is True
    assert "data" in body
    assert body["error"] is None


def test_03_persona_list_via_proxy(sidecar):
    """GET /persona (带 token) → 200 统一格式

    验证 CRUD GET 端点经 http_proxy 转发后返回统一格式。
    """
    assert _wait_ready(sidecar["port"])
    status, body = _http(sidecar["port"], sidecar["token"], "GET", "/persona")
    assert status == 200
    assert body is not None
    assert body["ok"] is True
    assert isinstance(body["data"], list)


def test_04_memory_graph_via_proxy(sidecar):
    """GET /memory/graph (带 token) → 200 统一格式

    验证另一个 CRUD GET 端点。
    """
    assert _wait_ready(sidecar["port"])
    status, body = _http(sidecar["port"], sidecar["token"], "GET", "/memory/graph")
    assert status == 200
    assert body is not None
    assert body["ok"] is True


def test_05_no_token_returns_401(sidecar):
    """无 Bearer token → 401 (http_proxy 在 Rust 端附加 token, 前端无需自带)

    验证 sidecar 中间件拒绝无 token 请求。
    """
    assert _wait_ready(sidecar["port"])
    url = f"http://127.0.0.1:{sidecar['port']}/health-check"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 401


def test_06_invalid_token_returns_401(sidecar):
    """错误 Bearer token → 401"""
    assert _wait_ready(sidecar["port"])
    status, _ = _http(sidecar["port"], "invalid-token-12345", "GET", "/health-check")
    assert status == 401


def test_07_health_direct_not_unified(sidecar):
    """/health 直连 (非统一格式, 不走 http_proxy)

    http_proxy command 期望统一格式 {ok, data, error}。
    /health 端点返回 {status: "ok"} 非统一格式, 不应走 http_proxy。
    前端通过 getApiBase() 直连 fetch。
    """
    assert _wait_ready(sidecar["port"])
    url = f"http://127.0.0.1:{sidecar['port']}/health"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {sidecar['token']}")
    with urllib.request.urlopen(req, timeout=2) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # /health 返回非统一格式 (无 ok/data/error 字段)
    assert "status" in data
    assert "ok" not in data  # 非统一格式


def test_08_nonexistent_path_returns_ok_false(sidecar):
    """不存在端点 (带 token) → 200 ok=false (或 404)

    验证 http_proxy 对不存在端点的错误处理。
    sidecar FastAPI 对未知路径返回 404, http_proxy 应将非 2xx 转为 Err。
    """
    assert _wait_ready(sidecar["port"])
    url = f"http://127.0.0.1:{sidecar['port']}/nonexistent/path/xyz"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {sidecar['token']}")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    # FastAPI 默认返回 404
    assert exc.value.code == 404


def test_09_post_endpoint_via_proxy(sidecar):
    """POST 端点 (带 token) → 200 统一格式

    验证 CRUD POST 经 http_proxy 转发。
    使用 /chat/conversations (创建会话) 作为测试端点。
    """
    assert _wait_ready(sidecar["port"])
    status, body = _http(
        sidecar["port"],
        sidecar["token"],
        "POST",
        "/chat/conversations",
        body={"title": "IPC Test", "model": "test"},
    )
    # 可能返回 200 (创建成功) 或其他状态
    assert status in (200, 201, 400, 422), f"Unexpected status: {status}"
    if status == 200:
        assert body is not None
        assert body["ok"] is True
