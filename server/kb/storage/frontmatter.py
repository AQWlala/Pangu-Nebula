# server/kb/storage/frontmatter.py
"""YAML Front Matter 解析与序列化"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import yaml


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class FrontMatter:
    """文档 front matter 结构"""
    id: str = ""
    title: str = ""
    type: str = "note"
    scope: str = "private"
    source_type: str = "manual"
    source_original_path: str = ""
    source_imported_at: str = ""
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    confidence: float = 1.0
    checksum: str = ""
    created_at: str = ""
    updated_at: str = ""


def parse_frontmatter(content: str) -> tuple[FrontMatter | None, str]:
    """解析 MD 内容，返回 (frontmatter, body)"""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    yaml_str, body = match.groups()
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError:
        return None, content

    if not isinstance(data, dict):
        return None, content

    source = data.get("source", {}) or {}
    fm = FrontMatter(
        id=data.get("id", ""),
        title=data.get("title", ""),
        type=data.get("type", "note"),
        scope=data.get("scope", "private"),
        source_type=source.get("type", "manual") if isinstance(source, dict) else "manual",
        source_original_path=source.get("original_path", "") if isinstance(source, dict) else "",
        source_imported_at=source.get("imported_at", "") if isinstance(source, dict) else "",
        tags=data.get("tags", []) or [],
        categories=data.get("categories", []) or [],
        relations=data.get("relations", []) or [],
        confidence=float(data.get("confidence", 1.0)),
        checksum=data.get("checksum", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )
    return fm, body


def dump_frontmatter(fm: FrontMatter) -> str:
    """序列化 front matter 为 YAML 字符串"""
    source = {
        "type": fm.source_type,
        "original_path": fm.source_original_path,
        "imported_at": fm.source_imported_at,
    }
    data = {
        "id": fm.id,
        "title": fm.title,
        "type": fm.type,
        "source": source,
        "scope": fm.scope,
        "tags": fm.tags,
        "categories": fm.categories,
        "relations": fm.relations,
        "confidence": fm.confidence,
        "checksum": fm.checksum,
    }
    if fm.created_at:
        data["created_at"] = fm.created_at
    if fm.updated_at:
        data["updated_at"] = fm.updated_at

    yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_str}---"
