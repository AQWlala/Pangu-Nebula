import asyncio
import tempfile
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from server.main import app
from server.db.connection import DatabaseConnection
from server.db.models import create_tables


@pytest.fixture(scope="function")
def test_client():
    return TestClient(app)


@pytest.fixture(scope="function")
async def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    test_db_conn = DatabaseConnection(db_path=tmp_path)
    await test_db_conn.init()

    conn = await test_db_conn.acquire()
    try:
        await create_tables(conn)
    finally:
        await test_db_conn.release(conn)

    yield test_db_conn

    os.unlink(tmp_path)


@pytest.fixture(scope="function")
def test_provider_mock():
    with patch("server.api.chat.provider_registry") as mock:
        mock.get_provider.return_value = MagicMock()
        mock.get_provider.return_value.generate.return_value = {"content": "test response"}
        yield mock
