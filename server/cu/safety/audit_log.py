# server/cu/safety/audit_log.py
"""操作审计日志（结构化 JSON，append-only）"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json


class AuditLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_step(self, task_id, step_index, action_type, action_payload,
                 result_status, result_data=None, screenshot_path=None, duration_ms=None):
        entry = {
            "log_id": f"culog-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{step_index:04d}",
            "task_id": task_id, "step_index": step_index, "action_type": action_type,
            "action_payload": action_payload, "result_status": result_status,
            "result_data": result_data or {}, "screenshot_path": screenshot_path,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "duration_ms": duration_ms,
        }
        task_log_dir = self.log_dir / task_id
        task_log_dir.mkdir(parents=True, exist_ok=True)
        (task_log_dir / f"step-{step_index:04d}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        return entry

    def get_task_logs(self, task_id):
        task_log_dir = self.log_dir / task_id
        if not task_log_dir.exists():
            return []
        return [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(task_log_dir.glob("step-*.json"))]
