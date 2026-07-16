# server/cu/knowledge_bridge.py
"""CU ↔ 知识库双向联动"""
from __future__ import annotations
from dataclasses import dataclass, field
import logging

from server.kb.storage.frontmatter import FrontMatter
from server.kb.storage.inbox import InboxWriter

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeCandidate:
    title: str
    content: str
    doc_type: str
    source_task_id: str
    confidence: float
    tags: list[str] = field(default_factory=lambda: ["cu-generated"])
    scope: str = "private"


class CUKnowledgeBridge:
    """CU 与知识库双向联动核心"""

    def __init__(self, inbox_writer: InboxWriter | None = None):
        """初始化桥接器。

        Args:
            inbox_writer: 可选的 InboxWriter。若提供，则 ``action_to_knowledge_sync``
                会将每个知识候选项通过 ``InboxWriter.stage()`` 写入 _inbox；
                若不提供，则仅返回候选项（向后兼容）。
        """
        self.inbox_writer = inbox_writer

    def action_to_knowledge_sync(self, task_id: str, step_results: list[dict],
                                 instruction: str) -> list[KnowledgeCandidate]:
        """将 CU 结果转化为知识候选（写入 _inbox）"""
        candidates = []
        success_steps = [s for s in step_results if s["result_status"] == "success"]
        failed_steps = [s for s in step_results if s["result_status"] != "success"]

        if success_steps:
            sop_content = self._generate_sop(instruction, success_steps)
            candidates.append(KnowledgeCandidate(
                title=f"CU SOP: {instruction}", content=sop_content,
                doc_type="note", source_task_id=task_id, confidence=0.88,
                tags=["cu-generated", "sop"], scope="private",
            ))

        if failed_steps:
            error_content = self._generate_error_doc(instruction, failed_steps)
            candidates.append(KnowledgeCandidate(
                title=f"CU 错误案例: {instruction}", content=error_content,
                doc_type="note", source_task_id=task_id, confidence=0.7,
                tags=["cu-generated", "error-case"], scope="private",
            ))

        # 将候选项写入 _inbox（若配置了 inbox_writer）
        # 防御性：单条 stage 失败不影响其它候选项与调用方
        if self.inbox_writer is not None and candidates:
            for cand in candidates:
                try:
                    self._stage_candidate(cand)
                except Exception as e:
                    logger.warning(
                        f"Failed to stage knowledge candidate '{cand.title}' "
                        f"for task {cand.source_task_id}: {e}"
                    )

        return candidates

    def _stage_candidate(self, candidate: KnowledgeCandidate) -> str:
        """通过 InboxWriter.stage() 将单个知识候选项写入 _inbox。

        Returns:
            pending_id 由 InboxWriter 返回。
        """
        frontmatter = FrontMatter(
            title=candidate.title,
            type=candidate.doc_type,
            scope=candidate.scope,
            source_type="cu",
            source_original_path=f"cu://task/{candidate.source_task_id}",
            tags=list(candidate.tags),
            confidence=candidate.confidence,
        )
        original_filename = f"cu-{candidate.source_task_id}.md"
        meta = {
            "source_task_id": candidate.source_task_id,
            "confidence": candidate.confidence,
            "tags": list(candidate.tags),
            "scope": candidate.scope,
        }
        return self.inbox_writer.stage(
            original_filename=original_filename,
            converted_md=candidate.content,
            frontmatter=frontmatter,
            meta=meta,
        )

    def _generate_sop(self, instruction: str, steps: list[dict]) -> str:
        lines = [f"# CU SOP: {instruction}\n", "> 本文档由 CU 任务自动生成\n"]
        for s in steps:
            lines.append(f"## 步骤 {s['step_index']}: {s['action_type']}")
            lines.append(f"- 状态: {s['result_status']}")
            if "result_data" in s:
                lines.append(f"- 结果: {s['result_data']}")
            lines.append("")
        return "\n".join(lines)

    def _generate_error_doc(self, instruction: str, steps: list[dict]) -> str:
        lines = [f"# CU 错误案例: {instruction}\n", "> 失败步骤记录\n"]
        for s in steps:
            lines.append(f"## 步骤 {s['step_index']}: {s['action_type']}")
            lines.append(f"- 状态: {s['result_status']}")
            lines.append("")
        return "\n".join(lines)
