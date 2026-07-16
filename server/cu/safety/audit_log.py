# server/cu/safety/audit_log.py
"""操作审计日志（结构化 JSON，append-only + hash chain）"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
from collections.abc import Iterator

_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_task_id(task_id: str) -> None:
    """Validate task_id to prevent path traversal.

    Rejects empty values, null bytes, ``..`` segments, and any character
    outside ``[A-Za-z0-9._-]`` (which covers ``/`` and ``\\``).
    """
    if (not task_id or "\x00" in task_id or ".." in task_id
            or not _TASK_ID_PATTERN.match(task_id)):
        raise ValueError(f"Invalid task_id: {task_id}")


class AuditLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir

    def log_step(self, task_id: str, step_index: int, action_type: str,
                 action_payload: dict, result_status: str,
                 result_data: dict | None = None,
                 screenshot_path: str | None = None,
                 duration_ms: int | None = None) -> dict:
        _validate_task_id(task_id)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / task_id / "audit.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        prev_hash = self._get_last_hash(log_file)
        entry = {
            "task_id": task_id,
            "step_index": step_index,
            "action_type": action_type,
            "action_payload": action_payload,
            "result_status": result_status,
            "result_data": result_data or {},
            "screenshot_path": screenshot_path,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prev_hash": prev_hash,
        }
        entry_json = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
        entry["hash"] = entry_hash

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry

    def _get_last_hash(self, log_file: Path) -> str:
        """获取日志文件中最后一条记录的 hash，用于构建哈希链。"""
        if not log_file.exists():
            return ""
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                return ""
            last_entry = json.loads(lines[-1])
            return last_entry.get("hash", "")
        except (json.JSONDecodeError, OSError):
            return ""

    def get_task_logs(self, task_id: str) -> list[dict]:
        _validate_task_id(task_id)
        log_file = self.log_dir / task_id / "audit.jsonl"
        if not log_file.exists():
            return []
        with open(log_file, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def iter_audit_entries(self, task_id: str, limit: int = 100) -> Iterator[dict]:
        """流式迭代审计日志条目,从末尾开始倒序。

        v2.2.1 P2: 用生成器避免一次性加载整个文件到内存,防止大日志文件 OOM。
        只读取文件末尾约 ``limit * 200`` 字节(按每行平均 200 字节估算),
        跳过无效 JSON 行,按倒序产出至多 ``limit`` 条。

        与 ``get_task_logs`` 的区别:后者返回全量 list(正序),用于完整回放;
        本方法面向「最近 N 条」的预览/分页场景,内存占用与 limit 成正比,
        而非与文件大小成正比。
        """
        _validate_task_id(task_id)
        log_file = self.log_dir / task_id / "audit.jsonl"
        if not log_file.exists():
            return
        file_size = log_file.stat().st_size
        # 读取末尾 limit*200 字节(假设每行平均 200 字节)
        read_size = min(file_size, limit * 200)
        with log_file.open("r", encoding="utf-8") as f:
            f.seek(file_size - read_size)
            lines = f.readlines()
        count = 0
        for line in reversed(lines):
            if count >= limit:
                return
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
