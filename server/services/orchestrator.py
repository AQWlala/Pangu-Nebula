from typing import Any, Callable

from ..tools.registry import BaseTool, ToolResult, get_tool, list_tools


class HookEngine:
    def __init__(self):
        self._pre_hooks: dict[str, list[Callable]] = {}
        self._post_hooks: dict[str, list[Callable]] = {}

    def add_pre_hook(self, event: str, fn: Callable) -> None:
        self._pre_hooks.setdefault(event, []).append(fn)

    def add_post_hook(self, event: str, fn: Callable) -> None:
        self._post_hooks.setdefault(event, []).append(fn)

    async def run_pre(self, event: str, context: dict) -> None:
        for fn in self._pre_hooks.get(event, []):
            res = fn(context)
            if hasattr(res, "__await__"):
                await res

    async def run_post(self, event: str, context: dict, result: Any) -> None:
        for fn in self._post_hooks.get(event, []):
            res = fn(context, result)
            if hasattr(res, "__await__"):
                await res


class Confirmer:
    async def confirm(self, tool_name: str, params: dict) -> bool:
        return True


class Orchestrator:
    def __init__(self, tool_registry=None, confirmer: Confirmer | None = None, hooks: HookEngine | None = None):
        self.tool_registry = tool_registry
        self.confirmer = confirmer or Confirmer()
        self.hooks = hooks or HookEngine()

    def _resolve_tool(self, tool_name: str) -> BaseTool:
        if self.tool_registry is not None:
            if hasattr(self.tool_registry, "get_tool"):
                return self.tool_registry.get_tool(tool_name)
            if isinstance(self.tool_registry, dict):
                cls = self.tool_registry[tool_name]
                return cls() if isinstance(cls, type) else cls
        return get_tool(tool_name)

    async def execute_single(self, tool_name: str, params: dict) -> ToolResult:
        context = {"tool_name": tool_name, "params": params}
        await self.hooks.run_pre("tool_call", context)

        allowed = await self.confirmer.confirm(tool_name, params)
        if not allowed:
            result = ToolResult(success=False, output="", error=f"Tool '{tool_name}' denied by confirmer")
            await self.hooks.run_post("tool_call", context, result)
            return result

        try:
            tool = self._resolve_tool(tool_name)
            result = await tool.execute(**params)
        except Exception as exc:
            result = ToolResult(success=False, output="", error=str(exc))

        await self.hooks.run_post("tool_call", context, result)
        return result

    async def execute_tool_calls(self, tool_calls: list[dict]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            tool_name = call.get("name") or call.get("tool") or ""
            params = call.get("parameters") or call.get("arguments") or {}
            if not tool_name:
                results.append(ToolResult(success=False, output="", error="Missing tool name"))
                continue
            result = await self.execute_single(tool_name, params)
            results.append(result)
        return results

    def available_tools(self) -> list[dict]:
        if self.tool_registry is not None and hasattr(self.tool_registry, "list_tools"):
            return self.tool_registry.list_tools()
        return list_tools()
