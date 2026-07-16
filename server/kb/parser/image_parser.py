# server/kb/parser/image_parser.py
"""图片解析器（降级占位，待多模态 API 启用）"""
from __future__ import annotations
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult


class ImageParser:
    """图片解析器 - 当前仅降级占位"""

    def __init__(self, vl_api_client=None):
        self.vl_api_client = vl_api_client

    def parse(self, file_path: Path | str) -> ParseResult:
        if self.vl_api_client:
            return self.parse_with_vl(file_path)
        return self._parse_degraded(file_path)

    def _parse_degraded(self, file_path: Path | str) -> ParseResult:
        path = Path(file_path) if not isinstance(file_path, Path) else file_path
        filename = path.name if path.exists() else str(file_path)
        content = f"![image]({filename}) <!-- 待多模态解析 -->"
        return ParseResult(
            True, content, 0.3, "image_degraded",
            assets=[str(path)] if path.exists() else [],
        )

    def parse_with_vl(self, file_path: Path | str) -> ParseResult:
        raise NotImplementedError("多模态解析未配置")
