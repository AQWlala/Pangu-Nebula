# server/config_kb_cu.py
"""知识库与 Computer Use 配置模块"""
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KBConfig:
    """知识库配置"""
    kb_root: Path = field(default_factory=lambda: Path.home() / ".pangu-nebula" / "knowledge_base")
    documents_dir: Path | None = None
    inbox_dir: Path | None = None
    sandbox_dir: Path | None = None
    archive_dir: Path | None = None
    indexes_dir: Path | None = None
    chroma_dir: Path | None = None
    kuzu_dir: Path | None = None
    meta_db: Path | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50

    def __post_init__(self):
        if self.documents_dir is None:
            self.documents_dir = self.kb_root / "documents"
        if self.inbox_dir is None:
            self.inbox_dir = self.kb_root / "_inbox"
        if self.sandbox_dir is None:
            self.sandbox_dir = self.kb_root / "_sandbox"
        if self.archive_dir is None:
            self.archive_dir = self.kb_root / "_archive"
        if self.indexes_dir is None:
            self.indexes_dir = self.kb_root / "indexes"
        if self.chroma_dir is None:
            self.chroma_dir = self.indexes_dir / "chroma"
        if self.kuzu_dir is None:
            self.kuzu_dir = self.indexes_dir / "kuzu"
        if self.meta_db is None:
            self.meta_db = self.kb_root / "meta.db"

    def ensure_dirs(self) -> None:
        for d in [self.kb_root, self.documents_dir, self.inbox_dir,
                  self.sandbox_dir, self.archive_dir, self.indexes_dir,
                  self.chroma_dir]:
            d.mkdir(parents=True, exist_ok=True)
        # 注意：kuzu_dir 不在此列表中，因为 kuzu 在该路径创建的是文件而非目录，
        # 预先创建为目录会导致 kuzu 报错 "Database path cannot be a directory"。


@dataclass
class CUConfig:
    """Computer Use 配置"""
    audit_log_dir: Path = Path.home() / ".pangu-nebula" / "logs" / "cu_audit"
    default_step_timeout_ms: int = 3000
    max_step_timeout_ms: int = 10000
    screenshot_enabled: bool = True
    max_retries: int = 2
    confidence_high: float = 0.85
    confidence_low: float = 0.6

    def ensure_dirs(self) -> None:
        self.audit_log_dir.mkdir(parents=True, exist_ok=True)
