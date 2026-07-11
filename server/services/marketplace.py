"""技能市场服务

负责 SKILL.md 标准格式的导入导出,以及市场技能列表。

SKILL.md 格式 = YAML front-matter + Markdown 正文:
    ---
    name: skill-name
    description: 技能描述
    category: development
    type: prompt
    version: 1.0.0
    author: Pangu Nebula
    variables: var1, var2, var3
    tags: tag1, tag2
    created_at: 2026-07-11
    ---

    # 技能名称

    正文内容...
"""

from datetime import date
from pathlib import Path

from .skill_loader import SkillLoader


class SkillMarketplace:
    """技能市场服务,负责 SKILL.md 格式的导入导出与市场列表"""

    def __init__(self, loader: SkillLoader | None = None, custom_dir: str = "data/skills"):
        self.loader = loader or SkillLoader()
        self.custom_dir = Path(custom_dir)

    def parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """解析 YAML front-matter(简单实现,不依赖 pyyaml)

        支持:
        - key: value           单值
        - key: v1, v2, v3      逗号分隔列表

        返回 (metadata_dict, body_text)
        """
        metadata: dict = {}
        body = content
        # 仅在以 --- 开头时尝试解析
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                # 去掉 frontmatter 后的正文
                body = content[end + 3:].lstrip("\n")
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if "," in value:
                        # 含逗号则视为列表
                        items = [v.strip() for v in value.split(",") if v.strip()]
                        metadata[key] = items
                    else:
                        metadata[key] = value
        return metadata, body

    def build_frontmatter(self, metadata: dict) -> str:
        """将 dict 构建为 YAML front-matter 字符串

        列表类型用逗号分隔;None 值跳过
        """
        lines = ["---"]
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)

    async def export_skill(self, skill_name: str) -> str:
        """导出技能为标准 SKILL.md 格式字符串

        通过 SkillLoader 加载技能,解析现有 frontmatter,
        重新生成标准格式并返回完整 markdown 文本
        """
        skill = await self.loader.load_skill(skill_name)
        if not skill:
            raise FileNotFoundError(f"Skill not found: {skill_name}")

        # 解析现有 frontmatter 与正文
        existing_meta, body = self.parse_frontmatter(skill.content)

        # 构建标准元数据,保留已有字段并补全默认值
        tags = skill.tags
        if not tags:
            existing_tags = existing_meta.get("tags")
            tags = existing_tags if isinstance(existing_tags, list) else []

        metadata: dict = {
            "name": skill.name,
            "description": skill.description or existing_meta.get("description", ""),
            "category": existing_meta.get("category", "general"),
            "type": existing_meta.get("type", "prompt"),
            "version": existing_meta.get("version", "1.0.0"),
            "author": existing_meta.get("author", "Pangu Nebula"),
            "tags": tags,
            "created_at": existing_meta.get("created_at", str(date.today())),
        }
        # 仅在存在变量时写入,避免空字段
        variables = existing_meta.get("variables")
        if variables:
            metadata["variables"] = variables

        frontmatter = self.build_frontmatter(metadata)
        # 组装最终文本:frontmatter + 空行 + 正文
        return f"{frontmatter}\n\n{body}".rstrip() + "\n"

    async def import_from_markdown(self, content: str, overwrite: bool = False) -> dict:
        """从 SKILL.md 内容导入技能

        解析 frontmatter,提取所有字段与正文,
        写入 data/skills/{name}.md,返回导入的技能信息
        """
        metadata, _body = self.parse_frontmatter(content)
        name = metadata.get("name")
        if not name:
            raise ValueError("SKILL.md missing required 'name' field in frontmatter")
        if not isinstance(name, str):
            raise ValueError("'name' field must be a string")

        self.custom_dir.mkdir(parents=True, exist_ok=True)
        dest = self.custom_dir / f"{name}.md"

        if dest.exists() and not overwrite:
            raise FileExistsError(
                f"Skill '{name}' already exists, use overwrite=True to replace"
            )

        # 写入完整内容(保留 frontmatter + body)
        dest.write_text(content, encoding="utf-8")

        # 清除缓存以便后续重新加载
        self.loader._cache.pop(name, None)

        # 规范化 tags 为列表
        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []

        return {
            "name": name,
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "general"),
            "type": metadata.get("type", "prompt"),
            "version": metadata.get("version", "1.0.0"),
            "author": metadata.get("author", ""),
            "tags": tags,
            "source": "custom",
            "path": str(dest),
        }

    async def list_marketplace(self) -> list[dict]:
        """列出所有可分享技能(builtin + custom)

        返回每个技能的: name, description, category, type, version, author, tags, source
        """
        skills = await self.loader.scan_all()
        result: list[dict] = []
        for skill in skills:
            # 仅展示可分享的内置与自定义技能
            if skill.source not in ("builtin", "custom"):
                continue
            meta, _ = self.parse_frontmatter(skill.content)

            # tags 优先取 SkillLoader 解析结果,其次取 frontmatter
            tags = skill.tags
            if not tags:
                meta_tags = meta.get("tags")
                tags = meta_tags if isinstance(meta_tags, list) else []

            result.append({
                "name": skill.name,
                "description": skill.description or meta.get("description", ""),
                "category": meta.get("category", "general"),
                "type": meta.get("type", "prompt"),
                "version": meta.get("version", "1.0.0"),
                "author": meta.get("author", ""),
                "tags": tags,
                "source": skill.source,
            })
        return result
