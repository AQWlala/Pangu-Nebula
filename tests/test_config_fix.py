import tempfile
from pathlib import Path
from server.config_kb_cu import KBConfig, CUConfig


def test_kb_config_custom_root():
    with tempfile.TemporaryDirectory() as tmp:
        custom_root = Path(tmp) / "custom_kb"
        config = KBConfig(kb_root=custom_root)
        assert config.documents_dir == custom_root / "documents"
        assert config.inbox_dir == custom_root / "_inbox"
        assert config.sandbox_dir == custom_root / "_sandbox"
        assert config.chroma_dir == custom_root / "indexes" / "chroma"
        assert config.kuzu_dir == custom_root / "indexes" / "kuzu"


def test_kb_config_default_root():
    config = KBConfig()
    assert config.kb_root == Path.home() / ".pangu-nebula" / "knowledge_base"
    assert config.documents_dir == config.kb_root / "documents"


def test_kb_config_ensure_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        config = KBConfig(kb_root=Path(tmp) / "kb")
        config.ensure_dirs()
        assert config.documents_dir.exists()
        assert config.inbox_dir.exists()
        assert config.chroma_dir.exists()
