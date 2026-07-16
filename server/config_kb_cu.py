# server/config_kb_cu.py
"""知识库与 Computer Use 配置模块"""
from pathlib import Path
from dataclasses import dataclass


@dataclass
class KBConfig:
    """知识库配置"""
    kb_root: Path = Path.home() / ".pangu-nebula" / "knowledge_base"
    documents_dir: Path = kb_root / "documents"
    inbox_dir: Path = kb_root / "_inbox"
    sandbox_dir: Path = kb_root / "_sandbox"
    archive_dir: Path = kb_root / "_archive"
    indexes_dir: Path = kb_root / "indexes"
    chroma_dir: Path = indexes_dir / "chroma"
    kuzu_dir: Path = indexes_dir / "kuzu"
    meta_db: Path = kb_root / "meta.db"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50

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
