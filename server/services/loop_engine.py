"""Phase 6C: Loop 循环迭代引擎。

执行→评估→改进→再执行的循环迭代模式:
- 执行阶段: 调用 LLM 执行目标
- 评估阶段: 调用 LLM 评估结果质量(0-10分)
- 改进阶段: 评分 < 阈值时,调用 LLM 生成改进建议并重新执行
- 循环终止: 评分达标或达到 max_iterations

融合 loop_guard 防死循环机制(来自 NomiFun):
- max_iterations 硬上限 20
- 每次迭代检查 status,如为 "cancelled" 则停止
- 连续 2 次评分相同或更低,停止循环(避免无效循环)
- 记录 budget_used

T1.10: IDMM 集成 - 反思↔保活闭环
- feedback_to_idmm: 反思结果反馈到 IDMM,触发停滞检测
- trigger_reflection_via_idmm: IDMM 检测停滞后注入 sidecar,触发新一轮反思
- run_loop_with_idmm: 完整自进化闭环(执行→评估→反思→IDMM保活→再执行)
"""

import json
import re
import time
from typing import AsyncIterator

from sqlalchemy import select

from ..db.engine import async_session
from ..db.orm import LoopIteration, Persona
from ..providers.base import Message as ProviderMessage
from ..providers.registry import get_provider, is_registered
from .idmm import IDMMEngine


# loop_guard: 最大迭代次数硬上限
MAX_ITERATIONS_HARD_LIMIT = 20
# 评分阈值: >= 此分数即视为达标,停止循环
SCORE_THRESHOLD = 8
# 连续评分无改善次数阈值,超过则停止
STAGNATION_LIMIT = 2


def _loop_to_dict(loop: LoopIteration) -> dict:
    """ORM 对象转换为 dict"""
    return {
        "id": loop.id,
        "persona_id": loop.persona_id,
        "goal": loop.goal,
        "status": loop.status,
        "iteration": loop.iteration,
        "max_iterations": loop.max_iterations,
        "steps": loop.steps or [],
        "result": loop.result,
        "evaluation": loop.evaluation,
        "budget_used": loop.budget_used or {"tokens": 0, "time_ms": 0, "cost": 0.0},
        "created_at": loop.created_at.isoformat() if loop.created_at else None,
        "updated_at": loop.updated_at.isoformat() if loop.updated_at else None,
    }


class LoopEngine:
    """Loop 循环迭代引擎:执行→评估→改进→再执行"""

    def __init__(self) -> None:
        # T1.10: 集成 IDMM 三层故障保活引擎
        self._idmm = IDMMEngine()

    # ===== 对外接口 =====

    async def create_loop(
        self, persona_id: int, goal: str, max_iterations: int = 5
    ) -> dict:
        """创建循环任务,返回 dict"""
        # loop_guard: 硬上限 20
        capped_max = max(1, min(int(max_iterations), MAX_ITERATIONS_HARD_LIMIT))
        async with async_session() as session:
            loop = LoopIteration(
                persona_id=persona_id,
                goal=goal,
                status="pending",
                iteration=0,
                max_iterations=capped_max,
                steps=[],
                budget_used={"tokens": 0, "time_ms": 0, "cost": 0.0},
            )
            session.add(loop)
            await session.commit()
            await session.refresh(loop)
            return _loop_to_dict(loop)

    async def run_loop(self, loop_id: int) -> AsyncIterator[dict]:
        """执行循环迭代(异步生成器,产出 SSE 事件)

        每次迭代:
          a. 执行阶段: 调用 LLM 执行目标
          b. 评估阶段: 调用 LLM 评估结果质量(0-10)
          c. 改进阶段: 评分 < 8 时生成改进建议并重新执行
          d. 评分 >= 8 或达到 max_iterations,停止循环
        """
        # 取出循环和 persona
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is None:
                yield {"type": "error", "error": "Loop not found"}
                return
            persona = await session.get(Persona, loop.persona_id)
            if persona is None:
                yield {"type": "error", "error": "Persona not found"}
                return
            # 设置为运行中
            loop.status = "running"
            await session.commit()
            goal = loop.goal
            max_iterations = loop.max_iterations
            steps = list(loop.steps or [])
            budget = dict(loop.budget_used or {"tokens": 0, "time_ms": 0, "cost": 0.0})

        # 校验 provider
        if not persona.model_provider or not is_registered(persona.model_provider):
            yield {
                "type": "error",
                "error": f"Provider '{persona.model_provider}' not registered",
            }
            await self._set_status(loop_id, "failed")
            return

        previous_result: str | None = None
        last_score: float | None = None
        stagnation_count = 0
        final_result = ""
        final_evaluation = ""
        iteration_count = 0

        for i in range(1, max_iterations + 1):
            # loop_guard: 检查取消状态
            if await self._is_cancelled(loop_id):
                yield {"type": "error", "error": "Loop cancelled"}
                return

            iteration_count = i
            iter_start = time.time()

            # 改进阶段(第一轮无改进建议)
            improvement: str | None = None
            if previous_result is not None:
                try:
                    improvement = await self._improve_iteration(
                        persona, goal, previous_result, final_evaluation
                    )
                except Exception as exc:
                    yield {"type": "error", "error": f"改进阶段失败: {exc}"}
                    await self._set_status(loop_id, "failed")
                    return

            # 执行阶段
            try:
                result, exec_tokens = await self._execute_iteration(
                    persona, goal, previous_result, improvement
                )
            except Exception as exc:
                yield {"type": "error", "error": f"执行阶段失败: {exc}"}
                await self._set_status(loop_id, "failed")
                return

            # 评估阶段
            try:
                eval_data, eval_tokens = await self._evaluate_iteration(
                    persona, goal, result
                )
            except Exception as exc:
                yield {"type": "error", "error": f"评估阶段失败: {exc}"}
                await self._set_status(loop_id, "failed")
                return

            iter_time_ms = int((time.time() - iter_start) * 1000)
            score = eval_data.get("score", 0)
            reason = eval_data.get("reason", "")
            needs_improvement = eval_data.get("needs_improvement", score < SCORE_THRESHOLD)
            evaluation_text = f"评分: {score}/10 - {reason}"

            final_result = result
            final_evaluation = evaluation_text

            # 追加步骤记录
            step_record = {
                "iteration": i,
                "action": "improve" if improvement else "execute",
                "result": result,
                "evaluation": evaluation_text,
                "score": score,
                "improved": improvement,
                "time_ms": iter_time_ms,
                "tokens": exec_tokens + eval_tokens,
            }
            steps.append(step_record)

            # 更新预算
            budget["tokens"] = budget.get("tokens", 0) + exec_tokens + eval_tokens
            budget["time_ms"] = budget.get("time_ms", 0) + iter_time_ms

            # 持久化中间状态
            await self._persist_progress(
                loop_id, i, steps, result, evaluation_text, budget
            )

            # 产出本次迭代事件
            yield {
                "type": "iteration",
                "iteration": i,
                "result": result,
                "evaluation": evaluation_text,
                "score": score,
            }

            # loop_guard: 连续 2 次评分相同或更低,停止循环
            if last_score is not None and score <= last_score:
                stagnation_count += 1
                if stagnation_count >= STAGNATION_LIMIT:
                    await self._finalize(
                        loop_id, final_result, final_evaluation,
                        iteration_count, steps, budget,
                    )
                    yield {
                        "type": "done",
                        "loop_id": loop_id,
                        "final_result": final_result,
                        "iterations": iteration_count,
                        "reason": "stagnation",
                    }
                    return
            else:
                stagnation_count = 0
            last_score = score

            # 评分达标,停止
            if score >= SCORE_THRESHOLD or not needs_improvement:
                await self._finalize(
                    loop_id, final_result, final_evaluation,
                    iteration_count, steps, budget,
                )
                yield {
                    "type": "done",
                    "loop_id": loop_id,
                    "final_result": final_result,
                    "iterations": iteration_count,
                    "reason": "threshold_reached",
                }
                return

            previous_result = result

        # 达到最大迭代次数
        await self._finalize(
            loop_id, final_result, final_evaluation,
            iteration_count, steps, budget,
        )
        yield {
            "type": "done",
            "loop_id": loop_id,
            "final_result": final_result,
            "iterations": iteration_count,
            "reason": "max_iterations",
        }

    async def cancel_loop(self, loop_id: int) -> dict | None:
        """取消循环,设置 status="cancelled" """
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is None:
                return None
            loop.status = "cancelled"
            await session.commit()
            await session.refresh(loop)
            return _loop_to_dict(loop)

    async def get_loop(self, loop_id: int) -> dict | None:
        """获取循环详情"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            return _loop_to_dict(loop) if loop else None

    async def list_loops(
        self,
        persona_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict]:
        """列出循环任务(支持按 persona_id / status 过滤,分页)"""
        page = max(page, 1)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size
        stmt = select(LoopIteration)
        if persona_id is not None:
            stmt = stmt.where(LoopIteration.persona_id == persona_id)
        if status:
            stmt = stmt.where(LoopIteration.status == status)
        stmt = stmt.order_by(LoopIteration.created_at.desc()).offset(offset).limit(page_size)
        async with async_session() as session:
            result = await session.execute(stmt)
            return [_loop_to_dict(loop) for loop in result.scalars().all()]

    async def delete_loop(self, loop_id: int) -> bool:
        """删除循环任务"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is None:
                return False
            await session.delete(loop)
            await session.commit()
            return True

    # ===== T1.10: IDMM 集成 - 反思↔保活闭环 =====

    async def feedback_to_idmm(
        self,
        loop_id: int,
        score: float,
        evaluation: str,
        conv_id: str | None = None,
    ) -> dict:
        """反思结果反馈到 IDMM,触发停滞检测

        将反思结果(评分+评估)记录到 IDMM 会话状态,并检测是否停滞。
        评分提升视为有进展(progress=True),否则视为无进展。

        闭环方向: 反思 → IDMM(记录+检测)

        Args:
            loop_id: 循环任务 ID
            score: 本次迭代评分(0-10)
            evaluation: 评估文本
            conv_id: 会话 ID,默认使用 f"loop-{loop_id}"

        Returns:
            停滞检测报告 dict
        """
        cid = conv_id or f"loop-{loop_id}"
        # 取上一次评分判断是否有进展
        state = self._idmm.get_conversation_state(cid)
        last_score = state[-1].get("score") if state else None
        progress = last_score is None or score > last_score
        # 记录本轮到 IDMM 会话状态
        self._idmm.record_round(cid, evaluation, score=score, progress=progress)
        # 触发停滞检测
        updated_state = self._idmm.get_conversation_state(cid)
        report = await self._idmm.check_stagnation(updated_state, conv_id=cid)
        return {
            "conv_id": report.conv_id,
            "stagnated": report.stagnated,
            "rounds_without_progress": report.rounds_without_progress,
            "threshold": report.threshold,
            "score": score,
            "progress": progress,
        }

    async def trigger_reflection_via_idmm(
        self,
        loop_id: int,
        conv_id: str | None = None,
        threshold: int = 3,
    ) -> dict:
        """IDMM 保活触发反思: 检测停滞后注入 sidecar 提示

        如果检测到停滞,生成 sidecar 提示并注入到会话中,
        以打破停滞并触发新一轮反思。

        闭环方向: IDMM(检测+注入) → 反思

        Args:
            loop_id: 循环任务 ID
            conv_id: 会话 ID,默认使用 f"loop-{loop_id}"
            threshold: 停滞阈值

        Returns:
            包含 stagnated / hint / injected 的 dict
        """
        cid = conv_id or f"loop-{loop_id}"
        state = self._idmm.get_conversation_state(cid)
        report = await self._idmm.check_stagnation(
            state, threshold=threshold, conv_id=cid
        )

        if not report.stagnated:
            return {
                "stagnated": False,
                "hint": None,
                "injected": False,
                "conv_id": cid,
            }

        # 生成 sidecar 提示(基于停滞轮数)
        hint = (
            f"检测到决策停滞(连续 {report.rounds_without_progress} 轮无进展)。"
            f"请尝试换个角度思考,或回顾目标并调整策略。"
        )
        # 注入 sidecar 到会话状态
        new_state = await self._idmm.inject_sidecar(state, hint, conv_id=cid)
        # 更新会话状态(sidecar 消息 progress=True,打破停滞)
        self._idmm.set_conversation_state(cid, new_state)

        return {
            "stagnated": True,
            "hint": hint,
            "injected": True,
            "conv_id": cid,
            "rounds_without_progress": report.rounds_without_progress,
        }

    async def _call_llm_with_l1_retry(
        self,
        persona: Persona,
        messages: list[ProviderMessage],
        max_retries: int = 2,
        timeout: float = 60.0,
    ) -> str:
        """用 L1 重试包装的 LLM 调用

        将 _call_llm 包装在 IDMM L1 规则层中,提供超时检测和指数退避重试。
        LLM 调用通常对网络超时敏感,L1 重试可提升调用可靠性。
        """
        async def _task():
            return await self._call_llm(persona, messages)

        result = await self._idmm.execute_with_l1_retry(
            _task,
            max_retries=max_retries,
            timeout=timeout,
            base_delay=0.5,  # LLM 调用退避较短
        )
        if not result.success:
            # L1 重试失败,抛出最后一个错误
            raise RuntimeError(f"L1 重试失败: {result.last_error}")
        return result.result

    async def run_loop_with_idmm(self, loop_id: int) -> AsyncIterator[dict]:
        """完整自进化闭环: 执行→评估→反思→IDMM保活→再执行

        在 run_loop 基础上集成 IDMM 三层保活:
        - 每次迭代后,将反思结果反馈到 IDMM (feedback_to_idmm)
        - 检测到停滞后,注入 sidecar 提示以恢复 (trigger_reflection_via_idmm)
        - 产出 IDMM 事件(idmm_feedback, idmm_sidecar)穿插在迭代事件之间

        验收: ① 反思→保活→反思闭环可运行
        """
        async for event in self.run_loop(loop_id):
            yield event
            # 在迭代事件后进行 IDMM 反馈
            if event.get("type") == "iteration":
                score = event.get("score", 0)
                evaluation = event.get("evaluation", "")
                feedback = await self.feedback_to_idmm(loop_id, score, evaluation)
                yield {"type": "idmm_feedback", "loop_id": loop_id, **feedback}
                # 如果检测到停滞,触发 sidecar 注入
                if feedback.get("stagnated"):
                    trigger = await self.trigger_reflection_via_idmm(loop_id)
                    yield {"type": "idmm_sidecar", "loop_id": loop_id, **trigger}

    # ===== 辅助方法 =====

    async def _execute_iteration(
        self,
        persona: Persona,
        goal: str,
        previous_result: str | None,
        improvement: str | None,
    ) -> tuple[str, int]:
        """执行单次迭代,返回 (结果文本, 估算 token 数)"""
        system_content = f"你是 {persona.name}。执行用户的目标。"
        user_content = f"目标: {goal}\n"
        if previous_result and improvement:
            user_content += f"\n上一次结果: {previous_result}\n改进建议: {improvement}\n请基于改进建议重新执行。"
        else:
            user_content += "\n请执行目标并返回结果。"

        messages = [
            ProviderMessage(role="system", content=system_content),
            ProviderMessage(role="user", content=user_content),
        ]
        response = await self._call_llm(persona, messages)
        tokens = self._estimate_tokens(system_content + user_content + response)
        return response, tokens

    async def _evaluate_iteration(
        self, persona: Persona, goal: str, result: str
    ) -> tuple[dict, int]:
        """评估结果质量,返回 (评估 dict, 估算 token 数)

        评估 dict: {"score": 0-10, "reason": "...", "needs_improvement": bool}
        """
        system_content = "你是一个结果评估引擎。评估执行结果的质量。"
        user_content = (
            f"目标: {goal}\n"
            f"执行结果: {result}\n"
            "请评估结果质量,返回 JSON: "
            '{"score": 0-10, "reason": "...", "needs_improvement": true/false}'
        )
        messages = [
            ProviderMessage(role="system", content=system_content),
            ProviderMessage(role="user", content=user_content),
        ]
        response = await self._call_llm(persona, messages)
        tokens = self._estimate_tokens(system_content + user_content + response)
        eval_data = self._parse_evaluation_json(response)
        return eval_data, tokens

    async def _improve_iteration(
        self, persona: Persona, goal: str, result: str, evaluation: str
    ) -> str:
        """生成改进建议,返回改进建议文本"""
        system_content = "你是一个改进建议引擎。分析结果不足并生成改进建议。"
        user_content = (
            f"目标: {goal}\n"
            f"当前结果: {result}\n"
            f"评估: {evaluation}\n"
            "请生成具体的改进建议:"
        )
        messages = [
            ProviderMessage(role="system", content=system_content),
            ProviderMessage(role="user", content=user_content),
        ]
        response = await self._call_llm(persona, messages)
        return response

    async def _call_llm(self, persona: Persona, messages: list[ProviderMessage]) -> str:
        """调用 LLM Provider 并收集完整响应"""
        provider = get_provider(persona.model_provider)
        full_response = ""
        async for chunk in provider.generate(
            messages,
            persona.model_name,
            temperature=persona.temperature,
            max_tokens=persona.max_tokens,
        ):
            full_response += chunk
        return full_response

    def _parse_evaluation_json(self, text: str) -> dict:
        """健壮解析 LLM 返回的评估 JSON

        处理: markdown 代码块、文本中嵌入 JSON、字段缺失等情况
        """
        raw = text.strip()
        # 去除 markdown 代码块 ```json ... ``` 或 ``` ... ```
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
        # 尝试直接解析
        try:
            data = json.loads(raw)
            return self._normalize_evaluation(data)
        except json.JSONDecodeError:
            pass
        # 兜底:从文本中提取第一个 {...} 片段
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return self._normalize_evaluation(data)
            except json.JSONDecodeError:
                pass
        # 全部失败,返回默认评估
        return {
            "score": 0,
            "reason": f"无法解析评估结果: {text[:200]}",
            "needs_improvement": True,
        }

    def _normalize_evaluation(self, data: dict) -> dict:
        """规范化评估结果,确保字段完整且类型正确"""
        try:
            score = float(data.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        # 评分限制在 0-10
        score = max(0.0, min(10.0, score))
        reason = str(data.get("reason", ""))
        needs = data.get("needs_improvement")
        if needs is None:
            needs = score < SCORE_THRESHOLD
        else:
            needs = bool(needs)
        return {"score": score, "reason": reason, "needs_improvement": needs}

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数(中文约 1 字 = 1 token,英文约 4 字符 = 1 token)"""
        if not text:
            return 0
        # 简单估算:总字符数 / 3
        return max(1, len(text) // 3)

    async def _is_cancelled(self, loop_id: int) -> bool:
        """检查循环是否已被取消"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            return loop is not None and loop.status == "cancelled"

    async def _set_status(self, loop_id: int, status: str) -> None:
        """设置循环状态"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is not None:
                loop.status = status
                await session.commit()

    async def _persist_progress(
        self,
        loop_id: int,
        iteration: int,
        steps: list[dict],
        result: str,
        evaluation: str,
        budget: dict,
    ) -> None:
        """持久化循环中间进度"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is None:
                return
            loop.iteration = iteration
            loop.steps = steps
            loop.result = result
            loop.evaluation = evaluation
            loop.budget_used = budget
            await session.commit()

    async def _finalize(
        self,
        loop_id: int,
        final_result: str,
        final_evaluation: str,
        iteration_count: int,
        steps: list[dict],
        budget: dict,
    ) -> None:
        """循环结束:设置 status="completed" 并写入最终结果"""
        async with async_session() as session:
            loop = await session.get(LoopIteration, loop_id)
            if loop is None:
                return
            # 如果已被取消,不覆盖 cancelled 状态
            if loop.status == "cancelled":
                return
            loop.status = "completed"
            loop.iteration = iteration_count
            loop.steps = steps
            loop.result = final_result
            loop.evaluation = final_evaluation
            loop.budget_used = budget
            await session.commit()
