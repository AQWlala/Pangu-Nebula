"""v2.2.0 代码执行工具 (Phase 3)

复用 PythonSandbox 在隔离环境中执行 Python 代码。

职责链 (与 ToolExecutor 配合):
    ToolExecutor 权限检查 (tools_enabled)
      → ToolExecutor InjectionGuard (code context)
        → ExecuteCodeTool.execute
          → PythonSandbox.execute (子进程隔离 + 网络/内存/超时限制)
            → 返回 stdout + 结构化 output

网络权限说明:
    默认 allow_network=False (安全优先)。
    persona.sandbox_allow_network 的联动在 ToolExecutor 权限层检查,
    若需将网络权限传入沙箱,可通过 kwargs["allow_network"] 传递
    (未来 Phase 6 集成时由 chat_service 注入)。
"""

from __future__ import annotations

from ..services.sandbox_engine import PythonSandbox
from .registry import BaseTool, ToolResult, register_tool


@register_tool("execute_code")
class ExecuteCodeTool(BaseTool):
    name = "execute_code"
    description = (
        "Execute Python code in a sandboxed environment and return stdout, "
        "structured output and stderr. Network is disabled by default. "
        "Subject to timeout and memory limits."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 60, max 180)",
                "default": 60,
            },
        },
        "required": ["code"],
    }
    # v2.2.1 F5: 不含 allow_network — 网络权限由 persona.sandbox_allow_network 在
    # ToolExecutor 权限层决定,LLM 不应通过 kwargs 注入。
    allowed_kwargs: set[str] = {"code", "timeout"}

    _MAX_TIMEOUT = 180
    _MEMORY_LIMIT_MB = 256

    async def execute(
        self, code: str, timeout: int = 60, **kwargs
    ) -> ToolResult:
        # 超时上限保护
        timeout = max(1, min(int(timeout), self._MAX_TIMEOUT))
        # 网络权限 (默认禁用,可由调用方通过 kwargs 注入)
        allow_network = bool(kwargs.get("allow_network", False))

        sandbox = PythonSandbox(
            timeout=timeout,
            memory_limit_mb=self._MEMORY_LIMIT_MB,
            allow_network=allow_network,
        )
        result = await sandbox.execute(code, input_data={})

        # 组装输出
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.output is not None:
            parts.append(f"[result]\n{result.output}")
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        output = "\n".join(parts)

        if result.success:
            return ToolResult(success=True, output=output)
        error = result.error or f"执行失败 (code={result.return_code})"
        if result.timed_out:
            error = f"代码执行超时 ({timeout}s)"
        elif result.memory_exceeded:
            error = f"内存超限 ({self._MEMORY_LIMIT_MB}MB)"
        return ToolResult(success=False, output=output, error=error)
