from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    server_port: int = 7860
    db_path: str = "data/nebula.db"
    database_url: str = "sqlite+aiosqlite:///data/nebula.db"
    debug: bool = True
    provider_default: str = ""

    model_config = {"env_prefix": "NEBULA_", "env_file": ".env"}


def load_settings() -> Settings:
    return Settings()
