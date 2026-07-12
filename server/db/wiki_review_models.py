from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from .orm import Base


class WikiReviewItem(Base):
    __tablename__ = "wiki_review_items"

    id = Column(Integer, primary_key=True)
    wiki_id = Column(Integer, nullable=False)  # 关联的 wiki 页面
    title = Column(String(200), nullable=False)
    proposed_content = Column(Text, nullable=False)  # 提议的新内容
    current_content = Column(Text, nullable=True)  # 当前内容 (用于 diff)
    status = Column(String(20), default="pending")  # pending/merged/discarded
    scope = Column(String(100), default="default")  # 作用域
    proposed_by = Column(String(100), default="agent")  # 提议者
    review_note = Column(Text, nullable=True)  # 审核备注
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)


class URLSnapshot(Base):
    __tablename__ = "url_snapshots"

    id = Column(Integer, primary_key=True)
    url = Column(String(2000), nullable=False)
    snapshot_content = Column(Text, nullable=True)  # 抓取的快照内容
    snapshot_at = Column(DateTime, default=datetime.utcnow)
    content_type = Column(String(100), default="text/html")
    status = Column(String(20), default="ok")  # ok/failed/ssrf_blocked
