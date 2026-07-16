"""路径安全守卫 — 防止 file_read/file_write 工具路径穿越

v2.2.1 安全修复 F1: file_read/file_write 原先直接 open(path) 无白名单,
LLM 可读取 ~/.ssh/id_rsa / .env / /etc/passwd 等敏感文件。

策略:
- 基于 persona 配置的 allowed_paths 做前缀校验
- 解析软链接防止符号链接绕过
- 拒绝访问敏感路径黑名单 (.env, .ssh, /etc, /var/log 等)

融合来源:
- docs/v2.2.0-architecture-plan.md 安全设计
- server/services/ssrf_guard.py (同类守卫模块风格)
- server/services/injection_guard.py
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path


class PathGuard:
    """路径安全守卫:白名单前缀校验 + 黑名单拒绝 + 软链接解析"""

    # 默认黑名单 (不区分大小写匹配)
    # - 点文件/目录: 凭证与配置
    # - Unix 敏感文件: 账户与权限
    # - 密钥文件名
    # - 证书扩展名
    DEFAULT_DENIED: list[str] = [
        ".env",
        ".ssh",
        ".aws",
        ".gnupg",
        ".gitconfig",
        ".npmrc",
        ".pypirc",
        "/etc/passwd",
        "/etc/shadow",
        "/etc/sudoers",
        "credentials",
        "id_rsa",
        "id_ecdsa",
        "id_ed25519",
        "*.key",
        "*.pem",
        "*.pfx",
        "*.p12",
    ]

    # write 模式额外禁止的系统目录名 (路径紧邻根之后的第二层 part, 不区分大小写)
    # 覆盖 Unix 系统目录与 Windows 系统目录
    _WRITE_DENIED_DIR_NAMES: set[str] = {
        "etc", "usr", "bin", "sbin", "var", "sys", "proc", "boot", "dev",
        "lib", "lib64", "root",
        "windows", "system32", "system",
        "program files", "program files (x86)",
    }

    def __init__(
        self,
        allowed_paths: list[str],
        denied_paths: list[str] | None = None,
    ) -> None:
        """初始化白名单与黑名单

        Args:
            allowed_paths: 允许访问的目录前缀列表 (会被 resolve 为绝对路径)
            denied_paths: 拒绝访问的路径模式列表; None 时使用 DEFAULT_DENIED
        """
        # resolve 白名单, 解析软链接与相对路径, 便于精确前缀判断
        self.allowed_paths: list[Path] = [
            Path(p).resolve() for p in allowed_paths
        ]
        self.denied_paths: list[str] = (
            list(denied_paths) if denied_paths is not None else list(self.DEFAULT_DENIED)
        )

    @classmethod
    def default_allowed_paths(cls) -> list[str]:
        """返回默认白名单:当前工作目录 + 用户文档目录 + KB 文档目录

        保证无 persona 配置时仍可访问业务必需的工作区与 KB 文档仓库。
        """
        paths: list[str] = [str(Path.cwd().resolve())]
        # 用户文档目录
        try:
            paths.append(str((Path.home() / "Documents").resolve()))
        except (OSError, RuntimeError):
            pass
        # KB 文档仓库目录 (项目根下 kb/)
        paths.append(str((Path.cwd().resolve() / "kb")))
        return paths

    @classmethod
    def default_denied_paths(cls) -> list[str]:
        """返回默认黑名单 (DEFAULT_DENIED 的副本)"""
        return list(cls.DEFAULT_DENIED)

    def _matches_denied(self, resolved: Path, pattern: str) -> bool:
        """判断已 resolve 的路径是否命中单个黑名单模式 (不区分大小写)

        匹配规则:
        - ``*.ext`` 扩展名模式: 比较路径 suffix
        - 带分隔符的路径模式 (如 ``/etc/passwd``): 拆分为 parts, 比较路径 parts 是否以模式 parts 结尾
        - 单纯文件名/目录名 (如 ``.env``/``id_rsa``): 路径任一 part 等于该名
        """
        pl = pattern.lower()

        # 扩展名模式: *.key / *.pem ...
        if pl.startswith("*."):
            return resolved.suffix.lower() == pl[1:]

        # 带路径分隔符的模式: /etc/passwd 等
        if "/" in pl or "\\" in pl:
            pat_parts = [p for p in pl.replace("\\", "/").split("/") if p]
            # 过滤掉盘符与裸分隔符, 仅保留真实路径段
            path_parts = [
                p.lower() for p in resolved.parts
                if p not in ("\\", "/", "")
            ]
            if len(path_parts) >= len(pat_parts):
                return path_parts[-len(pat_parts):] == pat_parts
            return False

        # 单纯文件名/目录名: 精确匹配任一 part (避免 .env 误伤 .environment)
        return pl in [p.lower() for p in resolved.parts]

    def validate(self, path: str, write: bool = False) -> tuple[bool, str]:
        """校验路径是否允许访问

        v2.2.1 P3: 入口做 NFKC 规范化, 防止 Unicode 同形字符绕过黑名单
        (如全角 ".ｅｎｖ" 规范化为 ".env" 后命中黑名单)。

        Args:
            path: 待校验路径 (绝对或相对)
            write: 是否为写操作; True 时额外拒绝系统目录

        Returns:
            (allowed, reason)。allowed=True 时 reason 为 "允许访问"。
        """
        # 0. v2.2.1 P3: NFKC 规范化路径字符串
        # 全角字符→半角 (ｅｎｖ → env), 兼容字符→标准字符
        # 在 resolve 前规范化, 使后续黑名单/白名单匹配基于规范形式
        if path:
            path = unicodedata.normalize("NFKC", path)
        # 1. resolve 解析软链接与相对路径, 得到真实绝对路径
        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError) as exc:
            return False, f"路径解析失败: {exc}"

        # 2. 黑名单优先 (read/write 均生效)
        for pattern in self.denied_paths:
            if self._matches_denied(resolved, pattern):
                return False, f"路径命中黑名单: {pattern}"

        # 3. write 模式额外拒绝系统目录 (根之后的第一级目录, 即 parts[1])
        # POSIX: ('/', 'etc', ...) ; Windows: ('D:\\', 'etc', ...) — parts[1] 均为根下首级目录
        if write:
            parts = resolved.parts
            if len(parts) >= 2 and parts[1].lower() in self._WRITE_DENIED_DIR_NAMES:
                return False, f"write 模式禁止写入系统目录: {parts[1]}"

        # 4. 白名单前缀校验 (用 relative_to 精确判断, 避免字符串前缀陷阱)
        for allowed in self.allowed_paths:
            try:
                resolved.relative_to(allowed)
                return True, "允许访问"
            except ValueError:
                continue

        return False, f"路径不在白名单内: {resolved}"
