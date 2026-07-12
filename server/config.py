import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings


def _get_app_dir() -> Path:
    """获取应用根目录。

    PyInstaller 打包后:使用 exe 所在目录(用户数据应放这里,可写)
    开发模式:使用项目根目录
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller onedir 模式: exe 所在目录
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# 应用根目录(打包后为 exe 所在目录,开发时为项目根)
APP_DIR = _get_app_dir()
# 数据目录(数据库等运行时数据)
DATA_DIR = APP_DIR / "data"


class Settings(BaseSettings):
    server_port: int = 7860
    db_path: str = str(DATA_DIR / "nebula.db")
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'nebula.db'}"
    debug: bool = True
    provider_default: str = ""

    model_config = {"env_prefix": "NEBULA_", "env_file": ".env"}


def load_settings() -> Settings:
    return Settings()
