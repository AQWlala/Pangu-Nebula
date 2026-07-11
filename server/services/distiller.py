"""自进化技能蒸馏引擎(Phase 5C)。

从历史任务记录中提取可复用模式:
- 连续多次成功 → 蒸馏为可复用技能(需人工确认后写入 data/skills/)
- 连续多次失败 → 生成教训记录,辅助后续避坑
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, desc

from ..db.engine import async_session
from ..db.orm import TaskRecord as TaskRecordORM
from ..providers.base import Message
from ..providers.registry import get_provider, is_registered


@dataclass
class DistillResult:
    """蒸馏结果"""

    success: bool
    skill_name: str | None = None
    skill_content: str | None = None
    lesson: str | None = None
    reason: str = ""


@dataclass
class TaskRecord:
    """供蒸馏分析使用的任务记录(与 ORM 模型字段对应,不含持久化字段)"""

    task_type: str
    description: str
    inputs: dict = field(default_factory=dict)
    output: str | None = None
    success: bool = False
    iterations: int = 1
    persona_id: int | None = None


def _orm_to_record(row: TaskRecordORM) -> TaskRecord:
    """ORM 行转换为蒸馏用 dataclass"""
    return TaskRecord(
        task_type=row.task_type,
        description=row.description,
        inputs=row.inputs or {},
        output=row.output,
        success=bool(row.success),
        iterations=row.iterations,
        persona_id=row.persona_id,
    )


class SkillDistiller:
    """技能蒸馏器:分析任务记录,提取技能或教训"""

    # 连续N次相似任务成功/失败才触发蒸馏
    CONSECUTIVE_THRESHOLD = 3
    # 技能写入目录
    _SKILLS_DIR = Path("data/skills")

    def __init__(self, provider_name: str = "openai", model: str = "gpt-4o-mini"):
        self.provider_name = provider_name
        self.model = model

    async def distill_from_success(self, records: list[TaskRecord]) -> DistillResult:
        """从多个成功任务中提取可复用模式,生成技能定义(不自动写入,等待人工确认)"""
        if not records:
            return DistillResult(success=False, reason="没有可蒸馏的成功记录")
        if not is_registered(self.provider_name):
            return DistillResult(success=False, reason=f"Provider '{self.provider_name}' 未注册")

        provider = get_provider(self.provider_name)
        prompt = self._build_distill_prompt(records, success=True)
        messages = [Message(role="user", content=prompt)]

        chunks: list[str] = []
        async for chunk in provider.generate(messages, self.model):
            chunks.append(chunk)
        raw = "".join(chunks).strip()

        try:
            data = self._parse_llm_json(raw)
        except json.JSONDecodeError as e:
            return DistillResult(success=False, reason=f"LLM 返回 JSON 解析失败: {e}")

        skill_name = (data.get("skill_name") or "").strip()
        if not skill_name:
            return DistillResult(success=False, reason="LLM 未返回有效的 skill_name")

        description = data.get("description", "")
        prompt_template = data.get("prompt_template", "")
        variables = data.get("variables", []) or []
        tags = data.get("tags", []) or []

        skill_content = self._format_skill_markdown(
            skill_name, description, prompt_template, variables, tags
        )
        return DistillResult(
            success=True,
            skill_name=skill_name,
            skill_content=skill_content,
            reason="成功蒸馏出可复用技能,等待人工确认",
        )

    async def distill_from_failure(self, records: list[TaskRecord]) -> DistillResult:
        """从失败任务中分析原因,生成教训记录(关联到任务类型)"""
        if not records:
            return DistillResult(success=False, reason="没有可分析的失败记录")
        if not is_registered(self.provider_name):
            return DistillResult(success=False, reason=f"Provider '{self.provider_name}' 未注册")

        provider = get_provider(self.provider_name)
        prompt = self._build_lesson_prompt(records)
        messages = [Message(role="user", content=prompt)]

        chunks: list[str] = []
        async for chunk in provider.generate(messages, self.model):
            chunks.append(chunk)
        raw = "".join(chunks).strip()

        try:
            data = self._parse_llm_json(raw)
        except json.JSONDecodeError as e:
            return DistillResult(success=False, reason=f"LLM 返回 JSON 解析失败: {e}")

        lesson = (data.get("lesson") or "").strip()
        if not lesson:
            return DistillResult(success=False, reason="LLM 未返回有效的 lesson")

        return DistillResult(
            success=True,
            lesson=lesson,
            reason="成功生成失败教训",
        )

    async def check_and_distill(
        self, task_type: str, persona_id: int | None = None
    ) -> DistillResult | None:
        """检查最近N次同类任务的成功/失败模式,满足阈值则触发蒸馏,否则返回None"""
        async with async_session() as session:
            stmt = select(TaskRecordORM).where(TaskRecordORM.task_type == task_type)
            if persona_id is not None:
                stmt = stmt.where(TaskRecordORM.persona_id == persona_id)
            stmt = stmt.order_by(desc(TaskRecordORM.created_at)).limit(self.CONSECUTIVE_THRESHOLD)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        # 记录数不足阈值,不触发
        if len(rows) < self.CONSECUTIVE_THRESHOLD:
            return None

        # 按时间正序排列(最旧的在前),便于判断"连续"
        rows_chrono = list(reversed(rows))
        records = [_orm_to_record(r) for r in rows_chrono]

        # 连续N次全部成功 → 成功蒸馏
        if all(r.success for r in records):
            return await self.distill_from_success(records)

        # 连续N次全部失败 → 失败教训
        if all(not r.success for r in records):
            return await self.distill_from_failure(records)

        # 成败交织,不满足连续条件
        return None

    async def confirm_distillation(self, skill_content: str, skill_name: str) -> dict:
        """人工确认后,将技能写入 data/skills/{skill_name}.md"""
        if not skill_name:
            return {"ok": False, "error": "skill_name 不能为空", "path": None}
        if not skill_content:
            return {"ok": False, "error": "skill_content 不能为空", "path": None}

        self._SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        # 规范化文件名,仅保留字母数字下划线连字符
        safe_name = re.sub(r"[^\w\-]", "_", skill_name)
        target = self._SKILLS_DIR / f"{safe_name}.md"
        target.write_text(skill_content, encoding="utf-8")
        return {
            "ok": True,
            "error": None,
            "path": str(target),
            "skill_name": safe_name,
        }

    def _build_distill_prompt(self, records: list[TaskRecord], success: bool) -> str:
        """构建蒸馏 LLM 提示词,要求输出技能定义 JSON"""
        records_text = self._format_records(records)
        if success:
            context = (
                "以下任务均取得了成功。请分析这些成功任务,提取可复用的执行模式, "
                "生成一个技能定义,使其能在未来类似任务中复用。"
            )
        else:
            context = (
                "以下任务均失败了。请分析失败原因,提取需要避免的模式, "
                "生成一个教训性的技能定义。"
            )

        return (
            "你是一个技能蒸馏专家。"
            + context
            + "\n\n"
            + "任务记录如下:\n"
            + records_text
            + "\n\n"
            + "请输出一个 JSON 对象(只输出 JSON,不要任何解释文字),格式如下:\n"
            "{\n"
            '  "skill_name": "简短的英文蛇形命名技能名",\n'
            '  "description": "技能用途的中文描述",\n'
            '  "prompt_template": "可复用的提示词模板,用 {{变量名}} 标记占位变量",\n'
            '  "variables": ["变量名列表"],\n'
            '  "tags": ["标签1", "标签2"]\n'
            "}\n"
        )

    def _build_lesson_prompt(self, records: list[TaskRecord]) -> str:
        """构建失败分析提示词,要求输出教训 JSON"""
        records_text = self._format_records(records)
        return (
            "你是一个任务复盘专家。以下任务均失败了,请分析失败的根本原因, "
            "总结出可复用的教训,帮助未来避免同类错误。\n\n"
            "失败任务记录如下:\n"
            + records_text
            + "\n\n"
            + "请输出一个 JSON 对象(只输出 JSON,不要任何解释文字),格式如下:\n"
            "{\n"
            '  "lesson": "具体的教训内容,中文描述",\n'
            '  "task_type": "对应的任务类型",\n'
            '  "severity": "high 或 medium 或 low"\n'
            "}\n"
        )

    def _parse_llm_json(self, text: str) -> dict:
        """处理 LLM 返回可能带 markdown code block 的情况,解析 JSON"""
        raw = text.strip()
        # 去除 markdown 代码块 ```json ... ``` 或 ``` ... ```
        if raw.startswith("```"):
            # 去掉首行 ```json 或 ```
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
        # 尝试直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 兜底:从文本中提取第一个 {...} 片段
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        # 仍然失败则抛出,由调用方捕获
        return json.loads(raw)

    def _format_records(self, records: list[TaskRecord]) -> str:
        """格式化任务记录为可读文本"""
        lines = []
        for i, r in enumerate(records, 1):
            lines.append(
                f"--- 任务 {i} ---\n"
                f"类型: {r.task_type}\n"
                f"描述: {r.description}\n"
                f"输入: {json.dumps(r.inputs, ensure_ascii=False) if r.inputs else '{}'}\n"
                f"输出: {r.output or '(无)'}\n"
                f"是否成功: {'是' if r.success else '否'}\n"
                f"迭代次数: {r.iterations}\n"
                f"Persona ID: {r.persona_id or '(无)'}"
            )
        return "\n\n".join(lines)

    def _format_skill_markdown(
        self,
        name: str,
        description: str,
        prompt_template: str,
        variables: list,
        tags: list,
    ) -> str:
        """组装技能 Markdown 内容(frontmatter + 模板),兼容 SkillLoader 解析格式"""
        tags_str = ", ".join(tags) if tags else ""
        frontmatter = "---\n"
        frontmatter += f"description: {description}\n"
        if tags_str:
            frontmatter += f"tags: {tags_str}\n"
        frontmatter += "---\n\n"

        body = f"# {name}\n\n"
        if description:
            body += f"{description}\n\n"
        if variables:
            body += "## 变量\n\n"
            for v in variables:
                body += f"- `{v}`\n"
            body += "\n"
        body += "## 提示词模板\n\n"
        body += f"```\n{prompt_template}\n```\n"
        return frontmatter + body
