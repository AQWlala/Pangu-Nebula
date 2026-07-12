from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from .orm import Base


class DAGNode(Base):
    __tablename__ = "dag_nodes"

    id = Column(Integer, primary_key=True)
    dag_id = Column(String(100), nullable=False)  # DAG 图 ID
    node_id = Column(String(100), nullable=False)  # 节点 ID (在 DAG 内唯一)
    title = Column(String(200), nullable=False)
    node_type = Column(String(50), default="task")  # task/decision/approval
    status = Column(String(20), default="pending")  # pending/running/completed/failed/skipped
    model = Column(String(100), nullable=True)  # 指定 LLM model
    brief = Column(Text, nullable=True)  # 节点 brief override
    config = Column(JSON, default=dict)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DAGEdge(Base):
    __tablename__ = "dag_edges"

    id = Column(Integer, primary_key=True)
    dag_id = Column(String(100), nullable=False)
    source_node_id = Column(String(100), nullable=False)
    target_node_id = Column(String(100), nullable=False)
    edge_type = Column(String(50), default="sequence")  # sequence/condition/parallel
    condition = Column(Text, nullable=True)  # 条件表达式 (edge_type=condition 时)
