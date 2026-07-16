# server/cu/verifier.py
"""CU 结果验证器"""
from __future__ import annotations
from dataclasses import dataclass
from server.cu.planner import CUTaskStep
from server.config_kb_cu import CUConfig


@dataclass
class VerificationResult:
    passed: bool
    level: str
    confidence: float
    warning: str | None = None
    requires_confirmation: bool = False
    criteria_met: bool = True


class CUResultVerifier:
    # 保留为向后兼容回退值；实际运行时从 CUConfig 读取
    CONFIDENCE_HIGH = 0.85
    CONFIDENCE_LOW = 0.6

    def __init__(self, config: CUConfig | None = None):
        self._config = config if config is not None else CUConfig()

    def verify_step_sync(self, step: CUTaskStep, actual_url: str = "",
                         confidence: float = 0.0) -> VerificationResult:
        if not self._check_criteria(step.success_criteria, actual_url):
            return VerificationResult(False, "low", confidence, criteria_met=False, requires_confirmation=True)

        if confidence >= self._config.confidence_high:
            return VerificationResult(True, "high", confidence)
        elif confidence >= self._config.confidence_low:
            return VerificationResult(True, "medium", confidence, warning="置信度中等，建议人工复核")
        else:
            return VerificationResult(False, "low", confidence, requires_confirmation=True)

    def _check_criteria(self, criteria: dict, actual_url: str) -> bool:
        if "url_contains" in criteria:
            return criteria["url_contains"] in actual_url
        return True
