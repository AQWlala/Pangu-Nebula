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
from .migrations import run_lightweight_migrations
from ..config import load_settings

settings = load_settings()
database_url = settings.database_url

# v2.2.1 P2: 显式配置连接池 — 防止 stale connection + 控制并发
# SQLite (默认 aiosqlite): 仅加 pool_pre_ping (SQLite 用 SingletonThreadPool,
#   pool_size/max_overflow 会被 SQLAlchemy 拒绝; pool_recycle 无意义因 SQLite
#   无服务端连接超时)
# PostgreSQL/MySQL: 完整连接池配置 (pool_size/max_overflow/pool_recycle)
_is_sqlite = database_url.startswith("sqlite")
_engine_kwargs: dict = {"pool_pre_ping": True}
if not _is_sqlite:
    _engine_kwargs.update({
        "pool_size": 10,       # 连接池大小
        "max_overflow": 20,    # 溢出连接数
        "pool_recycle": 1800,  # 30 分钟回收,防止长连接断网
    })
engine = create_async_engine(database_url, **_engine_kwargs)
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
        # v2.2.0: 补齐 create_all 无法追加的新列,旧库平滑升级
        await conn.run_sync(run_lightweight_migrations)
