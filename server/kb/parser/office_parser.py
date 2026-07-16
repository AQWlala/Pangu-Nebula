# server/kb/parser/office_parser.py
"""Office 文档解析器（Excel/Word → Markdown）"""
from __future__ import annotations
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult


class ExcelParser:
    """Excel→Markdown 解析器（Pandas）"""

    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        try:
            import pandas as pd
        except ImportError:
            return ParseResult(False, "", 0.0, "excel", "pandas 未安装")

        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            return ParseResult(False, "", 0.0, "excel", str(e))

        md_parts = []
        total_cells = 0
        converted_cells = 0

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            md_parts.append(f"## {sheet_name}\n")
            if df.empty:
                md_parts.append("*(空表)*\n")
                continue

            headers = df.columns.tolist()
            md_parts.append("| " + " | ".join(str(h) for h in headers) + " |")
            md_parts.append("| " + " | ".join("---" for _ in headers) + " |")

            for _, row in df.iterrows():
                cells = []
                for val in row:
                    total_cells += 1
                    if pd.isna(val):
                        cells.append("")
                    else:
                        cells.append(str(val))
                        converted_cells += 1
                md_parts.append("| " + " | ".join(cells) + " |")
            md_parts.append("")

        if total_cells == 0:
            confidence = 0.5  # Empty table, moderate confidence
        else:
            ratio = converted_cells / total_cells
            if ratio >= 0.95:
                confidence = 0.95
            elif ratio >= 0.8:
                confidence = 0.85
            elif ratio >= 0.5:
                confidence = 0.7
            else:
                confidence = 0.5
        return ParseResult(True, "\n".join(md_parts), confidence, "excel")


class WordParser:
    """Word→Markdown 解析器（python-docx）"""

    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        try:
            from docx import Document
        except ImportError:
            return ParseResult(False, "", 0.0, "word", "python-docx 未安装")

        try:
            doc = Document(str(file_path))
        except Exception as e:
            return ParseResult(False, "", 0.0, "word", str(e))

        md_parts = []
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading"):
                level = int(para.style.name.split()[-1]) if para.style.name[-1].isdigit() else 1
                md_parts.append(f"{'#' * (level + 1)} {para.text}")
            elif para.text.strip():
                md_parts.append(para.text)
            else:
                md_parts.append("")

        return ParseResult(True, "\n".join(md_parts), 0.85, "word")
