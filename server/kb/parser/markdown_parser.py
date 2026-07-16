# server/kb/parser/markdown_parser.py
"""Markdown/TXT 解析器"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    content: str
    confidence: float
    parser_name: str
    error: str = ""
    assets: list[str] = field(default_factory=list)


class MarkdownParser:
    """Markdown/纯文本解析器（直接透传）"""

    def parse(self, content: str | Path) -> ParseResult:
        if isinstance(content, Path):
            try:
                text = content.read_text(encoding="utf-8")
            except Exception as e:
                return ParseResult(False, "", 0.0, "markdown", str(e))
        else:
            text = content

        confidence = 0.95 if text.strip().startswith("#") else 0.85
        return ParseResult(True, text, confidence, "markdown")
