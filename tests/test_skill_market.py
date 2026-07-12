"""P2P 技能市场测试 (T5.4)

覆盖:
1. 市场模块信息端点
2. 发布技能到市场
3. 发布无效技能应被拒绝(验证失败)
4. 搜索技能(关键词/能力过滤)
5. 从市场安装技能
6. 评分机制
7. 查看评分
8. 列出所有已发布技能
9. 重复发布(覆盖)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.skill_market import (
    _reset_market_for_testing,
    _get_market_state_for_testing,
    router,
)


# ===== 测试用 FastAPI app(独立挂载 skill_market 路由) =====


def _make_test_app() -> FastAPI:
    """创建测试用 FastAPI 应用,挂载 skill_market 路由"""
    app = FastAPI(title="test-skill-market")
    app.include_router(router)
    return app


@pytest.fixture
def market_client():
    """每个测试用例都使用干净的市场状态"""
    _reset_market_for_testing()
    app = _make_test_app()
    with TestClient(app) as c:
        yield c
    _reset_market_for_testing()


# ===== 1. 市场模块信息 =====


def test_market_info(market_client):
    """GET /skill-market 应返回模块信息"""
    r = market_client.get("/skill-market")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["module"] == "skill-market"
    assert body["data"]["phase"] == "T5.4"
    assert body["data"]["decentralized"] is True
    assert body["data"]["skills_count"] == 0


# ===== 2. 发布技能 =====


def test_publish_skill(market_client):
    """POST /skill-market/publish 应发布技能到市场"""
    r = market_client.post(
        "/skill-market/publish",
        json={
            "name": "code-reviewer",
            "version": "1.2.0",
            "description": "A code review skill",
            "author": "tester",
            "capabilities": ["text", "code"],
            "publisher": "alice",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["name"] == "code-reviewer"
    assert data["version"] == "1.2.0"
    assert data["size"] > 0
    assert len(data["checksum"]) == 64  # SHA256 hex

    # 市场计数应增加
    info = market_client.get("/skill-market").json()
    assert info["data"]["skills_count"] == 1


def test_publish_skill_invalid_name(market_client):
    """无效技能名应被拒绝(400)"""
    r = market_client.post(
        "/skill-market/publish",
        json={"name": "bad/name", "version": "1.0.0"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["ok"] is False
    assert "validation" in body["detail"]["error"].lower() or "name" in body["detail"]["error"].lower()


def test_publish_skill_invalid_version(market_client):
    """无效版本号应被拒绝"""
    r = market_client.post(
        "/skill-market/publish",
        json={"name": "bad-version", "version": "not-a-version"},
    )
    assert r.status_code == 400


def test_publish_skill_with_code(market_client):
    """发布带代码的技能应成功"""
    import base64

    code = b"def handler():\n    return 'ok'\n"
    r = market_client.post(
        "/skill-market/publish",
        json={
            "name": "code-skill",
            "version": "0.1.0",
            "code": base64.b64encode(code).decode(),
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "code-skill"


# ===== 3. 搜索技能 =====


def test_search_skills_empty(market_client):
    """空市场搜索应返回空列表"""
    r = market_client.get("/skill-market/search")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["count"] == 0
    assert body["data"]["skills"] == []


def test_search_skills_by_keyword(market_client):
    """按关键词搜索"""
    # 发布两个技能
    market_client.post(
        "/skill-market/publish",
        json={"name": "code-reviewer", "description": "review code", "version": "1.0.0"},
    )
    market_client.post(
        "/skill-market/publish",
        json={"name": "summarizer", "description": "summarize text", "version": "1.0.0"},
    )

    # 搜索 "code"
    r = market_client.get("/skill-market/search", params={"q": "code"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["count"] == 1
    assert body["data"]["skills"][0]["name"] == "code-reviewer"


def test_search_skills_by_capability(market_client):
    """按能力过滤搜索"""
    market_client.post(
        "/skill-market/publish",
        json={
            "name": "vision-skill",
            "version": "1.0.0",
            "capabilities": ["text", "vision"],
        },
    )
    market_client.post(
        "/skill-market/publish",
        json={
            "name": "text-only",
            "version": "1.0.0",
            "capabilities": ["text"],
        },
    )

    # 过滤 vision 能力
    r = market_client.get("/skill-market/search", params={"capability": "vision"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["count"] == 1
    assert body["data"]["skills"][0]["name"] == "vision-skill"


# ===== 4. 从市场安装 =====


def test_install_from_market(market_client, tmp_path):
    """从市场安装技能应成功"""
    # 先发布
    market_client.post(
        "/skill-market/publish",
        json={
            "name": "installable-skill",
            "version": "2.0.0",
            "description": "can be installed",
        },
    )

    # 安装到临时目录
    r = market_client.post(
        "/skill-market/install",
        json={"name": "installable-skill", "target_dir": str(tmp_path)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["name"] == "installable-skill"
    assert body["data"]["version"] == "2.0.0"
    # 文件应存在
    assert (tmp_path / "installable-skill.skill").exists()


def test_install_not_in_market(market_client):
    """安装市场中不存在的技能应返回 404"""
    r = market_client.post(
        "/skill-market/install",
        json={"name": "nonexistent"},
    )
    assert r.status_code == 404


# ===== 5. 评分机制 =====


def test_rate_skill(market_client):
    """为技能评分应成功并影响平均分"""
    market_client.post(
        "/skill-market/publish",
        json={"name": "rateable", "version": "1.0.0"},
    )

    # 第一次评分
    r = market_client.post(
        "/skill-market/rate",
        json={"name": "rateable", "score": 4.5, "rater": "alice", "comment": "good"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["score"] == 4.5
    assert body["data"]["avg_score"] == 4.5
    assert body["data"]["rating_count"] == 1

    # 第二次评分
    r = market_client.post(
        "/skill-market/rate",
        json={"name": "rateable", "score": 3.0, "rater": "bob"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["rating_count"] == 2
    # 平均分 = (4.5 + 3.0) / 2 = 3.75
    assert body["data"]["avg_score"] == 3.75


def test_rate_skill_invalid_score(market_client):
    """超出 0-5 范围的评分应被拒绝"""
    market_client.post(
        "/skill-market/publish",
        json={"name": "rateable", "version": "1.0.0"},
    )

    r = market_client.post(
        "/skill-market/rate",
        json={"name": "rateable", "score": 6.0},
    )
    assert r.status_code == 422  # pydantic 验证错误


def test_rate_skill_not_in_market(market_client):
    """为不存在的技能评分应返回 404"""
    r = market_client.post(
        "/skill-market/rate",
        json={"name": "nonexistent", "score": 4.0},
    )
    assert r.status_code == 404


# ===== 6. 查看评分 =====


def test_get_ratings(market_client):
    """查看技能评分列表"""
    market_client.post(
        "/skill-market/publish",
        json={"name": "rated-skill", "version": "1.0.0"},
    )
    market_client.post(
        "/skill-market/rate",
        json={"name": "rated-skill", "score": 5.0, "rater": "alice", "comment": "excellent"},
    )
    market_client.post(
        "/skill-market/rate",
        json={"name": "rated-skill", "score": 4.0, "rater": "bob"},
    )

    r = market_client.get("/skill-market/ratings/rated-skill")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["rating_count"] == 2
    assert body["data"]["avg_score"] == 4.5
    ratings = body["data"]["ratings"]
    assert len(ratings) == 2
    assert any(r["rater"] == "alice" for r in ratings)
    assert any(r["rater"] == "bob" for r in ratings)


def test_get_ratings_not_found(market_client):
    """查看不存在技能的评分应 404"""
    r = market_client.get("/skill-market/ratings/nonexistent")
    assert r.status_code == 404


# ===== 7. 列出所有已发布技能 =====


def test_list_market_skills(market_client):
    """列出所有已发布技能"""
    market_client.post(
        "/skill-market/publish",
        json={"name": "skill-a", "version": "1.0.0"},
    )
    market_client.post(
        "/skill-market/publish",
        json={"name": "skill-b", "version": "2.0.0"},
    )

    r = market_client.get("/skill-market/list")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["count"] == 2
    names = [s["name"] for s in body["data"]["skills"]]
    assert "skill-a" in names
    assert "skill-b" in names


# ===== 8. 重复发布覆盖 =====


def test_publish_overwrite(market_client):
    """重复发布同名技能应覆盖旧条目"""
    market_client.post(
        "/skill-market/publish",
        json={"name": "duplicate", "version": "1.0.0", "description": "first"},
    )
    market_client.post(
        "/skill-market/publish",
        json={"name": "duplicate", "version": "2.0.0", "description": "second"},
    )

    # 应只有 1 个条目
    info = market_client.get("/skill-market").json()
    assert info["data"]["skills_count"] == 1

    # 列表中应是 v2.0.0
    listing = market_client.get("/skill-market/list").json()
    skill = [s for s in listing["data"]["skills"] if s["name"] == "duplicate"][0]
    assert skill["version"] == "2.0.0"
    assert skill["description"] == "second"


# ===== 9. 市场内存状态可直接访问(测试辅助) =====


def test_market_state_helper():
    """_get_market_state_for_testing 应返回内存市场字典"""
    _reset_market_for_testing()
    market, data = _get_market_state_for_testing()
    assert market == {}
    assert data == {}
    _reset_market_for_testing()
