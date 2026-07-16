# server/cu/sandbox/fs_sandbox.py
"""文件系统沙箱（白名单隔离）"""
from __future__ import annotations
from pathlib import Path


class SandboxViolation(PermissionError):
    """沙箱违规"""


class FsSandbox:
    """文件系统白名单沙箱"""

    def __init__(self, sandbox_root: Path, read_whitelist: list[Path] | None = None):
        self.sandbox_root = sandbox_root.resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.read_whitelist = [p.resolve() for p in (read_whitelist or [])]

    def validate_write(self, path: Path) -> bool:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.sandbox_root)
        except ValueError:
            raise SandboxViolation(f"CU 写操作越界: {path} 不在沙箱 {self.sandbox_root} 内")
        return True

    def validate_read(self, path: Path) -> bool:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.sandbox_root)
            return True
        except ValueError:
            pass
        for allowed in self.read_whitelist:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        raise SandboxViolation(f"CU 读操作越界: {path} 不在白名单内")
