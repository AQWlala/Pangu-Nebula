"""ACP (Agent Communication Protocol) ORM 模型 (T3.4-T3.6)

允许外部 Agent (Claude Code, Codex, Gemini CLI) 注册并调用 Pangu Nebula 的:
- 记忆系统 (读写记忆)
- 蜂群能力 (发起蜂群任务)
- 技能系统 (调用技能)
"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, JSON, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from .orm import Base


class ExternalAgent(Base):
    """外部 Agent 注册"""

    __tablename__ = "external_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # generic/claude_code/codex/gemini_cli
    agent_type: Mapped[str] = mapped_column(String(50), default="generic")
    # 调用端点
    endpoint: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # 能力声明
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    # 认证 token
    auth_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_called: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class ACPCallLog(Base):
    """ACP 调用日志"""

    __tablename__ = "acp_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # call_memory/call_swarm/call_skill
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    request: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ok/error/timeout
    status: Mapped[str] = mapped_column(String(20), default="ok")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )
