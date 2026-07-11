"""注入防护服务 (Phase 8A)

实现多种注入攻击检测与输入清洗:
- Prompt 注入: 检测试图绕过/重置系统提示词的模式
- 代码注入: SQL / Shell / Python 危险模式
- URL 注入: javascript: / data: 等危险协议, 路径遍历
- 通用检测: 综合所有模式

融合来源:
- Nebula 的安全模块设计
- NomiFun 的输入校验模式
"""

import re


# ===== Prompt 注入模式 =====
# 试图覆盖/绕过/泄露系统提示词的模式
PROMPT_INJECTION_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern, threat_type, severity)
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "prompt_injection_ignore", "high"),
    (r"you\s+are\s+(now\s+)?(a|an)\s+(different|new)", "prompt_injection_role_override", "high"),
    (r"system\s+prompt", "prompt_injection_system_leak", "high"),
    (r"forget\s+(everything|all)", "prompt_injection_forget", "high"),
    (r"reveal\s+(your|the)\s+(system\s+)?prompt", "prompt_injection_reveal_prompt", "high"),
    (r"show\s+(me\s+)?(your|the)\s+(system\s+)?prompt", "prompt_injection_show_prompt", "high"),
    (r"disregard\s+(all\s+)?(previous|prior)\s+(instructions|messages)", "prompt_injection_disregard", "high"),
    (r"new\s+instructions?\s*:", "prompt_injection_new_instructions", "medium"),
    (r"override\s+(your|the)\s+(system|instructions)", "prompt_injection_override", "high"),
    (r"you\s+are\s+(now\s+)?(in\s+)?(developer|admin|root)\s+mode", "prompt_injection_dev_mode", "high"),
    (r"(jailbreak|DAN)\s+mode", "prompt_injection_jailbreak", "high"),
    (r"act\s+as\s+(if\s+)?(you\s+are\s+)?(a|an)?\s*(different|new|unrestricted)", "prompt_injection_act_as", "medium"),
    (r"do\s+not\s+follow\s+(your|the)\s+rules", "prompt_injection_break_rules", "high"),
    (r"ignore\s+(your|the)\s+(rules|guidelines|restrictions)", "prompt_injection_ignore_rules", "high"),
    (r"pretend\s+(that\s+)?you\s+(are|can)", "prompt_injection_pretend", "medium"),
    (r"what\s+(is|are)\s+your\s+(instructions|rules|guidelines)", "prompt_injection_probe_instructions", "medium"),
    (r"repeat\s+(the\s+)?(above|previous|system)\s+(text|prompt|instructions)", "prompt_injection_repeat", "medium"),
]

# ===== 代码注入模式 =====
CODE_INJECTION_PATTERNS: list[tuple[str, str, str]] = [
    # SQL 注入
    (r"\bDROP\s+TABLE\b", "sql_drop_table", "high"),
    (r"\bDELETE\s+FROM\b", "sql_delete", "high"),
    (r"\bUNION\s+SELECT\b", "sql_union", "high"),
    (r"--\s*$", "sql_comment", "medium"),
    (r";\s*DROP\b", "sql_drop_semicolon", "high"),
    (r"\bINSERT\s+INTO\b", "sql_insert", "medium"),
    (r"\bUPDATE\s+\w+\s+SET\b", "sql_update", "medium"),
    (r"'\s*OR\s*'?\d+'?\s*=\s*'?\d+", "sql_tautology", "high"),
    (r"\bEXEC(UTE)?\s*\(", "sql_exec", "high"),
    (r"\bTRUNCATE\s+TABLE\b", "sql_truncate", "high"),

    # Shell 注入
    (r";\s*rm\s+", "shell_rm", "high"),
    (r"&&\s*rm\b", "shell_rm_and", "high"),
    (r"\|\s*sh\b", "shell_pipe_sh", "high"),
    (r"\|\s*bash\b", "shell_pipe_bash", "high"),
    (r"\$\(", "shell_command_substitution", "high"),
    (r"`[^`]+`", "shell_backtick", "high"),
    (r"\b(curl|wget)\s+", "shell_network_tool", "medium"),
    (r";\s*(cat|ls|pwd|whoami|id)\s*", "shell_recon", "medium"),

    # Python 注入
    (r"__import__\s*\(", "python_import", "high"),
    (r"\bexec\s*\(", "python_exec", "high"),
    (r"\beval\s*\(", "python_eval", "high"),
    (r"\bos\.system\s*\(", "python_os_system", "high"),
    (r"\bsubprocess\b", "python_subprocess", "high"),
    (r"\bos\.popen\s*\(", "python_os_popen", "high"),
    (r"__\w+__\s*\(", "python_dunder_call", "medium"),
    (r"\bcompile\s*\(", "python_compile", "medium"),
    (r"\bopen\s*\([^)]*['\"]w", "python_open_write", "medium"),
]

# ===== URL 注入模式 =====
URL_INJECTION_PATTERNS: list[tuple[str, str, str]] = [
    (r"javascript:", "url_javascript_protocol", "high"),
    (r"data:text/html", "url_data_html", "high"),
    (r"vbscript:", "url_vbscript_protocol", "high"),
    (r"\.\./", "url_path_traversal", "high"),
    (r"\.\.\\", "url_path_traversal_backslash", "high"),
    (r"%2e%2e%2f", "url_path_traversal_encoded", "high"),
    (r"%2e%2e/", "url_path_traversal_partial_encoded", "high"),
    (r"\.\.%2f", "url_path_traversal_partial_encoded2", "high"),
    (r"file://", "url_file_protocol", "high"),
    (r"\bonclick\s*=", "url_xss_onclick", "high"),
    (r"\bonload\s*=", "url_xss_onload", "high"),
    (r"\bonerror\s*=", "url_xss_onerror", "high"),
    (r"<script", "url_xss_script", "high"),
    (r"<iframe", "url_xss_iframe", "high"),
]

# 通用检测使用的所有模式集合
GENERAL_INJECTION_PATTERNS: list[tuple[str, str, str]] = (
    PROMPT_INJECTION_PATTERNS + CODE_INJECTION_PATTERNS + URL_INJECTION_PATTERNS
)


class InjectionGuard:
    """注入防护:检测 + 清洗"""

    def _detect(
        self, text: str, patterns: list[tuple[str, str, str]]
    ) -> list[dict]:
        """检测文本中匹配的注入模式

        返回 [{"type": "...", "pattern": "...", "severity": "..."}]
        """
        threats: list[dict] = []
        if not text:
            return threats
        for pattern, threat_type, severity in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                threats.append({
                    "type": threat_type,
                    "pattern": pattern,
                    "severity": severity,
                    "matched": match.group(0),
                })
        return threats

    def check(self, text: str, context: str = "general") -> dict:
        """检测注入

        context:
        - "prompt": 检测 Prompt 注入模式
        - "code": 检测代码注入(SQL/Shell/Python)
        - "url": 检测 URL 注入
        - "general": 通用检测(所有模式)

        返回 {"safe": bool, "threats": [...], "cleaned_text": "..."}
        """
        if text is None:
            text = ""
        context = (context or "general").lower()

        if context == "prompt":
            patterns = PROMPT_INJECTION_PATTERNS
        elif context == "code":
            patterns = CODE_INJECTION_PATTERNS
        elif context == "url":
            patterns = URL_INJECTION_PATTERNS
        else:  # general
            patterns = GENERAL_INJECTION_PATTERNS

        threats = self._detect(text, patterns)
        cleaned_text = self.clean(text) if threats else text

        return {
            "safe": len(threats) == 0,
            "threats": threats,
            "cleaned_text": cleaned_text,
            "context": context,
        }

    def clean(self, text: str) -> str:
        """清洗输入,移除所有危险模式

        将所有匹配的危险模式替换为空字符串
        """
        if not text:
            return text

        cleaned = text
        all_patterns = GENERAL_INJECTION_PATTERNS
        for pattern, _, _ in all_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # 额外清理:移除连续空格(替换产生的)
        cleaned = re.sub(r"  +", " ", cleaned)
        return cleaned


# 模块级单例
injection_guard = InjectionGuard()
