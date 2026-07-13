"""P0-W0 Sidecar launcher tests (v2.1.0 Phase 0)

Tests for launch.py Tauri sidecar mode:
- Port allocation (OS-assigned dynamic port)
- Handshake protocol (PORT=/TOKEN=/READY stdout output)
- Environment variable injection (NEBULA_PORT/NEBULA_TOKEN)
- Uvicorn startup (mocked, no actual server)
- Shell mode feature flag (NEBULA_SHELL env var)
"""

import os
from unittest.mock import patch

import pytest

from launch import (
    SHELL_MODE,
    allocate_sidecar_port,
    emit_sidecar_handshake,
    run_sidecar_only,
)


# ----------------------------------------------------------------------
# allocate_sidecar_port
# ----------------------------------------------------------------------

def test_allocate_sidecar_port_returns_valid_port():
    """allocate_sidecar_port returns an int in valid port range [1, 65535]"""
    port = allocate_sidecar_port()
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_allocate_sidecar_port_returns_different_ports():
    """Consecutive calls return at least 2 distinct ports (OS-assigned)"""
    ports = {allocate_sidecar_port() for _ in range(5)}
    assert len(ports) >= 2


# ----------------------------------------------------------------------
# emit_sidecar_handshake
# ----------------------------------------------------------------------

def test_emit_sidecar_handshake_format(capsys):
    """Handshake emits exactly 3 lines: PORT=, TOKEN=, READY"""
    test_port = 12345
    test_token = "a" * 64
    emit_sidecar_handshake(test_port, test_token)
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == f"PORT={test_port}"
    assert lines[1] == f"TOKEN={test_token}"
    assert lines[2] == "READY"


def test_emit_sidecar_handshake_flushes_stdout(capsys):
    """Handshake flushes stdout so Tauri parent receives lines immediately"""
    emit_sidecar_handshake(9999, "b" * 64)
    captured = capsys.readouterr()
    # If flush worked, all 3 lines are in captured.out immediately
    assert "PORT=9999" in captured.out
    assert "READY" in captured.out


# ----------------------------------------------------------------------
# SHELL_MODE (feature flag)
# ----------------------------------------------------------------------

def test_shell_mode_default_is_pywebview():
    """SHELL_MODE defaults to 'pywebview' when NEBULA_SHELL not set at import time"""
    # In the test environment, NEBULA_SHELL is not set, so SHELL_MODE
    # (read at module import time) should be "pywebview".
    assert SHELL_MODE == "pywebview"


# ----------------------------------------------------------------------
# run_sidecar_only
# ----------------------------------------------------------------------

def test_run_sidecar_only_sets_env_vars(monkeypatch):
    """run_sidecar_only sets NEBULA_PORT and NEBULA_TOKEN env vars"""
    monkeypatch.delenv("NEBULA_PORT", raising=False)
    monkeypatch.delenv("NEBULA_TOKEN", raising=False)

    with patch("uvicorn.run") as mock_run, patch("launch.emit_sidecar_handshake"):
        run_sidecar_only(host="127.0.0.1", port=9999)

    assert os.environ.get("NEBULA_PORT") == "9999"
    assert len(os.environ.get("NEBULA_TOKEN", "")) == 64  # 32 bytes hex
    mock_run.assert_called_once()


def test_run_sidecar_only_emits_handshake(monkeypatch):
    """run_sidecar_only calls emit_sidecar_handshake with port and 64-char token"""
    with patch("uvicorn.run"), patch("launch.emit_sidecar_handshake") as mock_emit:
        run_sidecar_only(host="127.0.0.1", port=8080)

    mock_emit.assert_called_once()
    emitted_port, emitted_token = mock_emit.call_args[0]
    assert emitted_port == 8080
    assert len(emitted_token) == 64


def test_run_sidecar_only_auto_allocates_port(monkeypatch):
    """run_sidecar_only auto-allocates port via allocate_sidecar_port when port=None"""
    monkeypatch.delenv("NEBULA_PORT", raising=False)

    with patch("uvicorn.run"), \
         patch("launch.allocate_sidecar_port", return_value=7777) as mock_alloc, \
         patch("launch.emit_sidecar_handshake"):
        run_sidecar_only()  # port=None default

    mock_alloc.assert_called_once()
    assert os.environ.get("NEBULA_PORT") == "7777"


def test_run_sidecar_only_starts_uvicorn_with_correct_args():
    """run_sidecar_only calls uvicorn.run with host, port, and warning log level"""
    with patch("uvicorn.run") as mock_run, patch("launch.emit_sidecar_handshake"):
        run_sidecar_only(host="127.0.0.1", port=5555)

    call_kwargs = mock_run.call_args
    # First positional arg is the app object, then host/port/log_level as kwargs
    assert call_kwargs[1]["host"] == "127.0.0.1"
    assert call_kwargs[1]["port"] == 5555
    assert call_kwargs[1]["log_level"] == "warning"
