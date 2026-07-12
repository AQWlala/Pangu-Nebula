"""DLP (Data Loss Prevention) 引擎 — redactor 的扩展

从简单的脱敏升级为完整的 DLP 引擎:
1. 数据分类标签 (公开/内部/机密/绝密)
2. 自动识别敏感数据 (身份证/手机号/银行卡/邮箱/IP)
3. 可配置脱敏策略 (保留前几位/全替换/哈希)
4. 审计日志 (记录所有脱敏操作)
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum
from typing import Optional


class DataClassification(str, Enum):
    """数据分级"""

    PUBLIC = "public"            # 公开
    INTERNAL = "internal"        # 内部
    CONFIDENTIAL = "confidential"  # 机密
    TOP_SECRET = "top_secret"      # 绝密


class SensitiveType(str, Enum):
    """敏感数据类型"""

    ID_CARD = "id_card"          # 身份证号
    PHONE = "phone"              # 手机号
    BANK_CARD = "bank_card"      # 银行卡号
    EMAIL = "email"              # 邮箱
    IP_ADDRESS = "ip_address"    # IP 地址
    API_KEY = "api_key"          # API Key
    PASSWORD = "password"        # 密码


# 分类级别排序 (低 -> 高)，用于 classify 取最高级
_CLASSIFICATION_ORDER = [
    DataClassification.PUBLIC,
    DataClassification.INTERNAL,
    DataClassification.CONFIDENTIAL,
    DataClassification.TOP_SECRET,
]


class DLPRule:
    """DLP 规则"""

    def __init__(
        self,
        sensitive_type: SensitiveType,
        pattern: str,
        mask_strategy: str = "partial",
        classification: DataClassification = DataClassification.CONFIDENTIAL,
    ) -> None:
        self.sensitive_type = sensitive_type
        self.pattern = re.compile(pattern)
        self.mask_strategy = mask_strategy  # partial / full / hash
        self.classification = classification


class DLPEngine:
    """DLP 引擎"""

    # 默认规则
    DEFAULT_RULES: list[DLPRule] = [
        DLPRule(
            SensitiveType.ID_CARD,
            r"\d{17}[\dXx]",
            "partial",
            DataClassification.CONFIDENTIAL,
        ),
        DLPRule(
            SensitiveType.PHONE,
            r"1[3-9]\d{9}",
            "partial",
            DataClassification.INTERNAL,
        ),
        DLPRule(
            SensitiveType.BANK_CARD,
            r"\d{16,19}",
            "full",
            DataClassification.CONFIDENTIAL,
        ),
        DLPRule(
            SensitiveType.EMAIL,
            r"[\w.-]+@[\w.-]+\.\w+",
            "partial",
            DataClassification.INTERNAL,
        ),
        DLPRule(
            SensitiveType.IP_ADDRESS,
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
            "full",
            DataClassification.INTERNAL,
        ),
        DLPRule(
            SensitiveType.API_KEY,
            r"(?:sk|pk|api[_-]?key)[=_][\w-]{20,}",
            "full",
            DataClassification.TOP_SECRET,
        ),
        DLPRule(
            SensitiveType.PASSWORD,
            r"(?:password|passwd|pwd)[=:][\S]+",
            "full",
            DataClassification.TOP_SECRET,
        ),
    ]

    def __init__(self, rules: Optional[list[DLPRule]] = None) -> None:
        self._rules: list[DLPRule] = rules if rules is not None else list(self.DEFAULT_RULES)
        self._audit_log: list[dict] = []

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan(self, text: str) -> list[dict]:
        """扫描文本中的敏感数据

        返回 [{type, match, position, classification}, ...]
        position 为 (start, end)
        """
        findings: list[dict] = []
        for rule in self._rules:
            for m in rule.pattern.finditer(text):
                findings.append({
                    "type": rule.sensitive_type.value,
                    "match": m.group(0),
                    "position": [m.start(), m.end()],
                    "classification": rule.classification.value,
                })
        return findings

    # ------------------------------------------------------------------
    # 脱敏
    # ------------------------------------------------------------------

    def _apply_strategy(self, match_text: str, strategy: str) -> str:
        """根据策略对单个匹配项脱敏"""
        if strategy == "full":
            return "*" * len(match_text)
        if strategy == "hash":
            return hashlib.sha256(match_text.encode("utf-8")).hexdigest()[:16]
        # partial: 保留前几位，后面用 * 替换
        if len(match_text) <= 2:
            return "*" * len(match_text)
        keep = min(3, len(match_text) // 3)
        return match_text[:keep] + "*" * (len(match_text) - keep)

    def mask(self, text: str, rules: Optional[list[DLPRule]] = None) -> str:
        """脱敏处理

        - rules 为 None: 使用全部规则
        - rules 有值: 仅使用指定规则
        - 根据 mask_strategy 处理:
            partial: 保留前几位，后面用 * 替换
            full:    全部用 * 替换
            hash:    用 SHA256 hash 替换
        - 同时记录审计日志
        """
        use_rules = rules if rules is not None else self._rules

        masked_text = text
        total_redactions = 0
        affected_types: list[str] = []

        # 从后向前替换，避免位置偏移
        replacements: list[tuple[int, int, str, DLPRule]] = []
        for rule in use_rules:
            for m in rule.pattern.finditer(text):
                replacements.append((m.start(), m.end(), m.group(0), rule))
        # 按开始位置降序
        replacements.sort(key=lambda x: x[0], reverse=True)

        for start, end, original, rule in replacements:
            replacement = self._apply_strategy(original, rule.mask_strategy)
            masked_text = masked_text[:start] + replacement + masked_text[end:]
            total_redactions += 1
            if rule.sensitive_type.value not in affected_types:
                affected_types.append(rule.sensitive_type.value)

        # 审计日志
        self._audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "mask",
            "input_length": len(text),
            "output_length": len(masked_text),
            "total_redactions": total_redactions,
            "affected_types": affected_types,
        })
        return masked_text

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------

    def classify(self, text: str) -> DataClassification:
        """分类文档 (返回最高敏感级别)"""
        findings = self.scan(text)
        if not findings:
            return DataClassification.PUBLIC
        # 找到所有命中的分级，返回最高级
        levels = {f["classification"] for f in findings}
        for level in reversed(_CLASSIFICATION_ORDER):
            if level.value in levels:
                return level
        return DataClassification.PUBLIC

    # ------------------------------------------------------------------
    # 审计日志
    # ------------------------------------------------------------------

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """获取脱敏审计日志 (按时间倒序，最多 limit 条)"""
        return list(reversed(self._audit_log))[:limit]

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------

    def add_rule(self, rule: DLPRule) -> None:
        """添加自定义规则"""
        self._rules.append(rule)

    def get_status(self) -> dict:
        """获取 DLP 引擎状态"""
        return {
            "rules_count": len(self._rules),
            "rule_types": [r.sensitive_type.value for r in self._rules],
            "audit_log_count": len(self._audit_log),
            "classifications": [c.value for c in _CLASSIFICATION_ORDER],
        }


# 模块级单例
dlp_engine = DLPEngine()
