# tests/test_phase0_infra.py
import pytest
from server.config_kb_cu import KBConfig, CUConfig

def test_kb_config_defaults():
    config = KBConfig()
    assert config.kb_root.name == "knowledge_base"
    assert config.documents_dir.name == "documents"
    assert config.inbox_dir.name == "_inbox"
    assert config.sandbox_dir.name == "_sandbox"
    assert config.chroma_dir.name == "chroma"
    assert config.kuzu_dir.name == "kuzu"
    assert config.meta_db.name == "meta.db"

def test_cu_config_defaults():
    config = CUConfig()
    assert config.audit_log_dir.name == "cu_audit"
    assert config.default_step_timeout_ms == 3000
    assert config.max_step_timeout_ms == 10000
    assert config.screenshot_enabled is True

def test_kb_config_dirs_are_under_kb_root():
    config = KBConfig()
    assert config.documents_dir.parent == config.kb_root
    assert config.inbox_dir.parent == config.kb_root
    assert config.sandbox_dir.parent == config.kb_root
