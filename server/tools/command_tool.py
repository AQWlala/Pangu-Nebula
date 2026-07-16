"""v2.2.0 命令执行工具 (Phase 2)

通过 subprocess 安全执行 shell 命令。

职责链 (与 ToolExecutor 配合):
    ToolExecutor 权限检查 (terminal_allowed)
      → ToolExecutor InjectionGuard (code context)
        → ExecuteCommandTool.execute
          → command_guard 黑名单检查
            → asyncio.create_subprocess_{shell|exec} 执行
              → 返回 stdout/stderr

v2.2.1 F6 双模式:
    allow_pipeline=False (默认,安全优先):
        用 asyncio.create_subprocess_exec(*shlex.split(command)) 直接执行
        不经过 shell 解释器,不支持 pipeline/重定向/变量展开
    allow_pipeline=True:
        用 asyncio.create_subprocess_shell(command) shell 模式
        必须先通过 command_guard.check_command 校验,并记录审计日志

不依赖 PTY (ptyprocess/winpty),使用 asyncio subprocess 直接执行,
适合 LLM 工具调用的一次性命令场景。交互式终端由 TerminalService 单独提供。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex

from ..services.command_guard import check_command
from .registry import BaseTool, ToolResult, register_tool


logger = logging.getLogger(__name__)


@register_tool("execute_command")
class ExecuteCommandTool(BaseTool):
    name = "execute_command"
    description = (
        "Execute a shell command and return stdout/stderr. "
        "Dangerous commands (rm -rf /, format, shutdown, ...) are blocked. "
        "Requires terminal_allowed permission on the persona."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 120)",
                "default": 30,
            },
            "allow_pipeline": {
                "type": "boolean",
                "description": (
                    "v2.2.1 F6: allow shell features (pipeline |, redirect >, "
                    "$VAR expansion). Default false (exec mode, safer). "
                    "When true, runs via shell and command_guard checks."
                ),
                "default": False,
            },
        },
        "required": ["command"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"command", "timeout", "allow_pipeline"}

    _MAX_TIMEOUT = 120

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        allow_pipeline: bool = False,
        **kwargs,
    ) -> ToolResult:
        # 1. 危险命令黑名单检查 — 无论 shell/exec 模式都校验
        safe, reason = check_command(command)
        if not safe:
            return ToolResult(success=False, output="", error=reason)

        # 2. 超时上限保护
        timeout = max(1, min(int(timeout), self._MAX_TIMEOUT))

        # 3. 执行命令 — 双模式
        try:
            if allow_pipeline:
                # shell 模式 — 支持 pipeline/重定向/变量展开
                # 风险更高,但 command_guard 已校验,并记录审计日志
                logger.warning(
                    "execute_command shell mode (allow_pipeline=True): %s",
                    command[:200],
                )
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # exec 模式 — 不经过 shell 解释器
                # shlex.split 拆分为 args list,直接传给 create_subprocess_exec
                # 注意:此模式不支持 pipeline/重定向/变量展开/shell builtins
                # 在 Windows 上,shlex.split 默认 posix=True 也能正确处理普通命令
                try:
                    args = shlex.split(command, posix=(os.name != "nt"))
                except ValueError as exc:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"命令解析失败 (shlex): {exc}",
                    )
                if not args:
                    return ToolResult(success=False, output="", error="空命令")
                logger.info(
                    "execute_command exec mode (allow_pipeline=False): %s",
                    args[0] if args else "",
                )
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"命令执行超时 ({timeout}s),已终止",
                )

            stdout = (
                stdout_bytes.decode("utf-8", errors="replace")
                if stdout_bytes
                else ""
            )
            stderr = (
                stderr_bytes.decode("utf-8", errors="replace")
                if stderr_bytes
                else ""
            )
            return_code = (
                proc.returncode if proc.returncode is not None else -1
            )

            # 组装输出
            parts: list[str] = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            output = "\n".join(parts)

            if return_code != 0:
                return ToolResult(
                    success=False,
                    output=output,
                    error=f"命令退出码 {return_code}",
                )
            return ToolResult(success=True, output=output)
        except Exception as exc:
            return ToolResult(
                success=False, output="", error=f"命令执行异常: {exc}"
            )
