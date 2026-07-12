"""L3 语义提取准确率压测 (骨架)。

验证 SpongeEngine 从对话中提取 L3 语义记忆的准确率，
通过已知语义对话集 (ConversationGenerator.generate_known_semantics)
计算 Jaccard 准确率，期望 >= 70%。

注意: 此测试需要真实 LLM 调用，当前为骨架模式。
运行方式: python -m pytest tests/benchmark/test_l3_accuracy.py -v --benchmark
"""

import pytest

from .data_generator import ConversationGenerator
from .metrics import BenchmarkMetrics


@pytest.mark.benchmark
class TestL3Accuracy:
    """L3 语义提取准确率测试。"""

    @pytest.fixture
    def known_conversations(self):
        """已知语义的对话集 (含 expected_semantics)。"""
        return ConversationGenerator.generate_known_semantics()

    @pytest.mark.skip(
        reason="骨架模式 — 需要真实 LLM key，待 v0.3 正式压测时启用"
    )
    async def test_l3_extraction_accuracy(self, known_conversations, db_session):
        """验证 L3 语义提取准确率 >= 70%。

        步骤:
          1. 用 sponge_engine 逐组提取语义关键词
          2. 与 expected_semantics 做 Jaccard 交集/并集
          3. 计算平均准确率
          4. assert accuracy >= 0.7
        """
        # from server.services.sponge_engine import SpongeEngine
        # engine = SpongeEngine()
        # accuracies = []
        # for group in known_conversations:
        #     result = await engine.absorb(group["conversation"], persona_id=1)
        #     extracted_tags = result.tags if result.extracted else []
        #     acc = BenchmarkMetrics.semantic_extraction_accuracy(
        #         extracted_tags, group["expected_semantics"]
        #     )
        #     accuracies.append(acc)
        # avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0
        # assert avg_accuracy >= 0.7, f"L3 准确率 {avg_accuracy:.2%} 低于 70%"
        pass
