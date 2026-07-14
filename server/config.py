import os, sys
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


def _get_app_dir() -> Path:
    """Resolve the application data directory.

    - Frozen (PyInstaller onedir): use platform-appropriate user data dir
      (%LOCALAPPDATA%/PanguNebula on Windows, etc.), because the exe directory
      may be read-only (e.g., C:/Program Files/).
    - Dev mode: use the project root (one level above server/).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller onedir – use OS user data directory
        import platform
        system = platform.system()
        if system == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")))
        elif system == "Darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "PanguNebula"
    # Dev mode: project root (parent of the server/ directory)
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

    # v2.1.0 Phase 0 — Tauri sidecar feature flag
    # "pywebview" (default, v2.0.x behavior) or "tauri" (v2.1.0 Phase 0+)
    shell: str = "pywebview"
    # Bearer token for IPC auth between Tauri main process and Python sidecar.
    # Empty in pywebview mode (no auth); set by launch.py in tauri mode.
    # Reads NEBULA_TOKEN (not NEBULA_SIDECAR_TOKEN) to match launch.py env vars.
    sidecar_token: str = Field(default="", validation_alias="NEBULA_TOKEN")
    # Port actually bound by sidecar (set by launch.py in tauri mode).
    # Reads NEBULA_PORT. Defaults to 0 (use server_port at runtime).
    sidecar_port: int = Field(default=0, validation_alias="NEBULA_PORT")

    model_config = {"env_prefix": "NEBULA_", "env_file": ".env"}


def load_settings() -> Settings:
    return Settings()
