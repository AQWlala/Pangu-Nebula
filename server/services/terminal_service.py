"""终端模式服务 — PTY/CLI 集成

双模式:
- 有 ptyprocess/winpty 时: 真实 PTY 终端
- 无依赖时: mock 模式 (返回占位输出)

用途: 让 Pangu Nebula 支持命令行交互模式
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
import uuid
from typing import Any


# F3: shell 白名单 — 防止指定任意可执行文件(如 calc.exe / ./evil.sh)
# 通过 shutil.which 解析完整路径后校验 basename,防止路径遍历绕过
_ALLOWED_SHELLS: dict[str, set[str]] = {
    "win32": {"cmd.exe", "powershell.exe", "pwsh.exe"},
    "linux": {"bash", "sh", "zsh", "fish", "dash"},
    "darwin": {"bash", "sh", "zsh", "fish"},
}


def _validate_shell(shell: str) -> tuple[bool, str]:
    """校验 shell 是否在白名单内,防止指定任意可执行文件。

    使用 shutil.which 解析完整路径后校验 basename,防止 ./evil.sh 绕过。
    返回 (True, resolved_path) 或 (False, error_message)。
    """
    resolved = shutil.which(shell)
    if resolved is None:
        return False, f"shell not found: {shell}"
    # v2.2.2: 跨平台 basename 提取 — Linux 上 os.path.basename 不认 Windows \ 路径分隔符
    basename = os.path.basename(resolved.replace("\\", "/")).lower()
    allowed = _ALLOWED_SHELLS.get(sys.platform, set())
    if basename not in allowed:
        return False, f"shell not allowed: {shell} (resolved: {resolved}). Allowed: {allowed}"
    return True, resolved


class TerminalService:
    """终端服务

    在 PTY 依赖可用时启动真实终端会话;否则进入 mock 模式,
    返回占位输出便于前端开发与测试。
    """

    def __init__(self) -> None:
        self._available = self._check_availability()
        # session_id -> { proc, cols, rows, shell, mock, created_at, buffer }
        self._sessions: dict[str, dict[str, Any]] = {}

    def _check_availability(self) -> bool:
        """检查 PTY 支持(ptyprocess 或 winpty)"""
        try:
            import ptyprocess  # type: ignore  # noqa: F401

            return True
        except ImportError:
            try:
                import winpty  # type: ignore  # noqa: F401

                return True
            except ImportError:
                return False

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------

    async def create_session(
        self, shell: str = "powershell", cols: int = 80, rows: int = 24
    ) -> dict:
        """创建终端会话

        mock 模式: 返回 {"ok": True, "data": {"session_id": "mock-xxx", "mock": True, ...}}
        real 模式: 启动 PTY 进程并返回 session_id
        """
        session_id = uuid.uuid4().hex
        if not self._available:
            session_id = f"mock-{session_id}"
            self._sessions[session_id] = {
                "mock": True,
                "shell": shell,
                "cols": cols,
                "rows": rows,
                "created_at": time.time(),
                "buffer": "",
                "proc": None,
            }
            return {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "mock": True,
                    "shell": shell,
                    "cols": cols,
                    "rows": rows,
                },
                "error": None,
            }

        # 真实 PTY 模式(依赖可用时)
        # F3: shell 白名单校验,防止指定任意可执行文件
        ok, result = _validate_shell(shell)
        if not ok:
            return {"ok": False, "data": None, "error": result}

        try:
            proc = await self._spawn_pty(result, cols, rows)
        except Exception as e:
            # 启动失败时回退到 mock 模式
            session_id = f"mock-{session_id}"
            self._sessions[session_id] = {
                "mock": True,
                "shell": shell,
                "cols": cols,
                "rows": rows,
                "created_at": time.time(),
                "buffer": f"[pty spawn failed: {e}; falling back to mock]\r\n",
                "proc": None,
            }
            return {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "mock": True,
                    "shell": shell,
                    "cols": cols,
                    "rows": rows,
                    "fallback_reason": str(e),
                },
                "error": None,
            }

        self._sessions[session_id] = {
            "mock": False,
            "shell": shell,
            "cols": cols,
            "rows": rows,
            "created_at": time.time(),
            "buffer": "",
            "proc": proc,
        }
        return {
            "ok": True,
            "data": {
                "session_id": session_id,
                "mock": False,
                "shell": shell,
                "cols": cols,
                "rows": rows,
            },
            "error": None,
        }

    async def _spawn_pty(self, shell: str, cols: int, rows: int) -> Any:
        """启动 PTY 进程(真实模式)"""
        try:
            import ptyprocess  # type: ignore

            proc = ptyprocess.PtyProcessUnicode.spawn([shell])
            proc.setwinsize(rows, cols)
            return proc
        except ImportError:
            try:
                import winpty  # type: ignore

                proc = winpty.PtyProcess.spawn(shell, dimensions=(cols, rows))
                return proc
            except ImportError as e:
                raise RuntimeError("no PTY backend available") from e

    def _get_session(self, session_id: str) -> dict | None:
        return self._sessions.get(session_id)

    # ------------------------------------------------------------------
    # 数据读写
    # ------------------------------------------------------------------

    async def write(self, session_id: str, data: str) -> dict:
        """向终端写入数据

        mock 模式: 返回 {"ok": True, "data": {"mock": True, "output": ...}}
        """
        session = self._get_session(session_id)
        if session is None:
            return {"ok": False, "data": None, "error": f"session not found: {session_id}"}

        if session.get("mock"):
            # mock 模式:模拟回显并返回占位输出
            echo = data
            session["buffer"] += echo
            # 模拟 shell 命令回显
            return {
                "ok": True,
                "data": {
                    "mock": True,
                    "output": f"mock output for: {data}",
                    "echo": echo,
                },
                "error": None,
            }

        # 真实模式:写入 PTY
        proc = session.get("proc")
        if proc is None:
            return {"ok": False, "data": None, "error": "pty process not available"}
        try:
            await asyncio.to_thread(proc.write, data)
        except Exception as e:
            return {"ok": False, "data": None, "error": f"write failed: {e}"}
        return {"ok": True, "data": {"mock": False, "written": len(data)}, "error": None}

    async def read(self, session_id: str, timeout: float = 1.0) -> dict:
        """读取终端输出

        mock 模式: 返回 {"ok": True, "data": {"data": "mock terminal output"}}
        """
        session = self._get_session(session_id)
        if session is None:
            return {"ok": False, "data": None, "error": f"session not found: {session_id}"}

        if session.get("mock"):
            return {
                "ok": True,
                "data": {
                    "data": "mock terminal output",
                    "mock": True,
                },
                "error": None,
            }

        # 真实模式:从 PTY 非阻塞读取
        proc = session.get("proc")
        if proc is None:
            return {"ok": False, "data": None, "error": "pty process not available"}
        try:
            chunk = await asyncio.to_thread(self._safe_read, proc, timeout)
        except Exception as e:
            return {"ok": False, "data": None, "error": f"read failed: {e}"}
        return {"ok": True, "data": {"data": chunk, "mock": False}, "error": None}

    @staticmethod
    def _safe_read(proc: Any, timeout: float) -> str:
        """从 PTY 安全读取(非阻塞,超时返回空字符串)"""
        try:
            # ptyprocess 提供 read_timeout
            return proc.read_timeout(timeout)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # 终端控制
    # ------------------------------------------------------------------

    async def resize(self, session_id: str, cols: int, rows: int) -> dict:
        """调整终端大小"""
        session = self._get_session(session_id)
        if session is None:
            return {"ok": False, "data": None, "error": f"session not found: {session_id}"}
        session["cols"] = cols
        session["rows"] = rows
        if not session.get("mock"):
            proc = session.get("proc")
            if proc is not None:
                try:
                    await asyncio.to_thread(proc.setwinsize, rows, cols)
                except Exception as e:
                    return {"ok": False, "data": None, "error": f"resize failed: {e}"}
        return {
            "ok": True,
            "data": {"session_id": session_id, "cols": cols, "rows": rows, "mock": session.get("mock", False)},
            "error": None,
        }

    async def close_session(self, session_id: str) -> dict:
        """关闭终端会话"""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return {"ok": False, "data": None, "error": f"session not found: {session_id}"}
        if not session.get("mock"):
            proc = session.get("proc")
            if proc is not None:
                try:
                    await asyncio.to_thread(proc.terminate, force=True)
                except Exception:
                    # 关闭失败时静默(进程可能已退出)
                    pass
        return {
            "ok": True,
            "data": {"session_id": session_id, "closed": True, "mock": session.get("mock", False)},
            "error": None,
        }

    async def list_sessions(self) -> list[dict]:
        """列出活跃会话"""
        result: list[dict] = []
        for sid, session in self._sessions.items():
            result.append({
                "session_id": sid,
                "mock": session.get("mock", False),
                "shell": session.get("shell"),
                "cols": session.get("cols"),
                "rows": session.get("rows"),
                "created_at": session.get("created_at"),
            })
        return result

    def get_status(self) -> dict:
        """获取终端服务状态"""
        return {
            "available": self._available,
            "mode": "real" if self._available else "mock",
            "active_sessions": len(self._sessions),
        }
