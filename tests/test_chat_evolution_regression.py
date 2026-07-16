"""TDD 回归测试: 复现并锁死三个 Bug

Bug1: GET /evolution 返回引擎信息对象 (非数组), 前端 EvolutionPage 误当数组 .map 崩溃
      正确契约: 日志列表在 GET /evolution/logs, 返回 {items, count}
Bug2: 对话未关联 persona 时, POST /chat/conversations/{id}/messages 直接报
      "Persona not configured", 应回退到系统默认 persona 或返回友好引导
Bug3: (前端, 见 vitest 套件) DiagnosticsPage reload 跳页
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    """从 SSE 响应文本解析出事件列表"""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Bug1: /evolution vs /evolution/logs 契约
# ---------------------------------------------------------------------------


class TestEvolutionContract:
    """锁定进化引擎 API 契约, 防止前端 .map 崩溃复发"""

    def test_get_evolution_returns_engine_info_not_array(self, client: TestClient):
        """GET /evolution 返回引擎信息对象 (含 engine/version/phases), 不是日志数组"""
        resp = client.get("/evolution")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        # 引擎信息是 dict, 不是 list — 这是前端崩溃的根因 (前端误当 list .map)
        assert isinstance(data, dict)
        assert "engine" in data
        assert "phases" in data
        # 明确不应是数组
        assert not isinstance(data, list)

    def test_get_evolution_logs_returns_items_array(self, client: TestClient):
        """GET /evolution/logs 返回 {items: [...], count: int}, items 必须是数组"""
        resp = client.get("/evolution/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert isinstance(data, dict)
        assert "items" in data
        # items 必须是 list — 前端 .map 的数据源
        assert isinstance(data["items"], list)
        assert "count" in data
        assert isinstance(data["count"], int)


# ---------------------------------------------------------------------------
# Bug2: persona 缺失时应回退到系统默认, 不应直接报错
# ---------------------------------------------------------------------------


class TestChatPersonaFallback:
    """对话未关联 persona 时, stream_reply 应回退到系统默认 persona, 不报错"""

    def test_stream_reply_without_persona_does_not_report_config_error(
        self, client: TestClient
    ):
        """无 persona 的对话发消息, 不应返回 'Persona not configured' 错误

        期望行为 (修复后):
        - 回退到系统默认 persona 继续对话 (产生 token/done), 或
        - 返回友好引导错误 (引导用户去角色管理创建角色)
        - 不应返回裸的 'Persona not configured for this conversation'
        """
        # 1. 通过 API 创建一个无 persona 的对话
        create_resp = client.post(
            "/chat/conversations",
            json={"title": "TDD-无角色对话", "persona_id": None},
        )
        assert create_resp.status_code == 200
        conv = create_resp.json()["data"]
        conv_id = conv["id"]

        # 2. 发送消息 (SSE 流)
        resp = client.post(
            f"/chat/conversations/{conv_id}/messages",
            json={"content": "你好"},
        )

        # 3. 解析 SSE 事件
        events = _parse_sse(resp.text)

        # 4. 不应有 "Persona not configured" 错误
        error_events = [e for e in events if e.get("type") == "error"]
        persona_errors = [
            e for e in error_events if "Persona not configured" in e.get("error", "")
        ]
        assert persona_errors == [], (
            f"应回退到默认 persona 或友好引导, 不应报 'Persona not configured': "
            f"{persona_errors}"
        )

    def test_stream_reply_without_persona_returns_success_or_friendly_error(
        self, client: TestClient
    ):
        """无 persona 时: 要么回退成功产生 token/done, 要么返回友好引导错误"""
        create_resp = client.post(
            "/chat/conversations",
            json={"title": "TDD-无角色对话2", "persona_id": None},
        )
        conv_id = create_resp.json()["data"]["id"]

        resp = client.post(
            f"/chat/conversations/{conv_id}/messages",
            json={"content": "测试"},
        )
        events = _parse_sse(resp.text)
        types = [e.get("type") for e in events]

        # 至少应该有 done 或 token 事件 (回退成功), 或友好 error (引导用户)
        has_success = "token" in types or "done" in types
        has_error = "error" in types
        assert has_success or has_error, (
            f"应返回 token/done 或 error 事件, 实际: {types}"
        )

        if has_error:
            err = next(e for e in events if e.get("type") == "error")
            # 错误信息应引导用户, 不应是裸的 "Persona not configured"
            assert "Persona not configured" not in err.get("error", ""), (
                f"错误应是友好引导, 不应裸报 'Persona not configured': {err}"
            )
