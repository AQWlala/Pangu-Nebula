from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...


_tool_registry: dict[str, type[BaseTool]] = {}


def register_tool(name: str):
    def decorator(cls: type[BaseTool]):
        _tool_registry[name] = cls
        cls.name = name
        return cls

    return decorator


def get_tool(name: str) -> BaseTool:
    if name not in _tool_registry:
        raise ValueError(f"Tool '{name}' not registered")
    return _tool_registry[name]()


def list_tools() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in (cls() for cls in _tool_registry.values())
    ]


def list_tools_schema() -> list[dict]:
    """v2.2.0: 返回 OpenAI function calling 格式的 tools schema。

    用于注入 provider 请求体的 `tools` 字段,让 LLM 在对话中发起工具调用。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in (cls() for cls in _tool_registry.values())
    ]


def is_registered(name: str) -> bool:
    return name in _tool_registry
