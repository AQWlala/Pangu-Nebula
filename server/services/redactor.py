"""敏感信息脱敏服务(Phase 8C)

基于 regex + 规则的脱敏引擎,支持:
- 邮箱 / 中国手机号 / 国际电话 / 身份证号 / 银行卡号
- API 密钥 / JWT / IPv4 / URL
- 运行时添加自定义规则(不持久化)
- detect 模式仅检测不替换

融合来源:
- NomiFun 的 nomi-redact 脱敏模块
"""

import re


# 内置脱敏规则字典
REDACTION_RULES: dict[str, dict] = {
    "email": {
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "replacement": "[EMAIL]",
        "description": "电子邮箱",
    },
    "phone_cn": {
        "pattern": r"1[3-9]\d{9}",
        "replacement": "[PHONE]",
        "description": "中国手机号",
    },
    "phone_intl": {
        "pattern": r"\+\d{1,3}[-\s]?\d{4,14}",
        "replacement": "[PHONE]",
        "description": "国际电话号码",
    },
    "id_card_cn": {
        "pattern": r"\d{17}[\dXx]",
        "replacement": "[ID_CARD]",
        "description": "中国身份证号",
    },
    "bank_card": {
        "pattern": r"\d{16,19}",
        "replacement": "[BANK_CARD]",
        "description": "银行卡号",
    },
    "api_key": {
        "pattern": r"(sk-|pk-|api_key|apikey|access_token|secret)[=:]\s*[A-Za-z0-9_\-]{20,}",
        "replacement": "[API_KEY]",
        "description": "API 密钥",
    },
    "jwt": {
        "pattern": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "replacement": "[JWT]",
        "description": "JWT 令牌",
    },
    "ipv4": {
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "replacement": "[IP]",
        "description": "IPv4 地址",
    },
    "url": {
        "pattern": r"https?://[^\s<>\"]+",
        "replacement": "[URL]",
        "description": "URL",
    },
}


class Redactor:
    """敏感信息脱敏器(regex + 规则)"""

    def __init__(self) -> None:
        # 复制一份内置规则,允许运行时通过 add_rule 扩展
        self.rules: dict[str, dict] = {k: dict(v) for k, v in REDACTION_RULES.items()}

    def list_rules(self) -> list[dict]:
        """列出所有可用规则"""
        return [
            {
                "name": name,
                "pattern": rule["pattern"],
                "replacement": rule["replacement"],
                "description": rule.get("description", ""),
            }
            for name, rule in self.rules.items()
        ]

    def add_rule(
        self,
        name: str,
        pattern: str,
        replacement: str = "***",
        description: str = "",
    ) -> dict:
        """添加自定义规则(运行时,不持久化)

        如果 name 已存在则覆盖
        """
        self.rules[name] = {
            "pattern": pattern,
            "replacement": replacement,
            "description": description,
        }
        return {
            "name": name,
            "pattern": pattern,
            "replacement": replacement,
            "description": description,
        }

    def _resolve_rules(self, rules: list[str]) -> list[tuple[str, dict]]:
        """根据传入的 rules 名单筛选要使用的规则

        - rules 为空: 使用全部规则
        - rules 有值: 仅使用指定的规则(忽略不存在的规则名)
        """
        if not rules:
            return list(self.rules.items())
        return [(name, self.rules[name]) for name in rules if name in self.rules]

    def redact(
        self,
        text: str,
        rules: list[str] | None = None,
        replacement: str = "***",
    ) -> dict:
        """脱敏处理

        - rules 为空: 使用所有规则
        - rules 有值: 仅使用指定规则
        - replacement 不为 "***": 覆盖所有规则的 replacement
        - 返回 {"redacted_text": ..., "matches": [...], "total_redactions": N}
        """
        if rules is None:
            rules = []
        use_rules = self._resolve_rules(rules)
        # 是否覆盖 replacement
        override = replacement != "***"

        redacted_text = text
        matches: list[dict] = []
        total = 0

        for name, rule in use_rules:
            pattern = rule["pattern"]
            repl = replacement if override else rule["replacement"]
            compiled = re.compile(pattern)
            found = compiled.findall(text)
            if not found:
                continue
            # 取样本(最多5个),去重保留顺序
            samples: list[str] = []
            seen: set[str] = set()
            for item in found:
                s = item if isinstance(item, str) else str(item)
                if s not in seen:
                    seen.add(s)
                    samples.append(s)
                    if len(samples) >= 5:
                        break
            count = len(found)
            total += count
            matches.append({"rule": name, "count": count, "samples": samples})
            # 对当前已处理的文本执行替换
            redacted_text = compiled.sub(repl, redacted_text)

        return {
            "redacted_text": redacted_text,
            "matches": matches,
            "total_redactions": total,
        }

    def detect(self, text: str, rules: list[str] | None = None) -> dict:
        """检测但不脱敏

        - 返回 {"matches": [{"rule": ..., "count": N, "samples": [...]}], "total_matches": N}
        - samples 为原始匹配内容(便于人工确认)
        """
        if rules is None:
            rules = []
        use_rules = self._resolve_rules(rules)

        matches: list[dict] = []
        total = 0

        for name, rule in use_rules:
            compiled = re.compile(rule["pattern"])
            found = compiled.findall(text)
            if not found:
                continue
            samples: list[str] = []
            seen: set[str] = set()
            for item in found:
                s = item if isinstance(item, str) else str(item)
                if s not in seen:
                    seen.add(s)
                    samples.append(s)
                    if len(samples) >= 5:
                        break
            count = len(found)
            total += count
            matches.append({"rule": name, "count": count, "samples": samples})

        return {"matches": matches, "total_matches": total}


# 模块级单例
redactor = Redactor()
