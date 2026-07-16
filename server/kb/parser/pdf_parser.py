# server/kb/parser/pdf_parser.py
"""PDF 解析器（Marker + pypdf 降级）"""
from __future__ import annotations
import logging
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult

logger = logging.getLogger(__name__)


class PdfParser:
    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if not file_path.exists():
            return ParseResult(False, "", 0.0, "pdf", f"文件不存在: {file_path}")

        try:
            return self._parse_with_marker(file_path)
        except Exception as e:
            logger.warning(f"Marker PDF parser failed, falling back to pypdf: {e}")

        try:
            return self._parse_with_pypdf(file_path)
        except Exception as e:
            return ParseResult(False, "", 0.0, "pdf", f"PDF 解析失败: {e}")

    def _parse_with_marker(self, file_path: Path) -> ParseResult:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(file_path))
        return ParseResult(True, rendered.markdown, 0.9, "pdf_marker")

    def _parse_with_pypdf(self, file_path: Path) -> ParseResult:
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return ParseResult(True, "\n\n".join(text_parts), 0.5, "pdf_pypdf")
