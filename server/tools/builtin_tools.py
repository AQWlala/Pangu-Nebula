import os

import httpx

from .registry import BaseTool, ToolResult, register_tool


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

    async def execute(self, path: str, encoding: str = "utf-8", **kwargs) -> ToolResult:
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

    async def execute(
        self, path: str, content: str, append: bool = False, encoding: str = "utf-8", **kwargs
    ) -> ToolResult:
        try:
            mode = "a" if append else "w"
            with open(path, mode, encoding=encoding) as f:
                f.write(content)
            return ToolResult(success=True, output=f"Wrote {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))
