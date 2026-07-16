# server/kb/storage/repo.py
"""Markdown 文档仓库 CRUD"""
from __future__ import annotations
from pathlib import Path
import hashlib
from datetime import datetime
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter, dump_frontmatter


class DocumentRepo:
    """本地 MD 文件仓库，唯一事实来源"""

    def __init__(self, documents_dir: Path):
        self.documents_dir = documents_dir
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, doc_id: str) -> Path:
        safe_id = doc_id.replace("/", "_").replace("\\", "_")
        return self.documents_dir / f"{safe_id}.md"

    def save(self, fm: FrontMatter, body: str) -> Path:
        now = datetime.utcnow().isoformat() + "Z"
        if not fm.created_at:
            fm.created_at = now
        fm.updated_at = now

        if not fm.checksum or fm.checksum.startswith("sha256:"):
            content_hash = hashlib.sha256(body.encode()).hexdigest()
            fm.checksum = f"sha256:{content_hash}"

        content = dump_frontmatter(fm) + "\n\n" + body
        file_path = self._file_path(fm.id)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read(self, doc_id: str) -> tuple[FrontMatter, str]:
        file_path = self._file_path(doc_id)
        content = file_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        return fm, body

    def exists(self, doc_id: str) -> bool:
        return self._file_path(doc_id).exists()

    def delete(self, doc_id: str) -> None:
        file_path = self._file_path(doc_id)
        if file_path.exists():
            file_path.unlink()

    def list_all(self) -> list[str]:
        return [f.stem for f in self.documents_dir.glob("*.md")]
