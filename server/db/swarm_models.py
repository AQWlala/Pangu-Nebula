from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .orm import Base


class Swarm(Base):
    __tablename__ = "swarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    subtasks: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow)

    workers: Mapped[list["SwarmWorker"]] = relationship(back_populates="swarm", cascade="all, delete-orphan")


class SwarmWorker(Base):
    __tablename__ = "swarm_workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    swarm_id: Mapped[int] = mapped_column(ForeignKey("swarms.id", ondelete="CASCADE"), nullable=False)
    subtask_id: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(50), default="openai")
    model_name: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    swarm: Mapped[Swarm] = relationship(back_populates="workers")
