# server/cu/executor/action_types.py
"""标准化动作类型"""
from __future__ import annotations

from enum import StrEnum


class ActionType(StrEnum):
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLICK = "browser_click"
    BROWSER_INPUT = "browser_input"
    BROWSER_WAIT = "browser_wait"
    BROWSER_EXTRACT = "browser_extract"
    BROWSER_DOWNLOAD = "browser_download"
    FS_WRITE = "fs_write"
    FS_READ = "fs_read"
    FS_DELETE = "fs_delete"

    @classmethod
    def is_reversible(cls, action_type: str) -> bool:
        return action_type in cls.REVERSIBLE

    @classmethod
    def is_irreversible(cls, action_type: str) -> bool:
        return action_type in cls.IRREVERSIBLE

    @classmethod
    def get_rollback_action(cls, action_type: str) -> str | None:
        return {
            cls.BROWSER_NAVIGATE: cls.BROWSER_NAVIGATE,
            cls.BROWSER_INPUT: cls.BROWSER_INPUT,
            cls.FS_WRITE: cls.FS_DELETE,
            cls.BROWSER_DOWNLOAD: cls.FS_DELETE,
        }.get(action_type)


# Enum 把类体内赋值的名称视为成员，因此非成员的查找集合必须在类体之外
# 定义。StrEnum 成员既是 str（hash 与 __eq__ 与对应字符串一致），故
# `"browser_navigate" in ActionType.REVERSIBLE` 仍然成立，向后兼容。
ActionType.REVERSIBLE = {
    ActionType.BROWSER_NAVIGATE,
    ActionType.BROWSER_INPUT,
    ActionType.FS_WRITE,
    ActionType.BROWSER_DOWNLOAD,
}
ActionType.PARTIALLY_REVERSIBLE = {ActionType.BROWSER_CLICK}
ActionType.IRREVERSIBLE = {ActionType.FS_DELETE}
