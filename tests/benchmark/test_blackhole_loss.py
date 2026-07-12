"""黑洞体压缩信息损失率压测 (骨架)。

验证 BlackHoleEngine 在压缩记忆后，关键信息损失率 < 15%。
对同一组问题分别用「原始记忆」与「压缩后记忆」生成回答，
比较不一致比例 (compression_loss_rate)。

注意: 此测试需要真实 LLM 调用，当前为骨架模式。
运行方式: python -m pytest tests/benchmark/test_blackhole_loss.py -v --benchmark
"""

import pytest


@pytest.mark.benchmark
class TestBlackHoleLoss:
    """黑洞体压缩信息损失率测试。"""

    @pytest.mark.skip(reason="骨架模式 — 需要真实 LLM key")
    async def test_compression_loss_rate(self, db_session):
        """验证压缩后关键信息损失率 < 15%。

        步骤:
          1. 注入一批记忆到 MemoryService
          2. 用 BlackHoleEngine 压缩
          3. 对同一组问题分别用原始/压缩记忆生成回答
          4. 计算 compression_loss_rate
          5. assert loss_rate < 0.15
        """
        # from server.services.blackhole_engine import BlackHoleEngine
        # from .data_generator import ConversationGenerator
        # from .metrics import BenchmarkMetrics
        #
        # original_answers = [...]   # 基于原始记忆的回答
        # compressed_answers = [...]  # 基于压缩记忆的回答
        # loss = BenchmarkMetrics.compression_loss_rate(
        #     original_answers, compressed_answers
        # )
        # assert loss < 0.15, f"压缩损失率 {loss:.2%} 超过 15%"
        pass
