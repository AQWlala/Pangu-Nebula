from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import shutil


@dataclass
class Skill:
    name: str
    description: str
    source: str
    path: str
    content: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


class SkillSource(ABC):
    @abstractmethod
    async def scan(self) -> list[Skill]: ...

    @abstractmethod
    async def load(self, name: str) -> Skill | None: ...


class _MarkdownSource(SkillSource):
    def __init__(self, base_dir: str, source_tag: str):
        self.base_dir = Path(base_dir)
        self._source_tag = source_tag

    def _parse(self, f: Path) -> Skill:
        content = f.read_text(encoding="utf-8")
        name = f.stem
        description = ""
        tags: list[str] = []
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                for line in frontmatter.split("\n"):
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                    elif line.startswith("tags:"):
                        tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
        return Skill(
            name=name,
            description=description,
            source=self._source_tag,
            path=str(f),
            content=content,
            tags=tags,
        )

    async def scan(self) -> list[Skill]:
        if not self.base_dir.exists():
            return []
        return [self._parse(f) for f in self.base_dir.glob("*.md")]

    async def load(self, name: str) -> Skill | None:
        f = self.base_dir / f"{name}.md"
        if not f.exists():
            return None
        return self._parse(f)


class BuiltinSource(_MarkdownSource):
    def __init__(self, base_dir: str = "server/skills"):
        super().__init__(base_dir, "builtin")


class CustomSource(_MarkdownSource):
    def __init__(self, base_dir: str = "data/skills"):
        super().__init__(base_dir, "custom")


class ExtensionSource(SkillSource):
    def __init__(self):
        self.entry_points = []
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="pangu.skills")
            self.entry_points = list(eps)
        except Exception:
            pass

    async def scan(self) -> list[Skill]:
        skills = []
        for ep in self.entry_points:
            try:
                cls = ep.load()
                instance = cls()
                if hasattr(instance, "get_skill_info"):
                    info = instance.get_skill_info()
                    skills.append(Skill(
                        name=info["name"],
                        description=info.get("description", ""),
                        source="extension",
                        path=ep.value,
                        content=info.get("content", ""),
                    ))
            except Exception:
                pass
        return skills

    async def load(self, name: str) -> Skill | None:
        for ep in self.entry_points:
            if ep.name != name:
                continue
            try:
                cls = ep.load()
                instance = cls()
                if hasattr(instance, "get_skill_info"):
                    info = instance.get_skill_info()
                    return Skill(
                        name=info["name"],
                        description=info.get("description", ""),
                        source="extension",
                        path=ep.value,
                        content=info.get("content", ""),
                    )
            except Exception:
                pass
        return None


class SkillLoader:
    def __init__(self):
        self.sources: list[SkillSource] = [
            BuiltinSource(),
            CustomSource(),
            ExtensionSource(),
        ]
        self._cache: dict[str, Skill] = {}

    async def scan_all(self) -> list[Skill]:
        all_skills = []
        for source in self.sources:
            skills = await source.scan()
            all_skills.extend(skills)
        for skill in all_skills:
            self._cache[skill.name] = skill
        return all_skills

    async def load_skill(self, name: str) -> Skill | None:
        if name in self._cache:
            return self._cache[name]
        for source in self.sources:
            skill = await source.load(name)
            if skill:
                self._cache[name] = skill
                return skill
        return None

    async def import_skill(self, path: str) -> Skill:
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")
        dest_dir = Path("data/skills")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(str(src), str(dest))
        content = dest.read_text(encoding="utf-8")
        skill = Skill(name=src.stem, description="", source="custom", path=str(dest), content=content)
        self._cache[skill.name] = skill
        return skill

    async def delete_skill(self, name: str) -> bool:
        f = Path("data/skills") / f"{name}.md"
        if not f.exists():
            return False
        f.unlink()
        self._cache.pop(name, None)
        return True

    def _build_skill_markdown(
        self,
        name: str,
        description: str,
        category: str,
        prompt_template: str,
        tags: list[str],
    ) -> str:
        """根据字段构建技能 markdown 内容(frontmatter + body)"""
        tag_str = ", ".join(tags) if tags else ""
        lines = ["---", f"name: {name}"]
        if description:
            lines.append(f"description: {description}")
        if category:
            lines.append(f"category: {category}")
        if tag_str:
            lines.append(f"tags: {tag_str}")
        lines.append("---")
        lines.append("")
        lines.append(prompt_template)
        return "\n".join(lines)

    async def create_skill(
        self,
        name: str,
        description: str,
        category: str,
        prompt_template: str,
        tags: list[str],
    ) -> Skill:
        """创建新技能,写入 data/skills/{name}.md;若已存在则抛出 FileExistsError"""
        dest_dir = Path("data/skills")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{name}.md"
        if dest.exists():
            raise FileExistsError(f"Skill already exists: {name}")
        content = self._build_skill_markdown(name, description, category, prompt_template, tags)
        dest.write_text(content, encoding="utf-8")
        skill = Skill(
            name=name,
            description=description,
            source="custom",
            path=str(dest),
            content=content,
            tags=tags,
        )
        self._cache[name] = skill
        return skill

    async def update_skill(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        prompt_template: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        """更新技能内容;读取现有技能合并字段后写入 data/skills/{name}.md

        若技能不存在(任何来源)抛出 FileNotFoundError。
        """
        existing = await self.load_skill(name)
        if not existing:
            raise FileNotFoundError(f"Skill not found: {name}")

        # 解析现有 frontmatter 获取当前字段
        from .skill_engine import PromptSkillEngine
        engine = PromptSkillEngine(self)
        parsed = engine.parse_markdown(existing.content)
        fm = parsed["frontmatter"]
        cur_description = fm.get("description", existing.description)
        cur_category = fm.get("category", "general")
        cur_tags = fm.get("tags", existing.tags)
        cur_template = parsed["body"].strip() or fm.get("prompt_template", "")

        # 合并更新(仅覆盖非 None 字段)
        new_description = description if description is not None else cur_description
        new_category = category if category is not None else cur_category
        new_tags = tags if tags is not None else cur_tags
        new_template = prompt_template if prompt_template is not None else cur_template

        dest_dir = Path("data/skills")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{name}.md"
        content = self._build_skill_markdown(name, new_description, new_category, new_template, new_tags)
        dest.write_text(content, encoding="utf-8")
        skill = Skill(
            name=name,
            description=new_description,
            source="custom",
            path=str(dest),
            content=content,
            tags=new_tags,
        )
        self._cache[name] = skill
        return skill
