import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from .orm import Base
from . import swarm_models  # noqa: F401 - register Swarm/SwarmWorker tables
from . import autowork_models  # noqa: F401
from . import dag_models  # noqa: F401
from . import wiki_review_models  # noqa: F401
from . import acp_models  # noqa: F401
from . import kb_models  # noqa: F401 - register KB tables
from . import cu_models  # noqa: F401 - register CU tables
from ..config import load_settings

settings = load_settings()
database_url = settings.database_url

engine = create_async_engine(database_url)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    if database_url.startswith("sqlite"):
        db_path = database_url.split("///")[-1]
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
