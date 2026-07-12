"""压测报告生成器。

将记忆系统压测结果汇总为 Markdown 报告，输出到 docs/memory-benchmark.md。

运行方式: python -m tests.benchmark.generate_report
输出: docs/memory-benchmark.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _fmt(value: Any) -> str:
    """格式化指标值为可读字符串。"""
    if isinstance(value, float):
        return f"{value:.2%}" if 0.0 <= value <= 1.0 else f"{value:.4f}"
    if value is None:
        return "N/A"
    return str(value)


def generate_benchmark_report(results: dict) -> str:
    """生成 Markdown 格式的压测报告。

    结构:
      1. 概述 (日期、版本、环境)
      2. L3 语义提取准确率
      3. L5 元认知价值
      4. 黑洞体压缩损失率
      5. 海绵体噪声过滤率
      6. 结论与优化建议

    Args:
        results: 压测结果字典，键包括:
            date, version, environment (可选),
            l3_accuracy, l5_value, blackhole_loss, sponge_noise,
            以及 conclusion / suggestions (可选)。

    Returns:
        Markdown 字符串。
    """
    date = results.get("date", datetime.now().isoformat())
    version = results.get("version", "unknown")
    environment = results.get("environment", {})
    l3 = results.get("l3_accuracy", "待测试")
    l5 = results.get("l5_value", "待测试")
    blackhole = results.get("blackhole_loss", "待测试")
    sponge = results.get("sponge_noise", "待测试")
    conclusion = results.get("conclusion", "待 v0.3 正式压测后补充。")
    suggestions = results.get("suggestions", [])

    lines: list[str] = []
    lines.append("# Pangu Nebula 记忆系统压测报告")
    lines.append("")
    lines.append("## 1. 概述")
    lines.append("")
    lines.append(f"- **日期**: {date}")
    lines.append(f"- **版本**: {version}")
    if environment:
        lines.append(f"- **环境**: {json.dumps(environment, ensure_ascii=False)}")
    else:
        lines.append("- **环境**: 待补充 (Python 3.11 + FastAPI + SQLite)")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 2. L3 语义提取准确率")
    lines.append("")
    lines.append("指标: SpongeEngine 提取语义与期望关键词的 Jaccard 准确率。")
    lines.append("")
    lines.append(f"**结果**: {_fmt(l3)}")
    lines.append("")
    lines.append("- 目标阈值: >= 70%")
    lines.append("- 计算方式: `BenchmarkMetrics.semantic_extraction_accuracy`")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 3. L5 元认知价值")
    lines.append("")
    lines.append("指标: 启用 L5 元认知层后任务完成率提升、错误重复率下降幅度。")
    lines.append("")
    lines.append(f"**结果**: {_fmt(l5)}")
    lines.append("")
    lines.append("- 期望: 有 L5 的任务完成率 > 无 L5")
    lines.append("- 期望: 有 L5 的错误重复率 < 无 L5")
    lines.append("- 计算方式: `BenchmarkMetrics.metacognition_value_delta`")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 4. 黑洞体压缩损失率")
    lines.append("")
    lines.append("指标: BlackHoleEngine 压缩记忆后，关键信息损失比例。")
    lines.append("")
    lines.append(f"**结果**: {_fmt(blackhole)}")
    lines.append("")
    lines.append("- 目标阈值: < 15%")
    lines.append("- 计算方式: `BenchmarkMetrics.compression_loss_rate`")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 5. 海绵体噪声过滤率")
    lines.append("")
    lines.append("指标: SpongeEngine 过滤噪声对话的占比。")
    lines.append("")
    lines.append(f"**结果**: {_fmt(sponge)}")
    lines.append("")
    lines.append("- 计算方式: `BenchmarkMetrics.noise_filter_rate`")
    lines.append("- 期望: 噪声被合理过滤，有价值记忆被保留")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 6. 结论与优化建议")
    lines.append("")
    lines.append(f"**结论**: {conclusion}")
    lines.append("")
    if suggestions:
        lines.append("**优化建议**:")
        lines.append("")
        for idx, s in enumerate(suggestions, 1):
            lines.append(f"{idx}. {s}")
        lines.append("")
    else:
        lines.append("优化建议待 v0.3 正式压测后补充。")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> 本报告由 `tests/benchmark/generate_report.py` 自动生成。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """骨架模式: 生成空报告模板。

    生成一份填占位值的报告模板到 docs/memory-benchmark.md，
    供 v0.3 正式压测时填充真实数据。
    """
    template = {
        "date": datetime.now().isoformat(),
        "version": "v0.3.0-skeleton",
        "environment": {
            "python": "3.11",
            "framework": "FastAPI + SQLite",
            "mode": "skeleton",
        },
        "l3_accuracy": "待测试",
        "l5_value": "待测试",
        "blackhole_loss": "待测试",
        "sponge_noise": "待测试",
        "conclusion": "骨架模式 — 尚未执行真实压测，待 v0.3 启用真实 LLM key 后填充。",
        "suggestions": [
            "启用真实 LLM key 后运行 tests/benchmark/ 下的压测用例",
            "根据 L3 准确率结果调优 sponge_engine 的提取 prompt",
            "根据黑洞压缩损失率调整 BlackHoleEngine 的压缩阈值",
        ],
    }
    report = generate_benchmark_report(template)
    output = Path("docs/memory-benchmark.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"报告模板已生成: {output}")


if __name__ == "__main__":
    main()
