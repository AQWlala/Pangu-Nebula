"""对话数据生成器 — 为记忆系统压测构造多轮对话数据。

覆盖场景: 技术讨论、日常对话、知识问答、代码审查等。
生成的数据用于:
  - L3 语义提取准确率测试 (generate_known_semantics)
  - 黑洞体压缩损失率测试 (generate_single_conversation / generate_batch)
  - 海绵体噪声过滤率测试 (含噪声的批量对话)
  - L5 元认知价值对比测试 (重复任务场景)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

# 固定随机种子，保证压测数据可复现
_DEFAULT_SEED = 20260712


# ---------------------------------------------------------------------------
# 内容模板池 — 覆盖多类对话场景
# ---------------------------------------------------------------------------

_TECH_TURNS = [
    "我们用 FastAPI 重构后端吧，async 支持更好。",
    "SQLAlchemy 2.0 的 async session 配合 aiosqlite 用起来挺顺。",
    "Pydantic v2 的 model_validate 比 parse_obj 快不少。",
    "记得给 ORM 模型加 index，查询性能差距很大。",
    "用 Alembic 做迁移，别手动改表结构。",
]

_DAILY_TURNS = [
    "今天天气不错，适合出去走走。",
    "中午想吃点清淡的，来个沙拉吧。",
    "周末打算去爬山，要一起吗？",
    "最近睡眠不太好，得调整下作息。",
    "这本书挺好看的，推荐给你。",
]

_KNOWLEDGE_TURNS = [
    "光合作用是植物把光能转成化学能的过程。",
    "地球到太阳的平均距离约 1.496 亿公里。",
    "DNA 双螺旋结构是沃森和克里克提出的。",
    "水的沸点在标准大气压下是 100 摄氏度。",
    "光速在真空中约 299792458 米每秒。",
]

_CODE_REVIEW_TURNS = [
    "这个函数圈复杂度太高了，建议拆分成几个小函数。",
    "这里没做空指针检查，可能抛 NoneType 错误。",
    "变量名 `a` 不够语义化，改成 `user_count` 更清晰。",
    "循环里每次都 new 一个对象，会有性能问题。",
    "异常被裸 except 吞掉了，至少要 log 一下。",
]

_NOISE_TURNS = [
    "嗯嗯。",
    "好的好的。",
    "哈哈哈。",
    "ok",
    "收到。",
    "...",
    "嗯",
]

# 每组 known_semantics: 关键词与对应对话片段绑定，用于 L3 准确率断言
_KNOWN_SEMANTIC_GROUPS: list[dict[str, Any]] = [
    {
        "topic": "Python 后端偏好",
        "conversation": [
            {"role": "user", "content": "我后端开发喜欢用 Python，比 Java 简洁多了。"},
            {"role": "assistant", "content": "Python 确实在后端开发中很流行，生态成熟。"},
            {"role": "user", "content": "特别是 FastAPI，写 API 又快又清晰。"},
        ],
        "expected_semantics": ["python", "后端", "fastapi"],
    },
    {
        "topic": "数据库选型",
        "conversation": [
            {"role": "user", "content": "项目要用数据库，SQLite 够用吗？"},
            {"role": "assistant", "content": "小项目 SQLite 足够，并发高的话建议 PostgreSQL。"},
            {"role": "user", "content": "那就先用 SQLite，后面再迁移。"},
        ],
        "expected_semantics": ["数据库", "sqlite", "postgresql"],
    },
    {
        "topic": "前端框架选择",
        "conversation": [
            {"role": "user", "content": "前端用 React 还是 Vue？"},
            {"role": "assistant", "content": "React 生态更丰富，Vue 上手更快。"},
            {"role": "user", "content": "我们团队熟 React，就用 React 加 TypeScript。"},
        ],
        "expected_semantics": ["前端", "react", "typescript"],
    },
    {
        "topic": "机器学习入门",
        "conversation": [
            {"role": "user", "content": "想学机器学习，该从哪入手？"},
            {"role": "assistant", "content": "建议先学线性代数和 Python，再看 scikit-learn。"},
            {"role": "user", "content": "数学基础得补，矩阵运算不太熟。"},
        ],
        "expected_semantics": ["机器学习", "python", "scikit-learn"],
    },
    {
        "topic": "Docker 部署",
        "conversation": [
            {"role": "user", "content": "应用想容器化部署，Docker 怎么配？"},
            {"role": "assistant", "content": "写个 Dockerfile，用多阶段构建减小镜像体积。"},
            {"role": "user", "content": "镜像层缓存要利用好，构建能快不少。"},
        ],
        "expected_semantics": ["docker", "部署", "容器"],
    },
]


def _pick(pool: list[str], rng: random.Random) -> str:
    return rng.choice(pool)


def _build_turn(role: str, content: str, ts: datetime) -> dict:
    return {
        "role": role,
        "content": content,
        "timestamp": ts.isoformat(timespec="seconds"),
    }


class ConversationGenerator:
    """生成多轮对话数据用于记忆系统压测。

    所有方法均为静态方法，可按需调用。默认使用固定随机种子保证可复现性。
    """

    # 场景池: (内容池, 权重) — 权重决定该场景出现概率
    _SCENARIOS: list[tuple[list[str], int]] = [
        (_TECH_TURNS, 3),
        (_DAILY_TURNS, 2),
        (_KNOWLEDGE_TURNS, 2),
        (_CODE_REVIEW_TURNS, 2),
        (_NOISE_TURNS, 1),  # 噪声占比较低，模拟真实对话分布
    ]

    @staticmethod
    def _build_pool(seed: int | None = None) -> tuple[random.Random, list[str]]:
        rng = random.Random(seed if seed is not None else _DEFAULT_SEED)
        pool: list[str] = []
        for turns, weight in ConversationGenerator._SCENARIOS:
            pool.extend(turns * weight)
        rng.shuffle(pool)
        return rng, pool

    @staticmethod
    def generate_single_conversation(
        num_turns: int = 100,
        *,
        seed: int | None = None,
    ) -> list[dict]:
        """生成单次多轮对话 (默认 100 轮)。

        每轮结构: {"role": "user"/"assistant", "content": "...", "timestamp": "..."}
        内容覆盖: 技术讨论、日常对话、知识问答、代码审查、噪声等场景。
        """
        rng, pool = ConversationGenerator._build_pool(seed)
        base_ts = datetime(2026, 1, 1, 9, 0, 0)
        conversation: list[dict] = []
        for i in range(num_turns):
            role = "user" if i % 2 == 0 else "assistant"
            content = _pick(pool, rng)
            ts = base_ts + timedelta(minutes=i * 2)
            conversation.append(_build_turn(role, content, ts))
        return conversation

    @staticmethod
    def generate_batch(
        num_conversations: int = 10,
        turns_per_conversation: int = 50,
        *,
        seed: int | None = None,
    ) -> list[list[dict]]:
        """批量生成对话。

        返回外层 list 长度 = num_conversations，每个元素是一次多轮对话。
        每条对话使用递增种子，保证整体可复现且彼此不同。
        """
        base_seed = seed if seed is not None else _DEFAULT_SEED
        batch: list[list[dict]] = []
        for idx in range(num_conversations):
            conv = ConversationGenerator.generate_single_conversation(
                turns_per_conversation, seed=base_seed + idx
            )
            batch.append(conv)
        return batch

    @staticmethod
    def generate_known_semantics() -> list[dict]:
        """生成已知语义的对话 (用于 L3 准确率测试)。

        每组结构:
            {
                "conversation": [{"role","content","timestamp"}, ...],
                "expected_semantics": ["关键词1", "关键词2", ...],
            }
        expected_semantics 用于与 sponge_engine 提取结果做交集/并集计算准确率。
        """
        rng = random.Random(_DEFAULT_SEED)
        results: list[dict] = []
        base_ts = datetime(2026, 1, 1, 9, 0, 0)
        for group in _KNOWN_SEMANTIC_GROUPS:
            conv: list[dict] = []
            for i, msg in enumerate(group["conversation"]):
                ts = base_ts + timedelta(minutes=i * 3)
                conv.append(_build_turn(msg["role"], msg["content"], ts))
            results.append(
                {
                    "topic": group["topic"],
                    "conversation": conv,
                    "expected_semantics": list(group["expected_semantics"]),
                }
            )
        # shuffle 顺序但保持可复现
        rng.shuffle(results)
        return results
