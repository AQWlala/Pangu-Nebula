# server/cu/knowledge_bridge.py
"""CU ↔ 知识库双向联动"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class KnowledgeCandidate:
    title: str
    content: str
    doc_type: str
    source_task_id: str
    confidence: float


class CUKnowledgeBridge:
    """CU 与知识库双向联动核心"""

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
            ))

        if failed_steps:
            error_content = self._generate_error_doc(instruction, failed_steps)
            candidates.append(KnowledgeCandidate(
                title=f"CU 错误案例: {instruction}", content=error_content,
                doc_type="note", source_task_id=task_id, confidence=0.7,
            ))

        return candidates

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
