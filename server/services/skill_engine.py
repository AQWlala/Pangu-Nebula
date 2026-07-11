"""提示词技能模板引擎 (Phase 5A)

支持 {{variable}} 和 {{variable|default:"xxx"}} 占位符语法,
解析技能 markdown frontmatter,渲染 prompt_template。
"""

from __future__ import annotations

import re
from typing import Any

from .skill_loader import SkillLoader, Skill


class PromptSkillEngine:
    """提示词技能模板引擎

    支持 ``{{variable}}`` 占位符替换与 ``{{variable|default:"xxx"}}`` 默认值语法。
    技能 markdown 的 frontmatter 可包含字段:
    name, description, category, prompt_template, variables(逗号分隔), tags。
    prompt_template 优先取 body 正文(支持多行),其次取 frontmatter 中的单行值。
    """

    # 匹配 {{variable}} 或 {{variable|default:"value"}} 或 {{variable|default:'value'}}
    # group(1)=变量名, group(2)=引号字符(可为空), group(3)=默认值(可为None)
    _VAR_PATTERN = re.compile(
        r"\{\{\s*(\w+)\s*"
        r"(?:\|\s*default\s*:\s*([\"']?)([^\"'}]*)\2\s*)?"
        r"\}\}"
    )

    def __init__(self, loader: SkillLoader | None = None):
        self.loader = loader or SkillLoader()

    # ------------------------------------------------------------------
    # 模板渲染核心
    # ------------------------------------------------------------------

    def render_template(self, template: str, variables: dict) -> str:
        """渲染模板,替换 {{variable}} 占位符,支持默认值语法

        - 变量已提供时使用提供的值
        - 变量未提供但有默认值时使用默认值
        - 变量未提供且无默认值时保留原占位符
        """

        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            default_value = match.group(3)  # 无默认值时为 None
            if variables and var_name in variables and variables[var_name] is not None:
                return str(variables[var_name])
            if default_value is not None:
                return default_value
            # 变量未提供且无默认值,保留原占位符
            return match.group(0)

        return self._VAR_PATTERN.sub(_replace, template)

    def extract_variables(self, template: str) -> list[str]:
        """提取模板中所有变量名(去重保序)"""
        seen: set[str] = set()
        result: list[str] = []
        for match in self._VAR_PATTERN.finditer(template):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def validate_variables(self, template: str, provided: dict) -> list[str]:
        """返回缺失的必需变量名(无默认值且未提供的变量)"""
        missing: list[str] = []
        provided_keys = set(provided.keys()) if provided else set()
        for match in self._VAR_PATTERN.finditer(template):
            var_name = match.group(1)
            has_default = match.group(3) is not None
            if has_default:
                continue  # 有默认值,非必需
            if var_name not in provided_keys and var_name not in missing:
                missing.append(var_name)
        return missing

    # ------------------------------------------------------------------
    # 技能 markdown 解析
    # ------------------------------------------------------------------

    def parse_markdown(self, content: str) -> dict[str, Any]:
        """解析技能 markdown,返回 frontmatter 字段字典和 body 正文"""
        frontmatter: dict[str, Any] = {}
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm_text = content[3:end].strip()
                body = content[end + 3:].lstrip("\n")
                for line in fm_text.split("\n"):
                    if ":" not in line:
                        continue
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if not key:
                        continue
                    if key in ("variables", "tags"):
                        frontmatter[key] = [v.strip() for v in value.split(",") if v.strip()]
                    else:
                        frontmatter[key] = value
        return {"frontmatter": frontmatter, "body": body}

    def _get_prompt_template(self, skill: Skill) -> str:
        """从技能中提取 prompt_template,body 正文优先"""
        parsed = self.parse_markdown(skill.content)
        body = parsed["body"].strip()
        if body:
            return body
        # body 为空时回退到 frontmatter 中的 prompt_template(单行)
        return parsed["frontmatter"].get("prompt_template", "")

    # ------------------------------------------------------------------
    # 技能执行
    # ------------------------------------------------------------------

    async def execute_skill(self, skill_name: str, variables: dict) -> dict[str, Any]:
        """加载技能 → 提取 prompt_template → 渲染 → 返回渲染后的 prompt

        返回字典包含: skill_name, prompt(渲染后), variables(模板变量列表)
        若技能不存在抛出 FileNotFoundError;缺少必需变量抛出 ValueError。
        """
        skill = await self.loader.load_skill(skill_name)
        if not skill:
            raise FileNotFoundError(f"Skill not found: {skill_name}")

        template = self._get_prompt_template(skill)
        if not template:
            raise ValueError(f"Skill '{skill_name}' has no prompt_template")

        missing = self.validate_variables(template, variables or {})
        if missing:
            raise ValueError(f"Missing required variables: {', '.join(missing)}")

        rendered = self.render_template(template, variables or {})
        return {
            "skill_name": skill_name,
            "prompt": rendered,
            "variables": self.extract_variables(template),
        }
