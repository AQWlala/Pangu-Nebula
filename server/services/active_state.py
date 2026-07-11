import json
from pathlib import Path

_STATE_FILE = Path("data/active_state.json")


def _ensure_dir() -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_state() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state: dict) -> None:
    _ensure_dir()
    _STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_active_persona_id() -> int | None:
    value = _read_state().get("active_persona_id")
    return int(value) if value is not None else None


def set_active_persona_id(persona_id: int) -> None:
    _write_state({"active_persona_id": persona_id})


def clear_active_persona_id() -> None:
    _write_state({})
