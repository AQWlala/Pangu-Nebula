# tests/test_cu_config_dedup.py
"""A6: planner/verifier 配置去重测试。

验证 CUTaskPlanner / CUResultVerifier 从 CUConfig 读取阈值，
同时保持向后兼容（不传 config 时行为与历史一致）。
"""
import pytest

from server.config_kb_cu import CUConfig
from server.cu.planner import CUTaskPlanner, CUTaskStep
from server.cu.verifier import CUResultVerifier


def _nav_step(**overrides):
    """构造一个 browser_navigate 测试步骤定义。"""
    step = {
        "action_type": "browser_navigate",
        "action_payload": {"url": "https://example.com"},
        "success_criteria": {"url_contains": "example.com"},
    }
    step.update(overrides)
    return step


def test_planner_custom_config_overrides_timeout():
    """Test 1: 自定义 CUConfig 覆盖 planner 默认/最大超时。"""
    config = CUConfig(max_step_timeout_ms=60000, default_step_timeout_ms=5000)
    planner = CUTaskPlanner(config=config)

    # 1) 未指定 timeout_ms 时使用 config.default_step_timeout_ms
    plan = planner.plan_manual("访问 example.com", [_nav_step()])
    assert plan.steps[0].timeout_ms == 5000

    # 2) 60s 超时在旧硬编码阈值（10000）下会被拒，自定义后应放行
    plan2 = planner.plan_manual("长任务", [_nav_step(timeout_ms=60000)])
    assert plan2.steps[0].timeout_ms == 60000

    # 3) 超过新最大值仍应拒绝
    with pytest.raises(ValueError, match="timeout"):
        planner.plan_manual("超时任务", [_nav_step(timeout_ms=70000)])


def test_verifier_custom_config_overrides_thresholds():
    """Test 2: 自定义 CUConfig 覆盖 verifier 置信度阈值。"""
    # 默认 high=0.85, low=0.6；自定义 high=0.9, low=0.7
    config = CUConfig(confidence_high=0.9, confidence_low=0.7)
    verifier = CUResultVerifier(config=config)
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})

    # 0.85 在默认阈值下是 high，在新阈值（high=0.9）下应为 medium
    result = verifier.verify_step_sync(step, "https://example.com", 0.85)
    assert result.passed is True
    assert result.level == "medium"
    assert result.warning is not None

    # 0.95 在新阈值下为 high
    result_high = verifier.verify_step_sync(step, "https://example.com", 0.95)
    assert result_high.passed is True
    assert result_high.level == "high"

    # 0.65 在默认阈值下是 medium，在新阈值（low=0.7）下应为 low（失败）
    result_low = verifier.verify_step_sync(step, "https://example.com", 0.65)
    assert result_low.passed is False
    assert result_low.level == "low"
    assert result_low.requires_confirmation is True


def test_default_config_backward_compat():
    """Test 3: 默认 CUConfig 产生与之前一致的行为（向后兼容）。"""
    # ---- planner ----
    planner_default = CUTaskPlanner()
    # 类常量作为向后兼容回退值仍保留
    assert CUTaskPlanner.MAX_TIMEOUT_MS == 10000
    assert CUTaskPlanner.DEFAULT_TIMEOUT_MS == 3000

    plan = planner_default.plan_manual("test", [_nav_step()])
    assert plan.steps[0].timeout_ms == 3000  # 历史默认值

    # 历史最大值约束仍然生效（30000 > 10000）
    with pytest.raises(ValueError, match="timeout"):
        planner_default.plan_manual("test", [_nav_step(timeout_ms=30000)])

    # ---- verifier ----
    verifier_default = CUResultVerifier()
    # 类常量作为向后兼容回退值仍保留
    assert CUResultVerifier.CONFIDENCE_HIGH == 0.85
    assert CUResultVerifier.CONFIDENCE_LOW == 0.6

    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})

    # high 阈值 0.85
    assert verifier_default.verify_step_sync(step, "https://example.com", 0.9).level == "high"
    # medium 区间 [0.6, 0.85)
    medium = verifier_default.verify_step_sync(step, "https://example.com", 0.7)
    assert medium.level == "medium"
    assert medium.passed is True
    # low < 0.6
    low = verifier_default.verify_step_sync(step, "https://example.com", 0.4)
    assert low.level == "low"
    assert low.passed is False

    # 不传 config 等价于传默认 config（行为一致）
    planner_with_default = CUTaskPlanner(config=CUConfig())
    plan2 = planner_with_default.plan_manual("test", [_nav_step()])
    assert plan2.steps[0].timeout_ms == plan.steps[0].timeout_ms

    verifier_with_default = CUResultVerifier(config=CUConfig())
    assert (verifier_with_default.verify_step_sync(step, "https://example.com", 0.7).level
            == medium.level)
