import os

import httpx

from ..services.path_guard import PathGuard
from .registry import BaseTool, ToolResult, register_tool


def _build_path_guard(persona) -> PathGuard:
    """根据 persona 配置构建 PathGuard

    persona 通过 tool_executor 的 kwargs 注入; 无 persona 或未配置 allowed_paths
    时回退到默认白名单, 保持向后兼容。
    """
    allowed = getattr(persona, "allowed_paths", None) if persona is not None else None
    if allowed:
        return PathGuard(list(allowed))
    return PathGuard(PathGuard.default_allowed_paths())


@register_tool("web_search")
class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for information. Returns a list of results with title, url and snippet."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    # v2.2.1 F5: 仅允许这两个参数,LLM 注入 allow_network 等会被过滤
    allowed_kwargs: set[str] = {"query", "max_results"}

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        api_key = os.getenv("WEB_SEARCH_API_KEY", "")
        endpoint = os.getenv("WEB_SEARCH_ENDPOINT", "https://api.duckduckgo.com/")
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(endpoint, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            results: list[dict] = []
            if isinstance(data, dict):
                if data.get("AbstractText"):
                    results.append(
                        {
                            "title": data.get("Heading", ""),
                            "url": data.get("AbstractURL", ""),
                            "snippet": data.get("AbstractText", ""),
                        }
                    )
                for topic in data.get("RelatedTopics", [])[: max_results - 1]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append(
                            {
                                "title": topic.get("Text", "")[:80],
                                "url": topic.get("FirstURL", ""),
                                "snippet": topic.get("Text", ""),
                            }
                        )
            return ToolResult(success=True, output=str(results))
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))


@register_tool("file_read")
class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read the content of a local file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative path to the file"},
            "encoding": {"type": "string", "description": "File encoding", "default": "utf-8"},
        },
        "required": ["path"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"path", "encoding"}

    async def execute(self, path: str, encoding: str = "utf-8", **kwargs) -> ToolResult:
        # v2.2.1 F1: PathGuard 路径白名单校验, 防止路径穿越读取敏感文件
        guard = _build_path_guard(kwargs.get("persona"))
        ok, reason = guard.validate(path, write=False)
        if not ok:
            return ToolResult(success=False, output="", error=f"PathGuard 拒绝: {reason}")
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return ToolResult(success=True, output=content)
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))


@register_tool("file_write")
class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Write content to a local file. Creates the file if it does not exist, overwrites if it does."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative path to the file"},
            "content": {"type": "string", "description": "Content to write"},
            "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False},
            "encoding": {"type": "string", "description": "File encoding", "default": "utf-8"},
        },
        "required": ["path", "content"],
    }
    # v2.2.1 F5
    allowed_kwargs: set[str] = {"path", "content", "append", "encoding"}

    async def execute(
        self, path: str, content: str, append: bool = False, encoding: str = "utf-8", **kwargs
    ) -> ToolResult:
        # v2.2.1 F1: PathGuard 路径白名单校验, 防止路径穿越写入系统/敏感文件
        guard = _build_path_guard(kwargs.get("persona"))
        ok, reason = guard.validate(path, write=True)
        if not ok:
            return ToolResult(success=False, output="", error=f"PathGuard 拒绝: {reason}")
        try:
            mode = "a" if append else "w"
            with open(path, mode, encoding=encoding) as f:
                f.write(content)
            return ToolResult(success=True, output=f"Wrote {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))
