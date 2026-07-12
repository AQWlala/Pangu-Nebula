from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from .orm import Base


class AutoWorkSession(Base):
    __tablename__ = "autowork_sessions"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="pending")  # pending/running/completed/failed/paused
    priority = Column(Integer, default=0)
    assigned_to = Column(String(100), nullable=True)  # 认领者
    config = Column(JSON, default=dict)  # 任务配置
    result = Column(Text, nullable=True)  # 执行结果
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
