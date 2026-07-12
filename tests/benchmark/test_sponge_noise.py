"""海绵体噪声过滤率压测 (骨架)。

验证 SpongeEngine 对噪声记忆的过滤能力。
向海绵体注入「有价值记忆 + 噪声对话」混合数据，
统计被过滤掉的噪声比例 (noise_filter_rate)。

注意: 此测试需要真实 LLM 调用，当前为骨架模式。
运行方式: python -m pytest tests/benchmark/test_sponge_noise.py -v --benchmark
"""

import pytest


@pytest.mark.benchmark
class TestSpongeNoise:
    """海绵体噪声过滤率测试。"""

    @pytest.mark.skip(reason="骨架模式 — 需要真实 LLM key")
    async def test_noise_filter_rate(self, db_session):
        """验证海绵体过滤噪声的比例。

        步骤:
          1. 用 ConversationGenerator 生成含噪声的批量对话
             (噪声轮次: "嗯嗯"、"ok"、"..." 等)
          2. 调用 SpongeEngine.absorb 处理
          3. 统计原始记忆数 vs 过滤后保留数
          4. 计算 noise_filter_rate
          5. 断言噪声被合理过滤 (保留有价值记忆)
        """
        # from server.services.sponge_engine import SpongeEngine
        # from .data_generator import ConversationGenerator
        # from .metrics import BenchmarkMetrics
        #
        # raw = ConversationGenerator.generate_single_conversation(num_turns=200)
        # raw_memories = [...]      # 注入的原始条目
        # filtered_memories = [...] # 海绵体过滤后保留条目
        # rate = BenchmarkMetrics.noise_filter_rate(raw_memories, filtered_memories)
        # assert rate >= 0.0  # 骨架: 具体阈值待 v0.3 标定
        pass
