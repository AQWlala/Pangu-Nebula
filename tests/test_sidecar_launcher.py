"""P0-W0 Sidecar launcher tests (v2.1.1)

Tests for launch.py Tauri sidecar mode:
- Port allocation (OS-assigned dynamic port)
- Handshake protocol (PORT=/TOKEN=/READY stdout output)
- Environment variable injection (NEBULA_PORT/NEBULA_TOKEN)
- Uvicorn startup (mocked, no actual server)
"""

import os
from unittest.mock import patch

import pytest

from launch import (
    allocate_os_port,
    emit_handshake,
    find_available_port,
    run_sidecar,
)


# ----------------------------------------------------------------------
# find_available_port
# ----------------------------------------------------------------------

def test_find_available_port_returns_valid_port():
    """find_available_port returns an int in valid port range [1, 65535]"""
    port = find_available_port()
    assert isinstance(port, int)
    assert 1 <= port <= 65535


# ----------------------------------------------------------------------
# allocate_os_port
# ----------------------------------------------------------------------

def test_allocate_os_port_returns_valid_port():
    """allocate_os_port returns an int in valid port range [1, 65535]"""
    port = allocate_os_port()
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_allocate_os_port_returns_different_ports():
    """Consecutive calls return at least 2 distinct ports (OS-assigned)"""
    ports = {allocate_os_port() for _ in range(5)}
    assert len(ports) >= 2


# ----------------------------------------------------------------------
# emit_handshake
# ----------------------------------------------------------------------

def test_emit_handshake_format(capsys):
    """Handshake emits exactly 3 lines: PORT=, TOKEN=, READY"""
    test_port = 12345
    test_token = "a" * 64
    emit_handshake(test_port, test_token)
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == f"PORT={test_port}"
    assert lines[1] == f"TOKEN={test_token}"
    assert lines[2] == "READY"


def test_emit_handshake_flushes_stdout(capsys):
    """Handshake flushes stdout so Tauri parent receives lines immediately"""
    emit_handshake(9999, "b" * 64)
    captured = capsys.readouterr()
    assert "PORT=9999" in captured.out
    assert "READY" in captured.out


# ----------------------------------------------------------------------
# run_sidecar
# ----------------------------------------------------------------------

def test_run_sidecar_sets_env_vars():
    """run_sidecar sets NEBULA_PORT and NEBULA_TOKEN in os.environ"""
    test_port = 12345
    with (
        patch("launch.allocate_os_port", return_value=test_port),
        patch("launch.emit_handshake") as mock_handshake,
        patch("launch.uvicorn.run") as mock_uvicorn,
    ):
        run_sidecar(host="127.0.0.1", port=test_port)
        assert os.environ["NEBULA_PORT"] == str(test_port)
        assert "NEBULA_TOKEN" in os.environ
        assert len(os.environ["NEBULA_TOKEN"]) == 64
        mock_handshake.assert_called_once()
        mock_uvicorn.assert_called_once()


def test_run_sidecar_auto_port():
    """run_sidecar uses allocate_os_port when port is None"""
    with (
        patch("launch.allocate_os_port", return_value=9999) as mock_port,
        patch("launch.emit_handshake"),
        patch("launch.uvicorn.run"),
    ):
        run_sidecar(host="127.0.0.1", port=None)
        mock_port.assert_called_once()


def test_run_sidecar_emits_handshake_with_correct_port_and_token():
    """run_sidecar emits handshake with the allocated port and generated token"""
    test_port = 8888
    with (
        patch("launch.allocate_os_port", return_value=test_port),
        patch("launch.emit_handshake") as mock_handshake,
        patch("launch.uvicorn.run"),
    ):
        run_sidecar(host="127.0.0.1", port=test_port)
        mock_handshake.assert_called_once()
        args = mock_handshake.call_args[0]
        assert args[0] == test_port
        assert len(args[1]) == 64