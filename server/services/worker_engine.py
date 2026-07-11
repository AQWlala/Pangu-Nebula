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
    max_retries: int = 2


@dataclass
class WorkerResult:
    worker_index: int
    status: WorkerStatus
    content: str = ""
    error: str = ""
    tokens_used: int = 0
    elapsed_ms: int = 0


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
