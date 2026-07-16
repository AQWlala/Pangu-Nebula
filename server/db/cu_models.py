"""Computer Use 审计日志 ORM 模型"""
from datetime import datetime
from sqlalchemy import String, Text, Integer, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from server.db.orm import Base


class CUAuditLog(Base):
    __tablename__ = "cu_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_payload: Mapped[str] = mapped_column(Text, nullable=False)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
