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
import logging
import time
from typing import Any

from ..db.engine import async_session
from ..tools.registry import get_tool, is_registered
from .audit_logger import audit_logger
from .injection_guard import injection_guard


logger = logging.getLogger(__name__)


# 工具所需额外权限映射 (基础权限 tools_enabled 对所有工具生效,此处只列额外项)
# key=tool_name, value=所需 persona 能力字段名
_TOOL_EXTRA_PERMS: dict[str, list[str]] = {
    # Phase 2: execute_command 需要 terminal_allowed
    "execute_command": ["terminal_allowed"],
    # Phase 5: browser_* 需要 browser_use_enabled
    "browser_navigate": ["browser_use_enabled"],
    "browser_screenshot": ["browser_use_enabled"],
    "browser_click": ["browser_use_enabled"],
    "browser_type": ["browser_use_enabled"],
    # v2.2.1 F7: computer_* 改用独立权限字段 computer_use_enabled
    # (与 browser_* 解耦,默认关闭,安全优先)
    "computer_screenshot": ["computer_use_enabled"],
    "computer_click": ["computer_use_enabled"],
    "computer_type_text": ["computer_use_enabled"],
    "computer_get_a11y_tree": ["computer_use_enabled"],
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

# v2.2.1 S5: 注入检查递归深度上限 (防止栈溢出)
_INJ_MAX_DEPTH = 10


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

        对所有字符串类型参数(包括 dict/list 嵌套结构)按工具对应的 context 检测。
        返回 (safe, threat_msg, threats)。safe=True 时其余字段为空。
        检测到任何威胁即拒绝 (安全优先)。

        v2.2.1 S5: 递归遍历 dict/list 中的所有字符串值,防止嵌套注入 payload。
        递归深度限制为 _INJ_MAX_DEPTH (10) 层,防止栈溢出。
        """
        context = _TOOL_GUARD_CONTEXT.get(name, "general")
        threats_all: list[dict] = []

        def _check_value(value: Any, path: str, depth: int) -> None:
            """递归检查值,将威胁追加到 threats_all"""
            if depth > _INJ_MAX_DEPTH:
                return
            if isinstance(value, str):
                result = injection_guard.check(value, context=context)
                if not result["safe"]:
                    for t in result["threats"]:
                        t["arg"] = path or "root"
                    threats_all.extend(result["threats"])
            elif isinstance(value, dict):
                for k, v in value.items():
                    new_path = f"{path}.{k}" if path else k
                    _check_value(v, new_path, depth + 1)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    new_path = f"{path}[{i}]"
                    _check_value(item, new_path, depth + 1)

        for key, val in arguments.items():
            _check_value(val, key, 0)

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

            # v2.2.1 F5: 参数白名单过滤 — 防止 LLM 注入 allow_network 等敏感参数
            # 仅当工具显式声明 allowed_kwargs (非空集合) 时才过滤,未声明的工具透传 (向后兼容)
            if hasattr(tool, "allowed_kwargs") and tool.allowed_kwargs:
                filtered_args = {
                    k: v for k, v in arguments.items() if k in tool.allowed_kwargs
                }
            else:
                filtered_args = arguments
            # 如果有被过滤的参数,记录审计日志
            filtered_keys = set(arguments.keys()) - set(filtered_args.keys())
            if filtered_keys:
                logger.warning(
                    "filtered disallowed kwargs for tool %s: %s",
                    name,
                    sorted(filtered_keys),
                )

            # v2.2.1 F1: 注入 persona 供 file_read/file_write 的 PathGuard 使用
            # persona 不在 allowed_kwargs 中, 但作为内部注入参数通过 **kwargs 传递,
            # 不会与 F5 的 LLM 参数过滤冲突 (filtered_args 已先于 persona 处理)
            result = await tool.execute(**filtered_args, persona=persona)
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
        except Exception as audit_exc:
            # v2.2.1 S6: 审计失败不再静默 — 安全事件必须有日志可查
            # 但审计失败仍不阻断工具执行流程 (主流程已先返回)
            logger.error(
                "audit log failed for tool %s: %s",
                name,
                audit_exc,
                exc_info=True,
            )


# 模块级单例
tool_executor = ToolExecutor()
