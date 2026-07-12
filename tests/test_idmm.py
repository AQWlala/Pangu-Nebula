"""Tests for IDMM 三层故障保活引擎 (T1.2 / T1.3 / T1.9 / T1.10)。

覆盖:
- L1 规则层: 超时检测 + 指数退避重试 (T1.2)
- L2 backup model 层: provider 健康检查 + 自动切换 (T1.3)
- L3 sidecar 层: 停滞检测 + 提示注入 (T1.9)
- T1.10 集成: LoopEngine ↔ IDMM 反思保活闭环
- API 端点: /idmm/* 路由
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.idmm import router as idmm_router
from server.services.idmm import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_STAGNATION_THRESHOLD,
    IDMMEngine,
    L1Result,
    L2Result,
    StagnationReport,
)


# ===== L1 规则层测试 (T1.2) =====


class TestL1RuleLayer:
    """L1 规则层: 超时检测 + 指数退避重试"""

    @pytest.mark.asyncio
    async def test_l1_success_first_try(self):
        """L1: 任务首次成功,无重试"""
        engine = IDMMEngine()

        async def _task():
            return "ok"

        result = await engine.execute_with_l1_retry(_task, max_retries=3)

        assert result.success is True
        assert result.result == "ok"
        assert result.total_retries == 0
        assert len(result.attempts) == 1
        assert result.attempts[0].success is True
        assert result.last_error is None

    @pytest.mark.asyncio
    async def test_l1_retry_on_timeout_then_success(self):
        """L1: 超时任务自动重试,最终成功 (验收①)"""
        engine = IDMMEngine()
        call_count = {"n": 0}

        async def _task():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise TimeoutError("模拟超时")
            return "recovered"

        # 使用很短的退避避免测试慢
        result = await engine.execute_with_l1_retry(
            _task, max_retries=3, base_delay=0.01, max_delay=0.05
        )

        assert result.success is True
        assert result.result == "recovered"
        assert result.total_retries == 2
        assert len(result.attempts) == 3
        # 前两次失败,第三次成功
        assert result.attempts[0].success is False
        assert result.attempts[1].success is False
        assert result.attempts[2].success is True
        assert "TimeoutError" in result.attempts[0].error

    @pytest.mark.asyncio
    async def test_l1_max_retries_configurable(self):
        """L1: 重试次数可配 (验收②)"""
        engine = IDMMEngine()
        call_counts = []

        async def _make_task():
            count = {"n": 0}

            async def _task():
                count["n"] += 1
                raise TimeoutError("始终超时")

            return count, _task

        # max_retries=1: 总尝试 2 次
        count1, task1 = await _make_task()
        r1 = await engine.execute_with_l1_retry(
            task1, max_retries=1, base_delay=0.01
        )
        assert r1.success is False
        assert r1.total_retries == 1
        assert len(r1.attempts) == 2
        assert count1["n"] == 2

        # max_retries=3: 总尝试 4 次
        count2, task2 = await _make_task()
        r2 = await engine.execute_with_l1_retry(
            task2, max_retries=3, base_delay=0.01
        )
        assert r2.success is False
        assert r2.total_retries == 3
        assert len(r2.attempts) == 4
        assert count2["n"] == 4

    @pytest.mark.asyncio
    async def test_l1_non_retryable_exception_fails_immediately(self):
        """L1: 非重试型异常(如 ValueError)立即失败,不重试"""
        engine = IDMMEngine()
        call_count = {"n": 0}

        async def _task():
            call_count["n"] += 1
            raise ValueError("参数错误,不可重试")

        result = await engine.execute_with_l1_retry(
            _task, max_retries=3, base_delay=0.01
        )

        assert result.success is False
        assert result.total_retries == 0
        assert len(result.attempts) == 1
        assert call_count["n"] == 1
        assert "ValueError" in result.last_error

    @pytest.mark.asyncio
    async def test_l1_exponential_backoff_delays(self):
        """L1: 验证指数退避延迟递增 (base_delay * 2^(n-1))"""
        engine = IDMMEngine()

        async def _task():
            raise TimeoutError("持续超时")

        result = await engine.execute_with_l1_retry(
            _task, max_retries=3, base_delay=0.1, max_delay=10.0
        )

        assert result.success is False
        assert len(result.attempts) == 4
        # 前三次失败后有退避,最后一次无退避
        # delay = base_delay * 2^(attempt-1)
        # attempt 1: 0.1 * 2^0 = 0.1s  -> 100ms
        # attempt 2: 0.1 * 2^1 = 0.2s  -> 200ms
        # attempt 3: 0.1 * 2^2 = 0.4s  -> 400ms
        # attempt 4: 最后一次,无退避 -> 0
        assert result.attempts[0].delay_ms == 100
        assert result.attempts[1].delay_ms == 200
        assert result.attempts[2].delay_ms == 400
        assert result.attempts[3].delay_ms == 0

    @pytest.mark.asyncio
    async def test_l1_timeout_detection(self):
        """L1: 超时检测 - 任务执行时间超过 timeout 被中断"""
        engine = IDMMEngine()

        async def _slow_task():
            await asyncio.sleep(1.0)
            return "should not reach"

        result = await engine.execute_with_l1_retry(
            _slow_task, max_retries=1, timeout=0.05, base_delay=0.01
        )

        assert result.success is False
        assert result.total_retries == 1
        # asyncio.wait_for 超时抛出 asyncio.TimeoutError
        assert "TimeoutError" in result.last_error or "Timeout" in result.last_error


# ===== L2 backup model 层测试 (T1.3) =====


class TestL2BackupLayer:
    """L2 backup model 层: provider 健康检查 + 自动切换"""

    @pytest.mark.asyncio
    async def test_l2_primary_success_no_switch(self):
        """L2: 主 provider 成功,不切换 backup"""
        engine = IDMMEngine()

        async def _factory(name):
            return f"result-from-{name}"

        result = await engine.execute_with_l2_fallback(
            _factory,
            primary_provider="openai",
            backup_providers=["anthropic", "gemini"],
        )

        assert result.success is True
        assert result.result == "result-from-openai"
        assert result.primary_used == "openai"
        assert result.backup_used is None
        assert result.switched is False
        assert len(result.switches) == 0

    @pytest.mark.asyncio
    async def test_l2_switch_to_backup_on_primary_failure(self):
        """L2: 主 provider 失败后自动切换 backup (验收①)"""
        engine = IDMMEngine()

        async def _factory(name):
            if name == "openai":
                raise RuntimeError("openai 不可用")
            return f"result-from-{name}"

        result = await engine.execute_with_l2_fallback(
            _factory,
            primary_provider="openai",
            backup_providers=["anthropic", "gemini"],
        )

        assert result.success is True
        assert result.result == "result-from-anthropic"
        assert result.primary_used == "openai"
        assert result.backup_used == "anthropic"
        assert result.switched is True
        assert len(result.switches) == 1
        assert result.switches[0].from_provider == "openai"
        assert result.switches[0].to_provider == "anthropic"

    @pytest.mark.asyncio
    async def test_l2_switch_logs_traceable(self):
        """L2: 切换日志可追溯 (验收②)"""
        engine = IDMMEngine()

        async def _factory(name):
            if name in ("openai", "anthropic"):
                raise RuntimeError(f"{name} 不可用")
            return f"result-from-{name}"

        result = await engine.execute_with_l2_fallback(
            _factory,
            primary_provider="openai",
            backup_providers=["anthropic", "gemini"],
        )

        assert result.success is True
        assert result.backup_used == "gemini"
        # 两轮切换: openai->anthropic, anthropic->gemini
        assert len(result.switches) == 2

        # 切换日志可通过 get_switch_logs 追溯
        logs = engine.get_switch_logs()
        assert len(logs) == 2
        assert logs[0]["from_provider"] == "openai"
        assert logs[0]["to_provider"] == "anthropic"
        assert logs[1]["from_provider"] == "anthropic"
        assert logs[1]["to_provider"] == "gemini"
        # 每条日志都有时间戳
        assert "timestamp" in logs[0]
        assert isinstance(logs[0]["timestamp"], float)
        # 日志包含失败原因
        assert "RuntimeError" in logs[0]["reason"]

    @pytest.mark.asyncio
    async def test_l2_all_providers_fail(self):
        """L2: 所有 provider 都失败时返回失败结果"""
        engine = IDMMEngine()

        async def _factory(name):
            raise RuntimeError(f"{name} 全部不可用")

        result = await engine.execute_with_l2_fallback(
            _factory,
            primary_provider="openai",
            backup_providers=["anthropic", "gemini"],
        )

        assert result.success is False
        assert result.switched is False  # 没有任何 backup 成功
        assert result.backup_used is None
        assert result.last_error is not None
        assert "RuntimeError" in result.last_error

    @pytest.mark.asyncio
    async def test_l2_check_provider_health_unregistered(self):
        """L2: 未注册的 provider 健康检查返回 False"""
        engine = IDMMEngine()
        health = await engine.check_provider_health("nonexistent-provider")
        assert health is False

    @pytest.mark.asyncio
    async def test_l2_check_provider_health_registered(self):
        """L2: 已注册且 test_connection 返回 True 的 provider 健康检查通过"""
        engine = IDMMEngine()
        # 注册一个 mock provider
        with patch("server.services.idmm.is_registered", return_value=True), \
             patch("server.services.idmm.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.test_connection = AsyncMock(return_value=True)
            mock_get.return_value = mock_provider

            health = await engine.check_provider_health("mock-provider")
            assert health is True


# ===== L3 sidecar 层测试 (T1.9) =====


class TestL3SidecarLayer:
    """L3 sidecar 层: 停滞检测 + 提示注入"""

    @pytest.mark.asyncio
    async def test_l3_detect_stagnation(self):
        """L3: 检测停滞 - 连续 N 轮无进展 (验收①)"""
        engine = IDMMEngine()
        # 构造对话: 5 轮全部无进展
        conversation = [
            {"role": "assistant", "content": "尝试1", "progress": False},
            {"role": "assistant", "content": "尝试2", "progress": False},
            {"role": "assistant", "content": "尝试3", "progress": False},
            {"role": "assistant", "content": "尝试4", "progress": False},
            {"role": "assistant", "content": "尝试5", "progress": False},
        ]

        report = await engine.check_stagnation(conversation, threshold=3)

        assert report.stagnated is True
        assert report.rounds_without_progress == 5
        assert report.threshold == 3

    @pytest.mark.asyncio
    async def test_l3_no_stagnation_with_progress(self):
        """L3: 最近有进展,不视为停滞"""
        engine = IDMMEngine()
        conversation = [
            {"role": "assistant", "content": "尝试1", "progress": False},
            {"role": "assistant", "content": "尝试2", "progress": False},
            {"role": "assistant", "content": "突破", "progress": True},
        ]

        report = await engine.check_stagnation(conversation, threshold=3)

        assert report.stagnated is False
        assert report.rounds_without_progress == 0

    @pytest.mark.asyncio
    async def test_l3_stagnation_threshold_boundary(self):
        """L3: 停滞阈值边界 - 无进展轮数等于阈值时视为停滞"""
        engine = IDMMEngine()
        conversation = [
            {"role": "assistant", "content": "尝试1", "progress": False},
            {"role": "assistant", "content": "尝试2", "progress": False},
            {"role": "assistant", "content": "尝试3", "progress": False},
        ]

        # threshold=3, rounds=3, 3>=3 视为停滞
        report = await engine.check_stagnation(conversation, threshold=3)
        assert report.stagnated is True
        assert report.rounds_without_progress == 3

        # threshold=4, rounds=3, 3<4 不视为停滞
        report2 = await engine.check_stagnation(conversation, threshold=4)
        assert report2.stagnated is False

    @pytest.mark.asyncio
    async def test_l3_sidecar_injection_recovers(self):
        """L3: sidecar 注入后 agent 恢复 (验收②)"""
        engine = IDMMEngine()
        conversation = [
            {"role": "assistant", "content": "尝试1", "progress": False},
            {"role": "assistant", "content": "尝试2", "progress": False},
            {"role": "assistant", "content": "尝试3", "progress": False},
        ]

        # 注入前: 停滞
        report_before = await engine.check_stagnation(
            conversation, threshold=3, conv_id="test-conv"
        )
        assert report_before.stagnated is True

        # 注入 sidecar 提示
        new_conversation = await engine.inject_sidecar(
            conversation, "请尝试换一个思路", conv_id="test-conv"
        )

        # 注入后: 新对话末尾有 sidecar 消息(progress=True),打破停滞
        assert len(new_conversation) == 4
        sidecar_msg = new_conversation[-1]
        assert sidecar_msg["role"] == "system"
        assert sidecar_msg["sidecar"] is True
        assert sidecar_msg["progress"] is True
        assert "[SIDECAR]" in sidecar_msg["content"]

        # 用新对话检测停滞: 应该不再停滞
        report_after = await engine.check_stagnation(
            new_conversation, threshold=3, conv_id="test-conv"
        )
        assert report_after.stagnated is False
        assert report_after.rounds_without_progress == 0

    @pytest.mark.asyncio
    async def test_l3_injection_history_recorded(self):
        """L3: sidecar 注入历史被记录,可查询"""
        engine = IDMMEngine()
        conv_id = "history-test"

        await engine.inject_sidecar([], "提示1", conv_id=conv_id)
        await engine.inject_sidecar([], "提示2", conv_id=conv_id)

        history = engine.get_injection_history(conv_id)
        assert len(history) == 2
        assert history[0] == "提示1"
        assert history[1] == "提示2"

    @pytest.mark.asyncio
    async def test_l3_sidecar_does_not_mutate_original(self):
        """L3: sidecar 注入不修改原对话列表"""
        engine = IDMMEngine()
        original = [{"role": "user", "content": "hello", "progress": True}]

        new_conv = await engine.inject_sidecar(original, "hint")
        # 原列表不变
        assert len(original) == 1
        # 新列表多了一条 sidecar
        assert len(new_conv) == 2


# ===== T1.10: LoopEngine ↔ IDMM 集成测试 =====


class TestLoopIDMMIntegration:
    """T1.10: LoopEngine 与 IDMM 集成 - 反思↔保活闭环"""

    @pytest.mark.asyncio
    async def test_feedback_to_idmm_records_progress(self):
        """反思结果反馈到 IDMM: 评分提升视为有进展"""
        from server.services.loop_engine import LoopEngine

        engine = LoopEngine()
        loop_id = 999  # 不需要真实 loop,只测试反馈逻辑

        # 第一轮: score=5,无前次,视为有进展
        fb1 = await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10")
        assert fb1["score"] == 5.0
        assert fb1["progress"] is True
        assert fb1["stagnated"] is False

        # 第二轮: score=7,提升,有进展
        fb2 = await engine.feedback_to_idmm(loop_id, 7.0, "评分: 7/10")
        assert fb2["progress"] is True
        assert fb2["stagnated"] is False

        # 第三轮: score=7,无提升,无进展
        fb3 = await engine.feedback_to_idmm(loop_id, 7.0, "评分: 7/10")
        assert fb3["progress"] is False

    @pytest.mark.asyncio
    async def test_feedback_to_idmm_detects_stagnation(self):
        """反思结果反馈到 IDMM: 连续无进展触发停滞检测"""
        from server.services.loop_engine import LoopEngine

        engine = LoopEngine()
        loop_id = 998

        # 第一轮: 无前次评分,视为有进展(progress=True)
        await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10 - first")
        # 后续 3 轮评分不变(无进展),累计 3 轮无进展触发停滞
        await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10 - second")
        await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10 - third")
        fb = await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10 - fourth")

        assert fb["stagnated"] is True
        assert fb["rounds_without_progress"] >= 3

    @pytest.mark.asyncio
    async def test_trigger_reflection_via_idmm_injects_sidecar(self):
        """IDMM 保活触发反思: 停滞时注入 sidecar 提示"""
        from server.services.loop_engine import LoopEngine

        engine = LoopEngine()
        loop_id = 997

        # 制造停滞: 第一轮有进展,后续 3 轮无进展,累计 3 轮无进展
        for _ in range(4):
            await engine.feedback_to_idmm(loop_id, 5.0, "评分: 5/10")

        # 触发反思: 应注入 sidecar
        trigger = await engine.trigger_reflection_via_idmm(loop_id, threshold=3)

        assert trigger["stagnated"] is True
        assert trigger["injected"] is True
        assert trigger["hint"] is not None
        assert "停滞" in trigger["hint"]

    @pytest.mark.asyncio
    async def test_trigger_reflection_no_stagnation_no_injection(self):
        """IDMM 保活触发反思: 无停滞时不注入 sidecar"""
        from server.services.loop_engine import LoopEngine

        engine = LoopEngine()
        loop_id = 996

        # 只有一轮反馈,无停滞
        await engine.feedback_to_idmm(loop_id, 8.0, "评分: 8/10")

        trigger = await engine.trigger_reflection_via_idmm(loop_id, threshold=3)
        assert trigger["stagnated"] is False
        assert trigger["injected"] is False
        assert trigger["hint"] is None

    @pytest.mark.asyncio
    async def test_call_llm_with_l1_retry_success(self):
        """L1 重试包装 LLM 调用: 成功场景"""
        from server.services.loop_engine import LoopEngine
        from server.providers.base import Message as ProviderMessage

        engine = LoopEngine()

        # mock provider: 首次调用即成功
        with patch("server.services.loop_engine.get_provider") as mock_get, \
             patch("server.services.loop_engine.is_registered", return_value=True):
            mock_provider = MagicMock()
            async def _fake_gen(*args, **kwargs):
                yield "llm response"
            mock_provider.generate = _fake_gen
            mock_get.return_value = mock_provider

            persona = MagicMock()
            persona.model_provider = "mock"
            persona.model_name = "mock-model"
            persona.temperature = 0.7
            persona.max_tokens = 100

            messages = [ProviderMessage(role="user", content="hello")]
            response = await engine._call_llm_with_l1_retry(
                persona, messages, max_retries=2, timeout=5.0
            )

            assert response == "llm response"

    @pytest.mark.asyncio
    async def test_call_llm_with_l1_retry_recovers_from_timeout(self):
        """L1 重试包装 LLM 调用: 超时后重试成功"""
        from server.services.loop_engine import LoopEngine
        from server.providers.base import Message as ProviderMessage

        engine = LoopEngine()
        call_count = {"n": 0}

        with patch("server.services.loop_engine.get_provider") as mock_get, \
             patch("server.services.loop_engine.is_registered", return_value=True):
            mock_provider = MagicMock()

            async def _fake_gen(*args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] < 2:
                    raise TimeoutError("LLM 超时")
                yield "recovered response"

            mock_provider.generate = _fake_gen
            mock_get.return_value = mock_provider

            persona = MagicMock()
            persona.model_provider = "mock"
            persona.model_name = "mock-model"
            persona.temperature = 0.7
            persona.max_tokens = 100

            messages = [ProviderMessage(role="user", content="hello")]
            response = await engine._call_llm_with_l1_retry(
                persona, messages, max_retries=3, timeout=5.0
            )

            assert response == "recovered response"
            assert call_count["n"] == 2  # 第一次失败,第二次成功


# ===== API 端点测试 =====


class TestIDMMAPI:
    """IDMM API 端点测试"""

    @pytest.fixture
    def client(self):
        """创建独立的 FastAPI 测试客户端(不依赖 main.py 注册)"""
        app = FastAPI()
        app.include_router(idmm_router)
        return TestClient(app)

    def test_api_module_info(self, client):
        """GET /idmm - 返回模块信息"""
        resp = client.get("/idmm")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["module"] == "idmm"
        assert "L1" in body["data"]["layers"]
        assert "L2" in body["data"]["layers"]
        assert "L3" in body["data"]["layers"]

    def test_api_l1_execute_success(self, client):
        """POST /idmm/execute - L1 首次成功"""
        resp = client.post("/idmm/execute", json={
            "task_payload": {"goal": "test"},
            "max_retries": 3,
            "base_delay": 0.01,
            "fail_first": 0,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["success"] is True
        assert body["data"]["total_retries"] == 0

    def test_api_l1_execute_with_retry(self, client):
        """POST /idmm/execute - L1 超时后重试成功"""
        resp = client.post("/idmm/execute", json={
            "task_payload": {},
            "max_retries": 3,
            "base_delay": 0.01,
            "max_delay": 0.05,
            "timeout": 5.0,
            "fail_first": 2,  # 前两次失败
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["success"] is True
        assert body["data"]["total_retries"] == 2
        assert len(body["data"]["attempts"]) == 3

    def test_api_l2_execute_fallback_switch(self, client):
        """POST /idmm/execute-fallback - L2 主 provider 失败切换 backup"""
        resp = client.post("/idmm/execute-fallback", json={
            "primary_provider": "openai",
            "backup_providers": ["anthropic"],
            "task_payload": {"goal": "test"},
            "failing_providers": ["openai"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["success"] is True
        assert body["data"]["switched"] is True
        assert body["data"]["primary_used"] == "openai"
        assert body["data"]["backup_used"] == "anthropic"
        assert len(body["data"]["switches"]) == 1

    def test_api_l2_execute_fallback_primary_success(self, client):
        """POST /idmm/execute-fallback - L2 主 provider 成功不切换"""
        resp = client.post("/idmm/execute-fallback", json={
            "primary_provider": "openai",
            "backup_providers": ["anthropic"],
            "failing_providers": [],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["switched"] is False
        assert body["data"]["backup_used"] is None

    def test_api_stagnation_detection(self, client):
        """GET /idmm/stagnation/{conv_id} - 停滞检测"""
        conversation = [
            {"role": "assistant", "content": "t1", "progress": False},
            {"role": "assistant", "content": "t2", "progress": False},
            {"role": "assistant", "content": "t3", "progress": False},
        ]
        resp = client.get("/idmm/stagnation/conv-1", params={
            "conversation": json.dumps(conversation),
            "threshold": 3,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["stagnated"] is True
        assert body["data"]["rounds_without_progress"] == 3
        assert body["data"]["conv_id"] == "conv-1"

    def test_api_stagnation_no_stagnation(self, client):
        """GET /idmm/stagnation/{conv_id} - 无停滞"""
        conversation = [
            {"role": "assistant", "content": "t1", "progress": True},
        ]
        resp = client.get("/idmm/stagnation/conv-2", params={
            "conversation": json.dumps(conversation),
            "threshold": 3,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["stagnated"] is False

    def test_api_stagnation_invalid_json(self, client):
        """GET /idmm/stagnation/{conv_id} - 无效 JSON 返回 400"""
        resp = client.get("/idmm/stagnation/conv-3", params={
            "conversation": "not-valid-json",
        })
        assert resp.status_code == 400
        body = resp.json()
        assert "Invalid conversation JSON" in body["detail"]["error"]

    def test_api_sidecar_injection(self, client):
        """POST /idmm/sidecar - sidecar 注入"""
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi", "progress": False},
        ]
        resp = client.post("/idmm/sidecar", json={
            "conversation": conversation,
            "hint": "请尝试新思路",
            "conv_id": "test-api-conv",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["injected"] is True
        assert body["data"]["hint"] == "请尝试新思路"
        # 新对话比原对话多一条 sidecar 消息
        assert len(body["data"]["conversation"]) == 3
        sidecar_msg = body["data"]["conversation"][-1]
        assert sidecar_msg["sidecar"] is True
        assert "[SIDECAR]" in sidecar_msg["content"]

    def test_api_switch_logs(self, client):
        """GET /idmm/switch-logs - 获取切换日志"""
        # 先触发一次切换
        client.post("/idmm/execute-fallback", json={
            "primary_provider": "openai",
            "backup_providers": ["anthropic"],
            "failing_providers": ["openai"],
        })
        # 查询切换日志
        resp = client.get("/idmm/switch-logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1
        assert body["data"][0]["from_provider"] == "openai"
        assert body["data"][0]["to_provider"] == "anthropic"
