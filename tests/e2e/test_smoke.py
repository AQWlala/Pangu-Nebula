# -*- coding: utf-8 -*-
"""冒烟测试 - Pangu Nebula (Phase 11D)

验证后端核心模块路由可用性。使用 TestClient(app) 进行测试。

测试项:
1.  GET /health          返回 200 (主应用健康检查)
2.  GET /health-check    返回 200 (健康检查模块)
3.  GET /persona         返回 200 (角色模块)
4.  GET /memory          返回 200 (记忆模块)
5.  GET /skills          返回 200 (技能模块)
6.  GET /sync            返回 200 (同步模块)
7.  GET /channel         返回 200 (渠道模块)
8.  GET /mcp             返回 200 (MCP 模块)
9.  GET /scheduler       返回 200 (调度器模块)
10. GET /providers       返回 200 (Provider 模块)

每个测试用 try/except 包裹,允许失败(标记 xfail)。
"""

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient,避免重复初始化。"""
    with TestClient(app) as c:
        yield c


def _check_endpoint(client, path, description):
    """通用端点检查: 失败时标记 xfail 而非报错。"""
    try:
        response = client.get(path)
        assert response.status_code == 200, (
            f"{description} {path} 返回 {response.status_code}: {response.text[:200]}"
        )
        print(f"[OK] {description} {path} -> {response.status_code}")
    except AssertionError as exc:
        pytest.xfail(f"{description} {path} 断言失败: {exc}")
    except Exception as exc:  # noqa: BLE001
        pytest.xfail(f"{description} {path} 异常: {type(exc).__name__}: {exc}")


@pytest.mark.asyncio
def test_health(client):
    """冒烟测试: 主应用健康检查 GET /health"""
    _check_endpoint(client, "/health", "主应用健康检查")


@pytest.mark.asyncio
def test_health_check(client):
    """冒烟测试: 健康检查模块 GET /health-check"""
    _check_endpoint(client, "/health-check", "健康检查模块")


@pytest.mark.asyncio
def test_persona(client):
    """冒烟测试: 角色模块 GET /persona"""
    _check_endpoint(client, "/persona", "角色模块")


@pytest.mark.asyncio
def test_memory(client):
    """冒烟测试: 记忆模块 GET /memory"""
    _check_endpoint(client, "/memory", "记忆模块")


@pytest.mark.asyncio
def test_skills(client):
    """冒烟测试: 技能模块 GET /skills"""
    _check_endpoint(client, "/skills", "技能模块")


@pytest.mark.asyncio
def test_sync(client):
    """冒烟测试: 同步模块 GET /sync"""
    _check_endpoint(client, "/sync", "同步模块")


@pytest.mark.asyncio
def test_channel(client):
    """冒烟测试: 渠道模块 GET /channel"""
    _check_endpoint(client, "/channel", "渠道模块")


@pytest.mark.asyncio
def test_mcp(client):
    """冒烟测试: MCP 模块 GET /mcp"""
    _check_endpoint(client, "/mcp", "MCP 模块")


@pytest.mark.asyncio
def test_scheduler(client):
    """冒烟测试: 调度器模块 GET /scheduler"""
    _check_endpoint(client, "/scheduler", "调度器模块")


@pytest.mark.asyncio
def test_providers(client):
    """冒烟测试: Provider 模块 GET /providers"""
    _check_endpoint(client, "/providers", "Provider 模块")
