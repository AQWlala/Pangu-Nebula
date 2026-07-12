"""Pangu Memory SDK — 类型定义

6 层认知记忆 + 元数据 + Memory 模型
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryLayer(str, Enum):
    """6 层认知记忆

    - L0 工作记忆: 瞬时上下文
    - L1 情景记忆: 具体事件、对话片段
    - L2 叙事记忆: 连贯的故事线
    - L3 语义记忆: 知识点、概念、事实
    - L4 程序记忆: 技能、流程、经验
    - L5 元认知: 身份、价值观、目标
    """

    L0_WORKING = "L0"
    L1_EPISODIC = "L1"
    L2_NARRATIVE = "L2"
    L3_SEMANTIC = "L3"
    L4_PROCEDURAL = "L4"
    L5_METACOGNITION = "L5"


class MemoryMetadata(BaseModel):
    """记忆元数据"""

    layer: MemoryLayer = MemoryLayer.L1_EPISODIC
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.5  # 0.0-1.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    source: str = ""  # 来源 (user/agent/system)
    backlinks: list[str] = Field(default_factory=list)  # 双向链接 (memory id 列表)
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展字段


class Memory(BaseModel):
    """记忆条目"""

    id: str = ""
    content: str
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
