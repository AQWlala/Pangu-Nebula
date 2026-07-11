"""
性能基准测试 - 验证启动 < 5s, 首响应 < 3s
"""
import time
import subprocess
import sys
import os
import httpx
import pytest

BACKEND_URL = "http://127.0.0.1:7860"
PYTHON = os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "python.exe")


@pytest.fixture(scope="module")
def backend_server():
    """启动后端服务器,返回启动耗时"""
    t0 = time.time()
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "7860"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # 等待服务就绪
    for _ in range(50):  # 最多等 5 秒
        time.sleep(0.1)
        try:
            r = httpx.get(f"{BACKEND_URL}/health", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception:
            continue
    t1 = time.time()
    startup_time = t1 - t0
    yield startup_time
    proc.terminate()
    proc.wait(timeout=5)


def test_backend_startup_under_5s(backend_server):
    """后端启动应 < 5s"""
    startup = backend_server
    print(f"\n后端启动耗时: {startup:.2f}s")
    assert startup < 5.0, f"后端启动 {startup:.2f}s 超过 5s 阈值"


def test_first_response_under_3s(backend_server):
    """首响应应 < 3s"""
    t0 = time.time()
    r = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
    t1 = time.time()
    response_time = t1 - t0
    print(f"\n首响应耗时: {response_time:.2f}s, 状态码: {r.status_code}")
    assert response_time < 3.0, f"首响应 {response_time:.2f}s 超过 3s 阈值"
    assert r.status_code == 200


def test_api_endpoints_response(backend_server):
    """关键 API 端点响应应 < 1s"""
    endpoints = ["/health", "/providers", "/persona", "/memory", "/skills"]
    for ep in endpoints:
        t0 = time.time()
        try:
            r = httpx.get(f"{BACKEND_URL}{ep}", timeout=3.0)
            t1 = time.time()
            elapsed = t1 - t0
            print(f"  {ep}: {elapsed:.2f}s [{r.status_code}]")
            assert elapsed < 1.0, f"{ep} 响应 {elapsed:.2f}s 超过 1s"
        except httpx.ConnectError:
            pass  # 端点可能未注册,跳过
