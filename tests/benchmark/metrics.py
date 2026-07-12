"""记忆系统压测评估指标。

定义四类核心指标，供 benchmark 测试断言与报告生成使用:
  - L3 语义提取准确率 (Jaccard 交集/并集)
  - 黑洞体压缩信息损失率 (压缩前后回答不一致比例)
  - 海绵体噪声过滤率 (被过滤掉的原始记忆比例)
  - L5 元认知价值差异 (有/无 L5 的任务完成率与错误重复率对比)
"""

from __future__ import annotations


def _normalize(items: list[str]) -> set[str]:
    """归一化关键词集合: 去空白、转小写、去重。"""
    return {str(x).strip().lower() for x in items if str(x).strip()}


class BenchmarkMetrics:
    """记忆系统压测评估指标。全部为静态方法，无状态。"""

    # ------------------------------------------------------------------
    # L3 语义提取准确率
    # ------------------------------------------------------------------
    @staticmethod
    def semantic_extraction_accuracy(
        extracted: list[str], expected: list[str]
    ) -> float:
        """L3 语义提取准确率 = 交集 / 并集 (Jaccard 系数)。

        Args:
            extracted: sponge_engine 实际提取出的语义关键词列表
            expected:  data_generator.generate_known_semantics 给出的期望关键词列表

        Returns:
            0.0 ~ 1.0 的浮点数。当两者均为空时返回 1.0 (约定无差异)。
        """
        ex_set = _normalize(extracted)
        exp_set = _normalize(expected)
        if not ex_set and not exp_set:
            return 1.0
        union = ex_set | exp_set
        if not union:
            return 1.0
        intersection = ex_set & exp_set
        return len(intersection) / len(union)

    # ------------------------------------------------------------------
    # 黑洞体压缩信息损失率
    # ------------------------------------------------------------------
    @staticmethod
    def compression_loss_rate(
        original_answers: list[str], compressed_answers: list[str]
    ) -> float:
        """黑洞体压缩信息损失率 = 不一致回答比例。

        对同一组问题分别用「原始记忆」与「黑洞压缩后记忆」生成回答，
        比较两者不一致的比例。比例越高说明压缩损失越大。

        Args:
            original_answers:  基于原始 (未压缩) 记忆的回答列表
            compressed_answers: 基于黑洞压缩后记忆的回答列表

        Returns:
            0.0 ~ 1.0 的浮点数 (不一致占比)。
            两个列表长度不等时按较短长度对齐比较。
        """
        if not original_answers or not compressed_answers:
            return 0.0
        n = min(len(original_answers), len(compressed_answers))
        if n == 0:
            return 0.0
        diff = 0
        for i in range(n):
            a = str(original_answers[i]).strip()
            b = str(compressed_answers[i]).strip()
            if a != b:
                diff += 1
        return diff / n

    # ------------------------------------------------------------------
    # 海绵体噪声过滤率
    # ------------------------------------------------------------------
    @staticmethod
    def noise_filter_rate(raw_memories: list, filtered_memories: list) -> float:
        """海绵体噪声过滤率 = 被过滤掉的比例。

        Args:
            raw_memories:     原始 (未过滤) 记忆条目列表
            filtered_memories: 海绵体过滤后保留的记忆条目列表

        Returns:
            0.0 ~ 1.0 的浮点数 (被过滤占比)。
            raw 为空时返回 0.0 (无输入则无过滤)。
        """
        raw_n = len(raw_memories) if raw_memories is not None else 0
        if raw_n == 0:
            return 0.0
        filtered_n = len(filtered_memories) if filtered_memories is not None else 0
        removed = max(raw_n - filtered_n, 0)
        return removed / raw_n

    # ------------------------------------------------------------------
    # L5 元认知价值差异
    # ------------------------------------------------------------------
    @staticmethod
    def metacognition_value_delta(
        with_l5: dict, without_l5: dict
    ) -> dict:
        """L5 元认知价值差异。

        对比「启用 L5 元认知层」与「关闭 L5」两组指标，量化 L5 带来的增量价值。

        Args:
            with_l5:    启用 L5 时的指标字典，至少包含:
                        {"task_completion_rate": float, "error_repeat_rate": float}
            without_l5: 关闭 L5 时的同结构指标字典

        Returns:
            {
                "task_completion_rate_delta": with - without,  # 正值 = L5 提升
                "error_repeat_rate_delta":    with - without,  # 负值 = L5 改善
                "with_l5":  {...},  # 原始 with_l5 回显
                "without_l5": {...},  # 原始 without_l5 回显
            }
        """
        def _rate(d: dict, key: str) -> float:
            v = d.get(key, 0.0) if isinstance(d, dict) else 0.0
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        with_completion = _rate(with_l5, "task_completion_rate")
        without_completion = _rate(without_l5, "task_completion_rate")
        with_repeat = _rate(with_l5, "error_repeat_rate")
        without_repeat = _rate(without_l5, "error_repeat_rate")

        return {
            "task_completion_rate_delta": with_completion - without_completion,
            "error_repeat_rate_delta": with_repeat - without_repeat,
            "with_l5": with_l5,
            "without_l5": without_l5,
        }
