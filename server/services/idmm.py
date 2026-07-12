"""IDMM 三层故障保活引擎 (T1.2 / T1.3 / T1.9)。

IDMM = Intelligent Decision Maintenance & Mitigation
用于在 agent 决策与 LLM 调用链路上提供三层故障保活能力:

- L1 规则层 (T1.2): 超时检测 + 指数退避重试
    超时任务自动重试,重试次数可配,异常被捕获后按指数退避策略重试。
- L2 backup model 层 (T1.3): provider 健康检查 + 自动切换
    主 provider 失败后自动切换到 backup provider,切换日志可追溯。
- L3 sidecar 层 (T1.9): 停滞检测 + 提示注入
    检测 agent 决策停滞(无进展 N 轮),通过 sidecar 注入提示恢复 agent。

所有数据结构使用 dataclass,内存存储,无外部依赖,便于测试。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..providers.registry import get_provider, is_registered


# ===== 默认配置常量 =====

# L1: 最大重试次数(不含首次执行)
DEFAULT_MAX_RETRIES = 3
# L1: 基础退避延迟(秒)
DEFAULT_BASE_DELAY = 1.0
# L1: 最大退避延迟(秒),避免退避时间过长
DEFAULT_MAX_DELAY = 30.0
# L1: 单次执行超时(秒)
DEFAULT_TIMEOUT = 30.0
# L3: 停滞阈值(连续无进展轮数)
DEFAULT_STAGNATION_THRESHOLD = 3


# ===== 数据结构 =====


@dataclass
class RetryAttempt:
    """单次重试记录(L1)"""

    attempt: int  # 第几次尝试(从 1 开始)
    success: bool
    error: str | None = None
    duration_ms: int = 0
    delay_ms: int = 0  # 本次失败后等待的退避延迟(毫秒)


@dataclass
class L1Result:
    """L1 规则层执行结果"""

    success: bool
    result: Any = None
    attempts: list[RetryAttempt] = field(default_factory=list)
    total_retries: int = 0  # 实际重试次数(不含首次)
    last_error: str | None = None


@dataclass
class ProviderSwitch:
    """provider 切换记录(L2,用于切换日志追溯)"""

    from_provider: str
    to_provider: str
    reason: str
    timestamp: float


@dataclass
class L2Result:
    """L2 backup model 层执行结果"""

    success: bool
    result: Any = None
    primary_used: str | None = None
    backup_used: str | None = None
    switched: bool = False
    switches: list[ProviderSwitch] = field(default_factory=list)
    last_error: str | None = None


@dataclass
class StagnationReport:
    """L3 停滞检测报告"""

    conv_id: str
    stagnated: bool
    rounds_without_progress: int
    threshold: int
    last_hint: str | None = None


# ===== IDMM 引擎 =====


class IDMMEngine:
    """IDMM 三层故障保活引擎

    L1: 规则层 - 超时检测+指数退避重试
    L2: backup model层 - provider健康检查+自动切换
    L3: sidecar层 - 停滞检测+提示注入
    """

    def __init__(self) -> None:
        # L2: provider 切换日志(内存存储,可追溯)
        self._switch_logs: list[ProviderSwitch] = []
        # L3: 会话停滞状态(内存存储: conv_id -> list of round states)
        self._conversation_state: dict[str, list[dict]] = {}
        # L3: 注入的 sidecar 提示历史(内存存储: conv_id -> list of hints)
        self._sidecar_injections: dict[str, list[str]] = {}

    # ===== L1: 规则层 - 超时检测 + 指数退避重试 =====

    async def execute_with_l1_retry(
        self,
        task: Callable[[], Awaitable[Any]],
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        retry_on: tuple = (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError),
    ) -> L1Result:
        """L1 规则层: 带超时检测和指数退避重试的执行

        验收: ① 超时任务自动重试 ② 重试次数可配

        Args:
            task: 异步可调用对象(无参 coroutine factory)
            max_retries: 最大重试次数(不含首次执行),默认 3
            base_delay: 基础退避延迟(秒),默认 1.0
            max_delay: 最大退避延迟(秒),默认 30.0
            timeout: 单次执行超时(秒),默认 30.0
            retry_on: 触发重试的异常类型,默认超时/连接错误

        Returns:
            L1Result: 包含成功状态、结果、所有尝试记录和重试次数
        """
        attempts: list[RetryAttempt] = []
        last_error: str | None = None
        # 总尝试次数 = 首次 + 重试次数
        total_attempts = max_retries + 1

        for attempt_idx in range(1, total_attempts + 1):
            start = time.time()
            try:
                # 超时检测: 使用 asyncio.wait_for 包装任务
                result = await asyncio.wait_for(task(), timeout=timeout)
                duration_ms = int((time.time() - start) * 1000)
                attempts.append(
                    RetryAttempt(
                        attempt=attempt_idx,
                        success=True,
                        duration_ms=duration_ms,
                    )
                )
                return L1Result(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_retries=attempt_idx - 1,
                )
            except retry_on as exc:
                # 可重试异常: 记录并按指数退避等待
                duration_ms = int((time.time() - start) * 1000)
                last_error = f"{type(exc).__name__}: {exc}"
                attempt_record = RetryAttempt(
                    attempt=attempt_idx,
                    success=False,
                    error=last_error,
                    duration_ms=duration_ms,
                )
                # 最后一次尝试失败,不再退避
                if attempt_idx >= total_attempts:
                    attempts.append(attempt_record)
                    break
                # 指数退避: delay = min(base_delay * 2^(attempt-1), max_delay)
                delay = min(base_delay * (2 ** (attempt_idx - 1)), max_delay)
                attempt_record.delay_ms = int(delay * 1000)
                attempts.append(attempt_record)
                await asyncio.sleep(delay)
            except Exception as exc:
                # 非重试型异常: 立即失败,不重试
                duration_ms = int((time.time() - start) * 1000)
                last_error = f"{type(exc).__name__}: {exc}"
                attempts.append(
                    RetryAttempt(
                        attempt=attempt_idx,
                        success=False,
                        error=last_error,
                        duration_ms=duration_ms,
                    )
                )
                break

        return L1Result(
            success=False,
            attempts=attempts,
            total_retries=len(attempts) - 1,
            last_error=last_error,
        )

    # ===== L2: backup model 层 - provider 健康检查 + 自动切换 =====

    async def check_provider_health(self, provider_name: str) -> bool:
        """检查 provider 健康状态

        通过 is_registered 校验注册状态,并尝试调用 test_connection
        """
        if not is_registered(provider_name):
            return False
        try:
            provider = get_provider(provider_name)
            return await provider.test_connection()
        except Exception:
            return False

    async def execute_with_l2_fallback(
        self,
        task_factory: Callable[[str], Awaitable[Any]],
        primary_provider: str,
        backup_providers: list[str] | None = None,
    ) -> L2Result:
        """L2 backup model 层: 主 provider 失败自动切换 backup

        验收: ① 主 provider 失败后自动切换 ② 切换日志可追溯

        Args:
            task_factory: 接收 provider_name 返回 coroutine 的工厂函数
            primary_provider: 主 provider 名称
            backup_providers: 备份 provider 名称列表(按优先级排序)

        Returns:
            L2Result: 包含成功状态、结果、切换记录
        """
        backups = list(backup_providers or [])
        switches: list[ProviderSwitch] = []
        last_error: str | None = None
        used_provider: str | None = None

        # 尝试主 provider
        try:
            result = await task_factory(primary_provider)
            return L2Result(
                success=True,
                result=result,
                primary_used=primary_provider,
                backup_used=None,
                switched=False,
                switches=[],
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            # 主 provider 失败: 如有 backup,记录切换日志
            if backups:
                switch = ProviderSwitch(
                    from_provider=primary_provider,
                    to_provider=backups[0],
                    reason=last_error,
                    timestamp=time.time(),
                )
                switches.append(switch)
                self._switch_logs.append(switch)

        # 主 provider 失败,依次尝试 backup
        for i, backup_name in enumerate(backups):
            try:
                result = await task_factory(backup_name)
                used_provider = backup_name
                return L2Result(
                    success=True,
                    result=result,
                    primary_used=primary_provider,
                    backup_used=backup_name,
                    switched=True,
                    switches=switches,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                # 切换到下一个 backup(如有)
                if i + 1 < len(backups):
                    switch = ProviderSwitch(
                        from_provider=backup_name,
                        to_provider=backups[i + 1],
                        reason=last_error,
                        timestamp=time.time(),
                    )
                    switches.append(switch)
                    self._switch_logs.append(switch)

        return L2Result(
            success=False,
            primary_used=primary_provider,
            backup_used=used_provider,
            switched=used_provider is not None,
            switches=switches,
            last_error=last_error,
        )

    def get_switch_logs(self) -> list[dict]:
        """获取 provider 切换日志(可追溯)"""
        return [
            {
                "from_provider": s.from_provider,
                "to_provider": s.to_provider,
                "reason": s.reason,
                "timestamp": s.timestamp,
            }
            for s in self._switch_logs
        ]

    def clear_switch_logs(self) -> None:
        """清空切换日志(用于测试)"""
        self._switch_logs.clear()

    # ===== L3: sidecar 层 - 停滞检测 + 提示注入 =====

    async def check_stagnation(
        self,
        conversation: list[dict],
        threshold: int = DEFAULT_STAGNATION_THRESHOLD,
        conv_id: str = "default",
    ) -> StagnationReport:
        """L3 停滞检测: 检测对话是否停滞(无进展 N 轮)

        验收: ① 停滞可检测

        Args:
            conversation: 对话消息列表,每条消息可包含 "progress" 字段
                          (True=有进展, False/None=无进展)
            threshold: 停滞阈值(连续无进展轮数),默认 3
            conv_id: 会话 ID

        Returns:
            StagnationReport: 停滞检测报告
        """
        rounds_without_progress = 0
        # 倒序扫描: 计算最近连续无进展的轮数
        for msg in reversed(conversation):
            if msg.get("progress", False):
                break
            rounds_without_progress += 1

        stagnated = rounds_without_progress >= threshold
        # 读取最近一次注入的 sidecar 提示
        injections = self._sidecar_injections.get(conv_id, [])
        last_hint = injections[-1] if injections else None

        return StagnationReport(
            conv_id=conv_id,
            stagnated=stagnated,
            rounds_without_progress=rounds_without_progress,
            threshold=threshold,
            last_hint=last_hint,
        )

    async def inject_sidecar(
        self,
        conversation: list[dict],
        hint: str,
        conv_id: str = "default",
    ) -> list[dict]:
        """L3 sidecar 注入: 在对话中注入提示以恢复停滞的 agent

        验收: ② sidecar 注入后 agent 恢复

        Args:
            conversation: 原对话列表
            hint: 注入的提示文本
            conv_id: 会话 ID

        Returns:
            注入 sidecar 后的新对话列表(不修改原列表)
        """
        # 记录注入历史
        self._sidecar_injections.setdefault(conv_id, []).append(hint)
        # 构造 sidecar 消息并追加到对话末尾
        sidecar_msg = {
            "role": "system",
            "content": f"[SIDECAR] {hint}",
            "sidecar": True,
            "progress": True,  # sidecar 注入视为有进展,打破停滞
        }
        # 返回新列表,不修改原列表
        return list(conversation) + [sidecar_msg]

    def get_injection_history(self, conv_id: str) -> list[str]:
        """获取会话的 sidecar 注入历史"""
        return list(self._sidecar_injections.get(conv_id, []))

    def record_round(
        self,
        conv_id: str,
        content: str,
        score: float | None = None,
        progress: bool = True,
    ) -> list[dict]:
        """记录一轮对话到会话状态(供 LoopEngine 等外部模块反馈进展)

        Args:
            conv_id: 会话 ID
            content: 本轮内容(如评估文本)
            score: 本轮评分(可选)
            progress: 是否有进展

        Returns:
            更新后的会话状态列表
        """
        state = self._conversation_state.setdefault(conv_id, [])
        state.append({
            "role": "assistant",
            "content": content,
            "score": score,
            "progress": progress,
        })
        return list(state)

    def get_conversation_state(self, conv_id: str) -> list[dict]:
        """获取会话状态(用于测试和调试)"""
        return list(self._conversation_state.get(conv_id, []))

    def set_conversation_state(self, conv_id: str, state: list[dict]) -> None:
        """设置会话状态(用于 sidecar 注入后更新状态)"""
        self._conversation_state[conv_id] = list(state)

    def reset(self, conv_id: str | None = None) -> None:
        """重置引擎状态(用于测试或会话清理)

        Args:
            conv_id: 指定会话 ID 则只重置该会话; None 则重置全部
        """
        if conv_id is None:
            self._switch_logs.clear()
            self._conversation_state.clear()
            self._sidecar_injections.clear()
        else:
            self._conversation_state.pop(conv_id, None)
            self._sidecar_injections.pop(conv_id, None)
