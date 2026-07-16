# server/kb/parser/validator.py
"""Front Matter 校验器"""
from server.kb.storage.frontmatter import FrontMatter

VALID_TYPES = {"note", "doc", "snippet", "cu_log"}
VALID_SCOPES = {"private", "project", "public"}
VALID_SOURCE_TYPES = {"manual", "import", "cu", "crawler"}
VALID_RELATION_TYPES = {"references", "extends", "contradicts", "derived_from"}


class ValidationError(ValueError):
    """校验错误"""


def validate_frontmatter(fm: FrontMatter) -> None:
    """校验 front matter 完整性"""
    if not fm.id:
        raise ValidationError("id 不能为空")
    if not fm.title:
        raise ValidationError("title 不能为空")
    if fm.type not in VALID_TYPES:
        raise ValidationError(f"type 必须是 {VALID_TYPES} 之一，得到: {fm.type}")
    if fm.scope not in VALID_SCOPES:
        raise ValidationError(f"scope 必须是 {VALID_SCOPES} 之一，得到: {fm.scope}")
    if fm.source_type not in VALID_SOURCE_TYPES:
        raise ValidationError(f"source.type 必须是 {VALID_SOURCE_TYPES} 之一，得到: {fm.source_type}")
    if not 0.0 <= fm.confidence <= 1.0:
        raise ValidationError(f"confidence 必须在 [0.0, 1.0] 范围内，得到: {fm.confidence}")
    if not fm.checksum:
        raise ValidationError("checksum 不能为空")

    for i, rel in enumerate(fm.relations):
        if "target" not in rel:
            raise ValidationError(f"relations[{i}] 缺少 target 字段")
        if rel.get("type") not in VALID_RELATION_TYPES:
            raise ValidationError(f"relations[{i}].type 必须是 {VALID_RELATION_TYPES} 之一")
