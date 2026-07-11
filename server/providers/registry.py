from typing import Any

from .base import BaseProvider

_registry: dict[str, type[BaseProvider]] = {}


def register_provider(name: str):
    def decorator(cls: type[BaseProvider]):
        _registry[name] = cls
        cls.name = name
        return cls

    return decorator


def get_provider(name: str) -> BaseProvider:
    if name not in _registry:
        raise ValueError(f"Provider '{name}' not registered")
    return _registry[name]()


def list_providers() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    for name, cls in _registry.items():
        try:
            instance = cls()
            providers.append(instance.info())
        except Exception:
            providers.append(
                {
                    "name": name,
                    "capabilities": {},
                    "supported_models": [],
                    "available": False,
                }
            )
    return providers


def get_provider_info(name: str) -> dict[str, Any] | None:
    if name not in _registry:
        return None
    cls = _registry[name]
    try:
        return cls().info()
    except Exception:
        return None


def is_registered(name: str) -> bool:
    return name in _registry
