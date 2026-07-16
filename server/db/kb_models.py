"""知识库元数据 ORM 模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.db.orm import Base


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    graph_built_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    relations_as_source = relationship("KBRelation", foreign_keys="KBRelation.source_id", back_populates="source")
    relations_as_target = relationship("KBRelation", foreign_keys="KBRelation.target_id", back_populates="target")


class KBRelation(Base):
    __tablename__ = "kb_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("kb_documents.id"), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), ForeignKey("kb_documents.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    source_method: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    source = relationship("KBDocument", foreign_keys=[source_id], back_populates="relations_as_source")
    target = relationship("KBDocument", foreign_keys=[target_id], back_populates="relations_as_target")
