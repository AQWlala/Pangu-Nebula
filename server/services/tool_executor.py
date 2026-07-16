"""v2.2.0 工具执行器 (Phase 1)

统一接管工具调用的权限检查、注入防护、执行与审计记录。

职责链:
    1. 注册检查 — 工具是否已注册
    2. 权限检查 — persona 的能力开关 (tools_enabled / terminal_allowed / browser_use_enabled)
    3. 注入防护 — InjectionGuard 按工具类型选择 context 检测参数
    4. 执行     — 调用 BaseTool.execute(**arguments)
    5. 审计     — AuditLogger 记录每次调用 (独立 session, 不污染调用方事务)

融合来源:
- docs/v2.2.0-architecture-plan.md Phase 1 设计
- server/services/injection_guard.py (已存在)
- server/services/audit_logger.py (已存在)
"""

from __future__ import annotations

import json
import time
from typing import Any

from ..db.engine import async_session
from ..tools.registry import get_tool, is_registered
from .audit_logger import audit_logger
from .injection_guard import injection_guard


# 工具所需额外权限映射 (基础权限 tools_enabled 对所有工具生效,此处只列额外项)
# key=tool_name, value=所需 persona 能力字段名
_TOOL_EXTRA_PERMS: dict[str, list[str]] = {
    # Phase 2: execute_command 需要 terminal_allowed
    "execute_command": ["terminal_allowed"],
    # Phase 5: browser_* / computer_* 需要 browser_use_enabled
    "browser_navigate": ["browser_use_enabled"],
    "browser_screenshot": ["browser_use_enabled"],
    "browser_click": ["browser_use_enabled"],
    "browser_type": ["browser_use_enabled"],
    "computer_screenshot": ["browser_use_enabled"],
    "computer_click": ["browser_use_enabled"],
    "computer_type_text": ["browser_use_enabled"],
    "computer_get_a11y_tree": ["browser_use_enabled"],
}

# 工具对应的 InjectionGuard 检测 context
# 默认 "general"; 命令/代码工具用 "code"; 文件工具用 "url"(路径遍历)
_TOOL_GUARD_CONTEXT: dict[str, str] = {
    "web_search": "general",
    "file_read": "url",
    "file_write": "url",
    "execute_command": "code",
    "execute_code": "code",
}

# 审计日志输入摘要最大长度
_SUMMARY_MAX = 500


class ToolExecutor:
    """工具执行器:权限 + 注入防护 + 执行 + 审计"""

    def _check_permissions(self, name: str, persona: Any) -> tuple[bool, str]:
        """权限检查

        返回 (allowed, deny_reason)。allowed=True 时 deny_reason 为空。
        """
        # 基础开关: 所有工具都需要 tools_enabled
        if not bool(getattr(persona, "tools_enabled", False)):
            return False, "该角色未启用工具调用 (tools_enabled=False)"

        # 额外权限
        for perm_field in _TOOL_EXTRA_PERMS.get(name, []):
            if not bool(getattr(persona, perm_field, False)):
                return False, f"该角色未授权所需权限 ({perm_field}=False)"

        return True, ""

    def _check_injection(self, name: str, arguments: dict) -> tuple[bool, str, list[dict]]:
        """注入防护检查

        对所有字符串类型参数按工具对应的 context 检测。
        返回 (safe, threat_msg, threats)。safe=True 时其余字段为空。
        检测到任何威胁即拒绝 (安全优先)。
        """
        context = _TOOL_GUARD_CONTEXT.get(name, "general")
        threats_all: list[dict] = []

        for key, val in arguments.items():
            if not isinstance(val, str):
                continue
            result = injection_guard.check(val, context=context)
            if not result["safe"]:
                for t in result["threats"]:
                    t["arg"] = key
                threats_all.extend(result["threats"])

        if threats_all:
            first = threats_all[0]
            msg = f"{first.get('type', 'unknown')} (arg={first.get('arg', '?')}, severity={first.get('severity', '?')})"
            return False, msg, threats_all

        return True, "", []

    async def execute(self, name: str, arguments: dict, persona: Any) -> dict:
        """执行工具调用

        Args:
            name: 工具名
            arguments: 工具参数 (已从 JSON 解析)
            persona: 角色对象 (需有 tools_enabled/terminal_allowed 等字段)

        Returns:
            {"success": bool, "output": str, "error": str, "duration_ms": int}
        """
        start = time.time()

        # 1. 注册检查
        if not is_registered(name):
            return {
                "success": False,
                "output": "",
                "error": f"未知工具: {name}",
                "duration_ms": 0,
            }

        # 2. 权限检查
        allowed, deny_reason = self._check_permissions(name, persona)
        if not allowed:
            await self._audit(
                name, persona, arguments, "", False, 0,
                {"blocked_by": "permission", "deny_reason": deny_reason},
            )
            return {"success": False, "output": "", "error": deny_reason, "duration_ms": 0}

        # 3. 注入防护检查
        safe, threat_msg, threats = self._check_injection(name, arguments)
        if not safe:
            await self._audit(
                name, persona, arguments, "", False, 0,
                {"blocked_by": "injection_guard", "threats": threats},
            )
            return {
                "success": False,
                "output": "",
                "error": f"InjectionGuard 拦截: {threat_msg}",
                "duration_ms": 0,
            }

        # 4. 执行
        try:
            tool = get_tool(name)
            result = await tool.execute(**arguments)
            duration_ms = int((time.time() - start) * 1000)
            output = result.output if result.success else (result.error or result.output)

            # 5. 审计记录
            await self._audit(name, persona, arguments, output, result.success, duration_ms, {})

            return {
                "success": result.success,
                "output": output,
                "error": result.error,
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            await self._audit(
                name, persona, arguments, str(exc), False, duration_ms,
                {"exception": type(exc).__name__},
            )
            return {
                "success": False,
                "output": "",
                "error": f"工具执行异常: {exc}",
                "duration_ms": duration_ms,
            }

    async def _audit(
        self,
        name: str,
        persona: Any,
        arguments: dict,
        output: str,
        success: bool,
        duration_ms: int,
        details: dict,
    ) -> None:
        """记录审计日志 (独立 session, 审计失败不阻断主流程)"""
        try:
            persona_id = getattr(persona, "id", None)
            try:
                input_summary = json.dumps(arguments, ensure_ascii=False)[:_SUMMARY_MAX]
            except (TypeError, ValueError):
                input_summary = str(arguments)[:_SUMMARY_MAX]
            output_summary = (output or "")[:_SUMMARY_MAX]
            all_details = {"tool": name, **details}
            if arguments:
                all_details["arguments"] = arguments

            async with async_session() as session:
                await audit_logger.log(
                    session,
                    action="tool_call",
                    persona_id=persona_id if persona_id else None,
                    resource=name,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    duration_ms=duration_ms,
                    success=success,
                    details=all_details,
                )
        except Exception:
            # 审计日志失败不应阻断工具执行流程
            pass


# 模块级单例
tool_executor = ToolExecutor()
