# tests/test_phase0_models.py
import pytest
from sqlalchemy import inspect
from server.db.kb_models import KBDocument, KBRelation
from server.db.cu_models import CUAuditLog


def test_kb_document_model_fields():
    assert KBDocument.__tablename__ == "kb_documents"
    assert hasattr(KBDocument, "id")
    assert hasattr(KBDocument, "title")
    assert hasattr(KBDocument, "scope")
    assert hasattr(KBDocument, "confidence")
    assert hasattr(KBDocument, "checksum")

def test_kb_relation_model_fields():
    assert KBRelation.__tablename__ == "kb_relations"
    assert hasattr(KBRelation, "source_id")
    assert hasattr(KBRelation, "target_id")
    assert hasattr(KBRelation, "relation_type")

def test_cu_audit_log_model_fields():
    assert CUAuditLog.__tablename__ == "cu_audit_logs"
    assert hasattr(CUAuditLog, "task_id")
    assert hasattr(CUAuditLog, "step_index")
    assert hasattr(CUAuditLog, "action_type")
    assert hasattr(CUAuditLog, "result_status")

@pytest.mark.asyncio
async def test_kb_tables_created(db_session):
    """Verify KB tables are created by Base.metadata.create_all"""
    engine = db_session.bind
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "kb_documents" in tables
    assert "kb_relations" in tables

@pytest.mark.asyncio
async def test_cu_tables_created(db_session):
    """Verify CU tables are created by Base.metadata.create_all"""
    engine = db_session.bind
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "cu_audit_logs" in tables
