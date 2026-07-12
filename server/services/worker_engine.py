import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from ..providers.base import Message
from ..providers.registry import get_provider
from .verifier import ResultVerifier


class WorkerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class WorkerConfig:
    worker_index: int
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120
    # T3.3: 失败 worker 重试策略,最多 3 次,指数退避
    max_retries: int = 3


@dataclass
class WorkerResult:
    worker_index: int
    status: WorkerStatus
    content: str = ""
    error: str = ""
    tokens_used: int = 0
    elapsed_ms: int = 0
    # T3.2: 反对意见标记 - 结果与多数不一致时为 True
    dissenting: bool = False


@dataclass
class SubtaskResult:
    subtask_id: str
    workers: list[WorkerResult] = field(default_factory=list)
    consensus: str = ""
    confidence: float = 0.0
    dissent: list[int] = field(default_factory=list)


class WorkerEngine:
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.verifier = ResultVerifier()

    async def execute_worker(
        self,
        system_prompt: str,
        subtask_description: str,
        config: WorkerConfig,
        context: str = "",
    ) -> WorkerResult:
        start = time.time()
        async with self.semaphore:
            for attempt in range(config.max_retries + 1):
                try:
                    async with asyncio.timeout(config.timeout):
                        provider = get_provider(config.model_provider)
                        messages = [
                            Message(role="system", content=system_prompt),
                            Message(
                                role="user",
                                content=f"任务：{subtask_description}\n\n上下文：{context}",
                            ),
                        ]
                        full_text = ""
                        async for chunk in provider.generate(
                            messages,
                            model=config.model_name,
                            temperature=config.temperature,
                            max_tokens=config.max_tokens,
                        ):
                            full_text += chunk
                        elapsed = int((time.time() - start) * 1000)
                        tokens = len(full_text) // 4
                        return WorkerResult(
                            worker_index=config.worker_index,
                            status=WorkerStatus.COMPLETED,
                            content=full_text,
                            tokens_used=tokens,
                            elapsed_ms=elapsed,
                        )
                except asyncio.TimeoutError:
                    if attempt < config.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return WorkerResult(
                        worker_index=config.worker_index,
                        status=WorkerStatus.TIMEOUT,
                        error="Timeout",
                        elapsed_ms=int((time.time() - start) * 1000),
                    )
                except Exception as e:
                    if attempt < config.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return WorkerResult(
                        worker_index=config.worker_index,
                        status=WorkerStatus.FAILED,
                        error=str(e),
                        elapsed_ms=int((time.time() - start) * 1000),
                    )
        return WorkerResult(
            worker_index=config.worker_index,
            status=WorkerStatus.FAILED,
            error="Max retries exceeded",
            elapsed_ms=int((time.time() - start) * 1000),
        )

    async def execute_subtask_workers(
        self,
        system_prompt: str,
        subtask: dict,
        worker_count: int = 3,
        context: str = "",
    ) -> SubtaskResult:
        subtask_id = subtask.get("id", "")
        description = subtask.get("description", "")

        configs = [WorkerConfig(worker_index=i) for i in range(worker_count)]
        tasks = [
            self.execute_worker(system_prompt, description, cfg, context)
            for cfg in configs
        ]
        workers = await asyncio.gather(*tasks)

        verification = self.verifier.verify(list(workers))

        # T3.2: 标记反对意见 worker - 结果与多数不一致时 dissenting=True
        for w in workers:
            if w.worker_index in verification.dissent_indices:
                w.dissenting = True

        return SubtaskResult(
            subtask_id=subtask_id,
            workers=list(workers),
            consensus=verification.consensus,
            confidence=verification.confidence,
            dissent=verification.dissent_indices,
        )

    async def execute_all_subtasks(
        self,
        system_prompt: str,
        subtasks: list[dict],
        context: str = "",
        worker_count: int = 3,
    ) -> list[SubtaskResult]:
        tasks = [
            self.execute_subtask_workers(system_prompt, subtask, worker_count, context)
            for subtask in subtasks
        ]
        return list(await asyncio.gather(*tasks))

    # ===== T3.2: 反对意见检测 =====

    def get_dissenting_workers(self, subtask_results: list[SubtaskResult]) -> list[dict]:
        """从子任务结果中提取所有被标记为反对意见的 worker

        - subtask_results: execute_all_subtasks / execute_subtask_workers 的返回值

        返回 [{subtask_id, worker_index, content_preview, error}]
        """
        dissenting: list[dict] = []
        for sr in subtask_results:
            for w in sr.workers:
                if w.dissenting:
                    dissenting.append({
                        "subtask_id": sr.subtask_id,
                        "worker_index": w.worker_index,
                        "status": w.status.value,
                        "content_preview": (w.content or "")[:200],
                        "error": w.error,
                    })
        return dissenting

    async def get_dissenting_workers_async(
        self, swarm_id: int
    ) -> list[dict]:
        """从数据库中读取蜂群的 worker,标记反对意见并返回

        - swarm_id: 蜂群 ID

        返回 [{worker_id, subtask_id, worker_index, status, result_preview, dissenting}]
        """
        from sqlalchemy import select

        from ..db.engine import async_session
        from ..db.swarm_models import SwarmWorker

        async with async_session() as session:
            result = await session.execute(
                select(SwarmWorker).where(SwarmWorker.swarm_id == swarm_id)
            )
            workers = list(result.scalars().all())

        # 按 subtask_id 分组,对每组的 completed worker 结果做相似度对比
        from difflib import SequenceMatcher

        groups: dict[str, list[SwarmWorker]] = {}
        for w in workers:
            groups.setdefault(w.subtask_id, []).append(w)

        dissenting_list: list[dict] = []
        for subtask_id, group in groups.items():
            completed = [w for w in group if w.status == "completed" and w.result]
            if len(completed) <= 1:
                continue
            # 计算每个 worker 与其他 worker 的平均相似度
            texts = [w.result or "" for w in completed]
            avg_sims = []
            for i, text in enumerate(texts):
                sims = [
                    SequenceMatcher(None, text, texts[j]).ratio()
                    for j in range(len(texts)) if j != i
                ]
                avg_sims.append(sum(sims) / len(sims) if sims else 0.0)
            # 平均相似度低于 0.6 视为反对意见
            for k, w in enumerate(completed):
                is_dissenting = avg_sims[k] < 0.6
                if is_dissenting:
                    dissenting_list.append({
                        "worker_id": w.id,
                        "subtask_id": subtask_id,
                        "worker_index": w.worker_index,
                        "status": w.status,
                        "result_preview": (w.result or "")[:200],
                        "dissenting": True,
                    })
        return dissenting_list
