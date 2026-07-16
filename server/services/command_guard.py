"""v2.2.0 危险命令防护 (Phase 2)

黑名单模式: 检测并拦截危险命令,防止 LLM 通过 execute_command 工具
执行破坏性操作。

覆盖类别:
- 文件系统破坏 (rm -rf /, format, mkfs, dd of=/dev/)
- 系统控制 (shutdown, reboot, halt, taskkill /f)
- 权限提升 (sudo rm, su root)
- 远程脚本执行 (curl | sh, wget | bash)
- 注册表/系统配置 (reg delete, regsvr32 /s)
"""

from __future__ import annotations

import re


# 危险命令模式列表 (pattern, description)
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # 文件系统破坏
    (r"\brm\s+(?:-\w*\s+)*-?rf?\s+/(?:\s|$|\*)", "rm -rf / 递归删除根目录"),
    (r"\brm\s+(?:-\w*\s+)*-?rf?\s+\*", "rm -rf * 递归删除当前目录"),
    (r"\brm\s+(?:-\w*\s+)*-?rf?\s+~(?:\s|$|\*)", "rm -rf ~ 递归删除家目录"),
    (r"\brm\s+(?:-\w*\s+)*-?rf?\s+%USERPROFILE%", "rm -rf 用户目录"),
    (r"\bformat\s+[a-z]:", "format 格式化磁盘"),
    (r"\bdel\s+/[sf]", "del /s /f 强制删除"),
    (r"\brmdir\s+/s", "rmdir /s 递归删除目录"),
    (r"\bmkfs\.", "mkfs 格式化文件系统"),
    (r"\bdd\s+.*of=/dev/", "dd 写入设备文件"),
    (r"\bshred\s+-", "shred 粉碎文件"),
    # 系统控制
    (r"\bshutdown\b", "shutdown 关机"),
    (r"\breboot\b", "reboot 重启"),
    (r"\bhalt\b", "halt 停机"),
    (r"\bpoweroff\b", "poweroff 关机"),
    (r"\btaskkill\s+/f", "taskkill /f 强制结束进程"),
    (r"\bkillall\b", "killall 结束所有进程"),
    (r"\bkill\s+-9\s+1\b", "kill -9 1 杀死 init 进程"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "systemctl 停止/禁用服务"),
    # 权限提升
    (r"\bsudo\s+rm\b", "sudo rm 提权删除"),
    (r"\bsu\s+root\b", "su root 切换 root"),
    (r"\bchmod\s+777\s+/", "chmod 777 根目录"),
    (r"\bchown\s+-R\b", "chown -R 递归修改属主"),
    # 远程脚本执行
    (r"\bcurl\s+.*\|\s*(?:sh|bash|zsh)\b", "curl | sh 管道执行远程脚本"),
    (r"\bwget\s+.*\|\s*(?:sh|bash|zsh)\b", "wget | sh 管道执行远程脚本"),
    (r"\bcurl\s+.*\|\s*python\b", "curl | python 管道执行远程代码"),
    (r"\bwget\s+.*\|\s*python\b", "wget | python 管道执行远程代码"),
    # 注册表/系统配置
    (r"\breg\s+delete\b", "reg delete 删除注册表"),
    (r"\bregsvr32\s+/s\b", "regsvr32 /s 静默注册 DLL"),
    (r"\bcd\b.*;\s*rm\b", "cd 切换后删除 (可疑链式)"),
    # 叉炸弹
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", "fork bomb 叉炸弹"),
]

_compiled_patterns = [
    (re.compile(p, re.IGNORECASE), desc) for p, desc in _DANGEROUS_PATTERNS
]


def check_command(command: str) -> tuple[bool, str]:
    """检查命令是否安全

    Returns:
        (safe, reason): safe=True 时 reason 为空;
        safe=False 时 reason 为拦截原因。
    """
    if not command or not command.strip():
        return False, "空命令"
    for pattern, desc in _compiled_patterns:
        if pattern.search(command):
            return False, f"危险命令被拦截: {desc}"
    return True, ""
