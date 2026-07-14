"""Provider configuration persistence — JSON file storage, env var priority"""

import json
import os
from pathlib import Path
from threading import Lock

from ..config import DATA_DIR

_CONFIG_PATH = DATA_DIR / "provider_config.json"
_lock = Lock()


def _ensure_config_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_config() -> dict:
    """Read config, returns {provider_name: {api_key, base_url, model}}"""
    _ensure_config_dir()
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(data: dict) -> None:
    _ensure_config_dir()
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_provider_config(name: str) -> dict | None:
    """Return config dict for a specific provider, or None."""
    with _lock:
        cfg = _read_config()
        return cfg.get(name)


def set_provider_config(name: str, api_key: str = "", base_url: str = "", model: str = "") -> None:
    """Save or update config for a provider."""
    with _lock:
        cfg = _read_config()
        cfg[name] = {"api_key": api_key, "base_url": base_url, "model": model}
        _write_config(cfg)


def list_all_configs() -> dict:
    """Return all provider configs."""
    with _lock:
        return _read_config()
