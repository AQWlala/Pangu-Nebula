# server/cu/executor/action_types.py
"""标准化动作类型"""


class ActionType:
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLICK = "browser_click"
    BROWSER_INPUT = "browser_input"
    BROWSER_WAIT = "browser_wait"
    BROWSER_EXTRACT = "browser_extract"
    BROWSER_DOWNLOAD = "browser_download"
    FS_WRITE = "fs_write"
    FS_READ = "fs_read"
    FS_DELETE = "fs_delete"

    REVERSIBLE = {BROWSER_NAVIGATE, BROWSER_INPUT, FS_WRITE, BROWSER_DOWNLOAD}
    PARTIALLY_REVERSIBLE = {BROWSER_CLICK}
    IRREVERSIBLE = {FS_DELETE}

    @classmethod
    def is_reversible(cls, action_type):
        return action_type in cls.REVERSIBLE

    @classmethod
    def is_irreversible(cls, action_type):
        return action_type in cls.IRREVERSIBLE

    @classmethod
    def get_rollback_action(cls, action_type):
        return {
            cls.BROWSER_NAVIGATE: cls.BROWSER_NAVIGATE,
            cls.BROWSER_INPUT: cls.BROWSER_INPUT,
            cls.FS_WRITE: cls.FS_DELETE,
            cls.BROWSER_DOWNLOAD: cls.FS_DELETE,
        }.get(action_type)
