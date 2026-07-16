# server/kb/retrieval/scope.py
"""作用域硬隔离过滤（E2 安全核心）"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.kb.retrieval.hybrid import SearchResult


class ScopeFilter:
    """服务端代码级强制 scope 过滤"""

    @staticmethod
    def filter(results: list["SearchResult"], scope: str) -> list["SearchResult"]:
        """双重保险：检索后再次校验 scope"""
        return [r for r in results if r.scope == scope]
