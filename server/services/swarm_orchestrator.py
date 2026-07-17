import asyncio
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import AsyncIterator

from sqlalchemy import select

from ..core.event_bus import get_event_bus
from ..db.engine import async_session
from ..db.orm import Persona
from ..db.swarm_models import Swarm, SwarmWorker
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider


class SwarmOrchestrator:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or async_session
        # Worker 动态扩缩容配置 (T3.1)
        self.min_workers = 2
        self.max_workers = 8

    async def decompose_task(self, swarm_id: int, goal: str, persona: Persona) -> list[dict]:
        prompt = (
            f"你是 {persona.name}。用户需要完成以下目标：\n{goal}\n\n"
            f"请将目标拆解为 2-5 个子任务，每个子任务可以并行执行。\n"
            f'返回 JSON 格式：\n[{{"id": "subtask_1", "title": "...", "description": "...", "worker_count": 3}}]'
        )

        messages = [
            ProviderMessage(role="system", content=persona.system_prompt),
            ProviderMessage(role="user", content=prompt),
        ]

        provider = get_provider(persona.model_provider)
        model = persona.model_name or "gpt-4"

        full_response = ""
        async for chunk in provider.generate(
            messages, model, temperature=persona.temperature, max_tokens=persona.max_tokens
        ):
            full_response += chunk

        subtasks = self._parse_subtasks(full_response)

        async with self.session_factory() as session:
            swarm = await session.get(Swarm, swarm_id)
            swarm.subtasks = subtasks
            await session.commit()

        return subtasks

    async def dispatch_workers(self, swarm_id: int, subtasks: list[dict]) -> None:
        async with self.session_factory() as session:
            swarm = await session.get(Swarm, swarm_id)
            persona = await session.get(Persona, swarm.persona_id)
            model_provider = (persona.model_provider if persona else None) or "openai"
            model_name = (persona.model_name if persona else None) or "gpt-4o-mini"

            for subtask in subtasks:
                count = max(2, min(5, int(subtask.get("worker_count", 3))))
                for i in range(count):
                    worker = SwarmWorker(
                        swarm_id=swarm_id,
                        subtask_id=subtask["id"],
                        worker_index=i,
                        model_provider=model_provider,
                        model_name=model_name,
                    )
                    session.add(worker)
            await session.commit()

    async def run_swarm(self, swarm_id: int) -> AsyncIterator[dict]:
        bus = get_event_bus()
        try:
            async with self.session_factory() as session:
                swarm = await session.get(Swarm, swarm_id)
                if swarm is None:
                    yield {"type": "error", "error": "Swarm not found"}
                    return
                persona = await session.get(Persona, swarm.persona_id)
                if persona is None:
                    yield {"type": "error", "error": "Persona not found"}
                    return
                goal = swarm.goal
                swarm.status = "decomposing"
                await session.commit()

            # 发布 swarm.started 事件 (EventBus, 异常不阻断主流程)
            try:
                await bus.publish(
                    "swarm.started",
                    {"swarm_id": swarm_id, "persona_id": persona.id, "goal": goal},
                    source="swarm_orchestrator",
                )
            except Exception:
                pass

            subtasks = await self.decompose_task(swarm_id, goal, persona)
            if not subtasks:
                raise RuntimeError("Failed to decompose task into subtasks")

            yield {"type": "decomposed", "subtasks": subtasks}

            # 发布 dag.node.started 事件 (decompose 阶段完成)
            try:
                await bus.publish(
                    "dag.node.started",
                    {"dag_id": f"dag-swarm-{swarm_id}", "phase": "decomposed", "subtasks": subtasks},
                    source="swarm_orchestrator",
                )
            except Exception:
                pass

            await self.dispatch_workers(swarm_id, subtasks)

            async with self.session_factory() as session:
                swarm = await session.get(Swarm, swarm_id)
                swarm.status = "running"
                await session.commit()

            async with self.session_factory() as session:
                result = await session.execute(
                    select(SwarmWorker).where(SwarmWorker.swarm_id == swarm_id)
                )
                workers = list(result.scalars().all())

            subtask_map = {st["id"]: st for st in subtasks}

            tasks = [
                asyncio.create_task(
                    self._run_worker_safe(w, subtask_map.get(w.subtask_id, {}), persona)
                )
                for w in workers
            ]

            for future in asyncio.as_completed(tasks):
                evt = await future
                yield evt
                # 发布 dag.node.completed 事件 (worker 完成)
                if evt.get("type") == "worker_done":
                    try:
                        await bus.publish(
                            "dag.node.completed",
                            {
                                "dag_id": f"dag-swarm-{swarm_id}",
                                "node_id": f"worker-{evt.get('subtask_id')}-{evt.get('worker_index')}",
                                "subtask_id": evt.get("subtask_id"),
                                "worker_index": evt.get("worker_index"),
                            },
                            source="swarm_orchestrator",
                        )
                    except Exception:
                        pass

            yield {"type": "verifying"}

            async with self.session_factory() as session:
                result = await session.execute(
                    select(SwarmWorker).where(SwarmWorker.swarm_id == swarm_id)
                )
                workers = list(result.scalars().all())

            verification = await self.verify_results(workers)
            final_result = await self.aggregate_results(
                swarm_id, verification["results"], persona
            )

            # 发布 swarm.completed 事件
            try:
                await bus.publish(
                    "swarm.completed",
                    {"swarm_id": swarm_id, "result": final_result},
                    source="swarm_orchestrator",
                )
            except Exception:
                pass

            yield {"type": "completed", "result": final_result}

        except Exception as exc:
            async with self.session_factory() as session:
                swarm = await session.get(Swarm, swarm_id)
                if swarm:
                    swarm.status = "failed"
                    await session.commit()
            # 发布 swarm.failed 事件
            try:
                await bus.publish(
                    "swarm.failed",
                    {"swarm_id": swarm_id, "error": str(exc)},
                    source="swarm_orchestrator",
                )
            except Exception:
                pass
            yield {"type": "error", "error": str(exc)}

    async def execute_worker(
        self, worker: SwarmWorker, subtask: dict, persona: Persona
    ) -> str:
        async with self.session_factory() as session:
            db_worker = await session.get(SwarmWorker, worker.id)
            db_worker.status = "running"
            await session.commit()

        messages = [
            ProviderMessage(role="system", content=persona.system_prompt),
            ProviderMessage(
                role="user",
                content=(
                    f"子任务：{subtask.get('title', '')}\n\n"
                    f"描述：{subtask.get('description', '')}\n\n"
                    f"请作为 {persona.name} 完成这个子任务，提供详细的结果。"
                ),
            ),
        ]

        provider = get_provider(worker.model_provider or persona.model_provider)
        model = worker.model_name or persona.model_name or "gpt-4o-mini"

        full_response = ""
        try:
            async for chunk in provider.generate(
                messages,
                model,
                temperature=persona.temperature,
                max_tokens=persona.max_tokens,
            ):
                full_response += chunk
        except Exception as exc:
            async with self.session_factory() as session:
                db_worker = await session.get(SwarmWorker, worker.id)
                db_worker.status = "failed"
                db_worker.error = str(exc)
                await session.commit()
            raise

        async with self.session_factory() as session:
            db_worker = await session.get(SwarmWorker, worker.id)
            db_worker.status = "completed"
            db_worker.result = full_response
            db_worker.tokens_used = len(full_response) // 4
            db_worker.completed_at = datetime.utcnow()
            await session.commit()

        return full_response

    async def verify_results(self, workers: list[SwarmWorker]) -> dict:
        groups: dict[str, list[SwarmWorker]] = {}
        for w in workers:
            groups.setdefault(w.subtask_id, []).append(w)

        results_per_subtask = []
        all_verified = True

        for subtask_id, group in groups.items():
            completed = [w for w in group if w.status == "completed" and w.result]
            if not completed:
                all_verified = False
                results_per_subtask.append({
                    "subtask_id": subtask_id,
                    "verified": False,
                    "consensus": "",
                    "dissent": [w.id for w in group],
                })
                continue

            if len(completed) == 1:
                results_per_subtask.append({
                    "subtask_id": subtask_id,
                    "verified": True,
                    "consensus": completed[0].result,
                    "dissent": [],
                })
                continue

            texts = [w.result or "" for w in completed]
            best_idx = 0
            best_count = 0
            for i, text in enumerate(texts):
                count = 1
                for j, other in enumerate(texts):
                    if i != j and SequenceMatcher(None, text, other).ratio() > 0.7:
                        count += 1
                if count > best_count:
                    best_count = count
                    best_idx = i

            majority = best_count > len(texts) / 2
            consensus = texts[best_idx] if majority else ""
            dissent = []
            for k, w in enumerate(completed):
                if majority and SequenceMatcher(None, texts[k], consensus).ratio() <= 0.7:
                    dissent.append(w.id)
            for w in group:
                if w.status != "completed":
                    dissent.append(w.id)

            if not majority:
                all_verified = False

            results_per_subtask.append({
                "subtask_id": subtask_id,
                "verified": majority,
                "consensus": consensus,
                "dissent": dissent,
            })

        return {"verified": all_verified, "results": results_per_subtask}

    async def aggregate_results(
        self, swarm_id: int, verified_results: list[dict], persona: Persona
    ) -> str:
        summaries = []
        for vr in verified_results:
            status = "已验证" if vr["verified"] else "需人工审核"
            consensus = vr.get("consensus") or "无共识"
            summaries.append(f"子任务 {vr['subtask_id']}（{status}）：\n{consensus}")

        prompt = (
            f"你是 {persona.name}。蜂群已执行以下子任务结果：\n\n"
            + "\n\n---\n\n".join(summaries)
            + "\n\n请汇总所有子任务结果，生成最终报告。"
        )

        messages = [
            ProviderMessage(role="system", content=persona.system_prompt),
            ProviderMessage(role="user", content=prompt),
        ]

        provider = get_provider(persona.model_provider)
        model = persona.model_name or "gpt-4"

        full_response = ""
        async for chunk in provider.generate(
            messages, model, temperature=persona.temperature, max_tokens=persona.max_tokens
        ):
            full_response += chunk

        async with self.session_factory() as session:
            swarm = await session.get(Swarm, swarm_id)
            swarm.result = full_response
            swarm.status = "completed"
            await session.commit()

        return full_response

    async def _run_worker_safe(
        self, worker: SwarmWorker, subtask: dict, persona: Persona
    ) -> dict:
        try:
            await self.execute_worker(worker, subtask, persona)
            return {
                "type": "worker_done",
                "subtask_id": worker.subtask_id,
                "worker_index": worker.worker_index,
            }
        except Exception as exc:
            return {
                "type": "worker_failed",
                "subtask_id": worker.subtask_id,
                "worker_index": worker.worker_index,
                "error": str(exc),
            }

    # ===== T3.1: Worker 动态扩缩容 =====

    async def resize_workers(self, swarm_id: int, count: int) -> dict:
        """调整蜂群的 worker 数量

        - swarm_id: 蜂群 ID
        - count: 目标 worker 数量(会被限制在 [min_workers, max_workers] 范围内)

        返回 {ok, swarm_id, before, after, added, removed}
        """
        target = max(self.min_workers, min(self.max_workers, count))

        async with self.session_factory() as session:
            result = await session.execute(
                select(SwarmWorker).where(SwarmWorker.swarm_id == swarm_id)
            )
            workers = list(result.scalars().all())
            before = len(workers)

            if before == target:
                return {
                    "ok": True,
                    "swarm_id": swarm_id,
                    "before": before,
                    "after": before,
                    "added": 0,
                    "removed": 0,
                    "message": "worker count unchanged",
                }

            if before < target:
                # 扩容:添加新 worker
                added = 0
                # 取已有 worker 的 provider/model 作为模板
                template_provider = "openai"
                template_model = "gpt-4o-mini"
                if workers:
                    template_provider = workers[0].model_provider or template_provider
                    template_model = workers[0].model_name or template_model
                # 找到最大 worker_index 便于续号(按 subtask 分组补齐)
                subtask_groups: dict[str, list[SwarmWorker]] = {}
                for w in workers:
                    subtask_groups.setdefault(w.subtask_id, []).append(w)
                for subtask_id, group in subtask_groups.items():
                    max_idx = max((w.worker_index for w in group), default=-1)
                    # 每个 subtask 至少 target 个 worker
                    current = len(group)
                    if current < target:
                        need = target - current
                        for _ in range(need):
                            max_idx += 1
                            new_worker = SwarmWorker(
                                swarm_id=swarm_id,
                                subtask_id=subtask_id,
                                worker_index=max_idx,
                                model_provider=template_provider,
                                model_name=template_model,
                            )
                            session.add(new_worker)
                            added += 1
                await session.commit()
                return {
                    "ok": True,
                    "swarm_id": swarm_id,
                    "before": before,
                    "after": before + added,
                    "added": added,
                    "removed": 0,
                }

            # 缩容:移除多余的 worker(优先移除 pending 状态的)
            excess = before - target
            removed = 0
            # 按 status 优先级排序: pending > running > completed > failed
            status_priority = {"pending": 0, "running": 1, "completed": 2, "failed": 3}
            sorted_workers = sorted(
                workers,
                key=lambda w: (status_priority.get(w.status, 9), -w.worker_index),
            )
            for w in sorted_workers[:excess]:
                await session.delete(w)
                removed += 1
            await session.commit()
            return {
                "ok": True,
                "swarm_id": swarm_id,
                "before": before,
                "after": before - removed,
                "added": 0,
                "removed": removed,
            }

    # ===== T3.2: 多样性指标 =====

    async def get_diversity_metrics(self, swarm_id: int) -> dict:
        """获取蜂群的 provider 多样性指标

        返回 {ok, swarm_id, total_workers, provider_distribution, model_distribution, diversity_score}
        - diversity_score: 0-1,越高表示越多样(基于 Shannon 熵归一化)
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(SwarmWorker).where(SwarmWorker.swarm_id == swarm_id)
            )
            workers = list(result.scalars().all())

        total = len(workers)
        if total == 0:
            return {
                "ok": True,
                "swarm_id": swarm_id,
                "total_workers": 0,
                "provider_distribution": {},
                "model_distribution": {},
                "diversity_score": 0.0,
            }

        provider_counts: dict[str, int] = {}
        model_counts: dict[str, int] = {}
        for w in workers:
            p = w.model_provider or "unknown"
            m = w.model_name or "unknown"
            provider_counts[p] = provider_counts.get(p, 0) + 1
            model_counts[m] = model_counts.get(m, 0) + 1

        # Shannon 熵归一化作为多样性得分
        import math
        provider_entropy = 0.0
        for count in provider_counts.values():
            p = count / total
            provider_entropy -= p * math.log(p) if p > 0 else 0
        max_entropy = math.log(len(provider_counts)) if len(provider_counts) > 1 else 1
        diversity_score = provider_entropy / max_entropy if max_entropy > 0 else 0.0

        return {
            "ok": True,
            "swarm_id": swarm_id,
            "total_workers": total,
            "provider_distribution": provider_counts,
            "model_distribution": model_counts,
            "diversity_score": round(diversity_score, 4),
        }

    def _parse_subtasks(self, response: str) -> list[dict]:
        text = response.strip()
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        try:
            subtasks = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                try:
                    subtasks = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return []
            else:
                return []

        result = []
        for i, st in enumerate(subtasks, 1):
            if not isinstance(st, dict):
                continue
            result.append({
                "id": st.get("id", f"subtask_{i}"),
                "title": st.get("title", f"子任务 {i}"),
                "description": st.get("description", ""),
                "worker_count": max(2, min(5, int(st.get("worker_count", 3)))),
            })
        return result
