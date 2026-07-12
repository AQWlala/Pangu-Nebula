import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings


def _get_app_dir() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _get_app_dir()
DATA_DIR = APP_DIR / "data"


class Settings(BaseSettings):
    server_port: int = 7860
    db_path: str = str(DATA_DIR / "nebula.db")
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'nebula.db'}"
    debug: bool = True
    provider_default: str = ""
    cors_origins: str = (
        "http://127.0.0.1:*,http://localhost:*,app://*,tauri://*"
    )

    model_config = {"env_prefix": "NEBULA_", "env_file": ".env"}


def load_settings() -> Settings:
    return Settings()
