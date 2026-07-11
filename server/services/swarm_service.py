import asyncio
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db.engine import async_session
from ..db.swarm_models import Swarm, SwarmWorker


def _swarm_to_dict(swarm: Swarm, include_workers: bool = False) -> dict:
    data = {
        "id": swarm.id,
        "persona_id": swarm.persona_id,
        "goal": swarm.goal,
        "title": swarm.title,
        "status": swarm.status,
        "result": swarm.result,
        "subtasks": swarm.subtasks,
        "created_at": swarm.created_at.isoformat() if swarm.created_at else None,
        "updated_at": swarm.updated_at.isoformat() if swarm.updated_at else None,
    }
    if include_workers:
        data["workers"] = [_worker_to_dict(w) for w in swarm.workers]
    return data


def _worker_to_dict(worker: SwarmWorker) -> dict:
    return {
        "id": worker.id,
        "swarm_id": worker.swarm_id,
        "subtask_id": worker.subtask_id,
        "worker_index": worker.worker_index,
        "status": worker.status,
        "result": worker.result,
        "error": worker.error,
        "model_provider": worker.model_provider,
        "model_name": worker.model_name,
        "tokens_used": worker.tokens_used,
        "created_at": worker.created_at.isoformat() if worker.created_at else None,
        "completed_at": worker.completed_at.isoformat() if worker.completed_at else None,
    }


class SwarmService:
    async def create_swarm(
        self, session: AsyncSession, persona_id: int, goal: str, title: str | None
    ) -> dict:
        swarm = Swarm(persona_id=persona_id, goal=goal, title=title or goal[:100], status="pending")
        session.add(swarm)
        await session.commit()
        await session.refresh(swarm)
        return _swarm_to_dict(swarm)

    async def get_swarm(self, session: AsyncSession, swarm_id: int) -> dict | None:
        result = await session.execute(
            select(Swarm)
            .where(Swarm.id == swarm_id)
            .options(selectinload(Swarm.workers))
        )
        swarm = result.scalar_one_or_none()
        return _swarm_to_dict(swarm, include_workers=True) if swarm else None

    async def list_swarms(
        self, session: AsyncSession, page: int = 1, page_size: int = 20
    ) -> list[dict]:
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Swarm)
            .order_by(Swarm.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return [_swarm_to_dict(s) for s in result.scalars().all()]

    async def update_swarm(
        self, session: AsyncSession, swarm_id: int, **kwargs
    ) -> dict | None:
        swarm = await session.get(Swarm, swarm_id)
        if not swarm:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(swarm, key, value)
        await session.commit()
        await session.refresh(swarm)
        return _swarm_to_dict(swarm)

    async def delete_swarm(self, session: AsyncSession, swarm_id: int) -> bool:
        swarm = await session.get(Swarm, swarm_id)
        if not swarm:
            return False
        await session.delete(swarm)
        await session.commit()
        return True

    async def update_swarm_status(
        self, session: AsyncSession, swarm_id: int, status: str, result: str | None = None
    ) -> None:
        swarm = await session.get(Swarm, swarm_id)
        if not swarm:
            return
        swarm.status = status
        if result is not None:
            swarm.result = result
        await session.commit()

    async def save_worker(
        self,
        session: AsyncSession,
        swarm_id: int,
        subtask_id: str,
        worker_index: int,
        status: str,
        result: str | None,
        error: str | None,
        tokens: int = 0,
    ) -> None:
        worker = SwarmWorker(
            swarm_id=swarm_id,
            subtask_id=subtask_id,
            worker_index=worker_index,
            status=status,
            result=result,
            error=error,
            tokens_used=tokens,
        )
        session.add(worker)
        await session.commit()

    async def get_workers(self, session: AsyncSession, swarm_id: int) -> list[dict]:
        result = await session.execute(
            select(SwarmWorker)
            .where(SwarmWorker.swarm_id == swarm_id)
            .order_by(SwarmWorker.subtask_id, SwarmWorker.worker_index)
        )
        return [_worker_to_dict(w) for w in result.scalars().all()]

    async def _check_cancelled(self, swarm_id: int) -> bool:
        async with async_session() as session:
            swarm = await session.get(Swarm, swarm_id)
            return swarm is not None and swarm.status == "cancelled"

    async def run_swarm(self, swarm_id: int) -> AsyncIterator[dict]:
        async with async_session() as session:
            swarm = await session.get(Swarm, swarm_id)
            if swarm is None:
                yield {"type": "error", "error": "Swarm not found"}
                return
            goal = swarm.goal
            swarm.status = "decomposing"
            await session.commit()

        yield {"type": "status", "swarm_id": swarm_id, "status": "decomposing"}
        await asyncio.sleep(0.1)

        if await self._check_cancelled(swarm_id):
            yield {"type": "error", "error": "Swarm cancelled"}
            return

        subtasks = self._decompose(goal)
        async with async_session() as session:
            swarm = await session.get(Swarm, swarm_id)
            if swarm:
                swarm.subtasks = subtasks
                swarm.status = "running"
                await session.commit()

        yield {"type": "decomposed", "subtasks": subtasks}
        await asyncio.sleep(0.1)

        worker_results: list[str] = []
        for subtask in subtasks:
            if await self._check_cancelled(swarm_id):
                yield {"type": "error", "error": "Swarm cancelled"}
                return

            subtask_id = subtask["id"]
            worker_count = subtask["worker_count"]
            for idx in range(worker_count):
                if await self._check_cancelled(swarm_id):
                    yield {"type": "error", "error": "Swarm cancelled"}
                    return

                await asyncio.sleep(0.15)
                worker_result = f"[{subtask_id}/worker_{idx}] partial result for: {subtask['title']}"
                worker_results.append(worker_result)
                async with async_session() as session:
                    await self.save_worker(
                        session, swarm_id, subtask_id, idx,
                        "completed", worker_result, None, tokens=50,
                    )

                yield {
                    "type": "worker_done",
                    "subtask_id": subtask_id,
                    "worker_index": idx,
                    "status": "completed",
                }

            yield {"type": "verifying", "subtask_id": subtask_id}
            await asyncio.sleep(0.1)

            yield {
                "type": "verified",
                "subtask_id": subtask_id,
            }

        if await self._check_cancelled(swarm_id):
            yield {"type": "error", "error": "Swarm cancelled"}
            return

        yield {"type": "aggregating"}
        await asyncio.sleep(0.1)

        final_result = "\n".join(worker_results)
        async with async_session() as session:
            await self.update_swarm_status(session, swarm_id, "completed", final_result)

        yield {"type": "completed", "result": final_result}

    def _decompose(self, goal: str) -> list[dict]:
        snippet = goal[:60] + ("..." if len(goal) > 60 else "")
        return [
            {"id": "subtask_1", "title": f"分析目标: {snippet}", "worker_count": 3},
            {"id": "subtask_2", "title": f"执行方案: {snippet}", "worker_count": 3},
            {"id": "subtask_3", "title": f"验证结果: {snippet}", "worker_count": 2},
        ]
