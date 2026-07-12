import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from server.main import app
from server.db.orm import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
def test_client():
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(scope="function")
def mock_provider():
    with patch("server.providers.registry.get_provider") as mock_get,          patch("server.providers.registry.is_registered", return_value=True):
        provider = MagicMock()

        async def _fake_generate(messages, model, temperature=0.7, max_tokens=4096):
            yield "mock response"

        provider.generate = _fake_generate
        provider.info.return_value = {
            "name": "mock", "capabilities": {"chat": True},
            "supported_models": ["mock-model"], "available": True,
        }
        mock_get.return_value = provider
        yield mock_get
