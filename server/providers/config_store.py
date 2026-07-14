"""Provider 配置持久化 — JSON 文件存储，env var 优先

路径管理: 使用 server.config.DATA_DIR (打包后重定向到 %APPDATA%/nebula/data)
导入兼容: resolve_api_key / resolve_base_url 供 protocols 调用
参数命名: set_provider_config 参数名与 server.api.providers 保持一致
"""

import json
import os
from threading import Lock

from ..config import DATA_DIR

_CONFIG_PATH = DATA_DIR / "provider_config.json"
_lock = Lock()


def _ensure_config_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_config() -> dict:
    """读取配置，返回 {provider_name: {api_key, api_base, default_model}}"""
    _ensure_config_dir()
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config(config: dict) -> None:
    _ensure_config_dir()
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_provider_config(provider_name: str) -> dict:
    """获取指定 provider 的配置。env var 优先，config 文件作为 fallback。"""
    config = _read_config()
    return config.get(provider_name, {})


def set_provider_config(
    provider_name: str,
    api_key: str | None = None,
    api_base: str | None = None,
    default_model: str | None = None,
) -> None:
    """设置指定 provider 的配置，部分更新。

    参数名与 server.api.providers.ProviderConfigureRequest 保持一致。
    """
    with _lock:
        config = _read_config()
        entry = config.get(provider_name, {})
        if api_key is not None:
            entry["api_key"] = api_key
        if api_base is not None:
            entry["api_base"] = api_base
        if default_model is not None:
            entry["default_model"] = default_model
        config[provider_name] = entry
        _write_config(config)


def resolve_api_key(env_key: str, provider_name: str) -> str:
    """解析 API Key：先查 env var，再查 config 文件。"""
    env_val = os.getenv(env_key, "")
    if env_val:
        return env_val
    config = get_provider_config(provider_name)
    return config.get("api_key", "")


def resolve_base_url(
    env_base_url_key: str,
    provider_name: str,
    default_base_url: str,
) -> str:
    """解析 Base URL：先查 env var，再查 config 文件，最后用默认值。"""
    env_val = os.getenv(env_base_url_key, "")
    if env_val:
        return env_val.rstrip("/")
    config = get_provider_config(provider_name)
    config_url = config.get("api_base", "")
    if config_url:
        return config_url.rstrip("/")
    return default_base_url.rstrip("/")


def list_all_configs() -> dict:
    """列出所有已保存的配置（屏蔽 api_key 值，只显示是否已设置）。"""
    config = _read_config()
    safe = {}
    for name, entry in config.items():
        safe[name] = {
            "has_api_key": bool(entry.get("api_key")),
            "api_base": entry.get("api_base", ""),
            "default_model": entry.get("default_model", ""),
        }
    return safe
