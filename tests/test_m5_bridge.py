# tests/test_m5_bridge.py
import pytest
from server.cu.verifier import CUResultVerifier, VerificationResult
from server.cu.knowledge_bridge import CUKnowledgeBridge, KnowledgeCandidate
from server.cu.planner import CUTaskStep


def test_verifier_high_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.9)
    assert result.passed is True
    assert result.level == "high"

def test_verifier_medium_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.7)
    assert result.passed is True
    assert result.level == "medium"
    assert result.warning is not None

def test_verifier_low_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.4)
    assert result.passed is False
    assert result.level == "low"
    assert result.requires_confirmation is True

def test_verifier_criteria_failed():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "expected.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.9)
    assert result.passed is False

def test_bridge_action_to_knowledge():
    bridge = CUKnowledgeBridge()
    candidates = bridge.action_to_knowledge_sync(
        "cutask-001",
        [{"step_index": 0, "action_type": "browser_navigate", "result_status": "success",
          "result_data": {"url": "https://example.com/login"}},
         {"step_index": 1, "action_type": "browser_click", "result_status": "success",
          "result_data": {"nav_url": "https://example.com/dashboard"}}],
        "登录系统",
    )
    assert len(candidates) > 0
    sop = [c for c in candidates if "SOP" in c.title or "sop" in c.title.lower()]
    assert len(sop) > 0
