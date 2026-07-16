# server/kb/storage/inbox.py
"""_inbox 暂存回写管理"""
from __future__ import annotations
from pathlib import Path
import json
import re
import uuid
import shutil
from datetime import datetime, timezone
from server.kb.storage.frontmatter import FrontMatter, dump_frontmatter

_PENDING_ID_PATTERN = re.compile(r"^pending-\d{14}-[0-9a-f]{8}$")


def _validate_pending_id(pending_id: str) -> None:
    """Validate pending_id to prevent path traversal.

    Format: pending-YYYYMMDDHHMMSS-XXXXXXXX (8 hex chars).
    Rejects any input containing ``..``, ``/``, ``\\`` or null bytes.
    """
    if not _PENDING_ID_PATTERN.match(pending_id):
        raise ValueError(f"Invalid pending_id: {pending_id}")


class InboxWriter:
    """管理 _inbox/ 暂存区，禁止直写 documents/"""

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def stage(
        self,
        original_filename: str,
        converted_md: str,
        frontmatter: FrontMatter,
        meta: dict,
    ) -> str:
        pending_id = f"pending-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        pending_dir = self.inbox_dir / pending_id
        pending_dir.mkdir(parents=True, exist_ok=True)

        (pending_dir / "converted.md").write_text(converted_md, encoding="utf-8")
        (pending_dir / "frontmatter.yaml").write_text(
            dump_frontmatter(frontmatter), encoding="utf-8"
        )

        meta_data = {
            "original_filename": original_filename,
            "staged_at": datetime.now(timezone.utc).isoformat() + "Z",
            **meta,
        }
        (pending_dir / "meta.json").write_text(
            json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return pending_id

    def get_pending(self, pending_id: str) -> dict | None:
        _validate_pending_id(pending_id)
        pending_dir = self.inbox_dir / pending_id
        if not pending_dir.exists():
            return None

        converted_path = pending_dir / "converted.md"
        meta_path = pending_dir / "meta.json"
        fm_path = pending_dir / "frontmatter.yaml"

        if not converted_path.exists():
            return None

        return {
            "pending_id": pending_id,
            "converted_md": converted_path.read_text(encoding="utf-8"),
            "frontmatter": fm_path.read_text(encoding="utf-8") if fm_path.exists() else "",
            "meta": json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {},
        }

    def list_pending(self) -> list[str]:
        return [d.name for d in self.inbox_dir.iterdir() if d.is_dir()]

    def remove_pending(self, pending_id: str) -> None:
        _validate_pending_id(pending_id)
        pending_dir = self.inbox_dir / pending_id
        if pending_dir.exists():
            shutil.rmtree(pending_dir)
