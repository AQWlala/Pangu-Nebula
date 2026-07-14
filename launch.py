# -*- coding: utf-8 -*-
"""Pangu Nebula application entry point (v2.1.0 — Tauri 2).

Launches the FastAPI backend. Desktop window is provided by the Tauri 2 shell.
Two modes:
- Default (Tauri sidecar): stdout emits PORT=/TOKEN=/READY for Tauri parent process
- --no-window: Standalone backend server (for debugging / Docker deployment)

Usage:
    python launch.py                       # Tauri sidecar mode (default)
    python launch.py --port 8080           # Specify port
    python launch.py --host 0.0.0.0        # Specify listen address
    python launch.py --no-window           # Standalone server mode
    python launch.py --no-window --reload  # Dev mode with hot reload
    python launch.py --version             # Show version
"""

import argparse
import os
import secrets
import socket
import sys
import time

import uvicorn

VERSION = "2.1.3"


# ---------------------------------------------------------------------------
# Frozen app stdout redirection (PyInstaller windowed subsystem safety)
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    try:
        sys.stdout.write("")
    except (OSError, IOError):
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")


# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------
def find_available_port(start_port: int = 7860) -> int:
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    raise RuntimeError("No available port found")


def allocate_os_port() -> int:
    """Let the OS pick a free port (used in Tauri sidecar mode)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Tauri sidecar handshake
# ---------------------------------------------------------------------------
def emit_handshake(port: int, token: str) -> None:
    """Emit PORT= / TOKEN= / READY to stdout for Tauri parent process."""
    sys.stdout.write(f"PORT={port}\n")
    sys.stdout.write(f"TOKEN={token}\n")
    sys.stdout.write("READY\n")
    sys.stdout.flush()


def run_sidecar(host: str = "127.0.0.1", port: int | None = None) -> None:
    """Tauri sidecar mode: start backend, emit handshake to stdout."""
    if port is None:
        port = allocate_os_port()
    token = secrets.token_hex(32)
    os.environ["NEBULA_PORT"] = str(port)
    os.environ["NEBULA_TOKEN"] = token
    emit_handshake(port, token)
    from server.main import app
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Standalone server (for dev / Docker)
# ---------------------------------------------------------------------------
def start_server(host: str, port: int, reload: bool = False) -> None:
    if reload:
        uvicorn.run("server.main:app", host=host, port=port, reload=True, log_level="info")
    else:
        from server.main import app
        uvicorn.run(app, host=host, port=port, log_level="info")


def wait_for_server(host: str, port: int, timeout: int = 10) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pangu-nebula",
        description="Pangu Nebula — metacognitive multi-agent runtime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python launch.py                  Tauri sidecar mode (default)\n"
            "  python launch.py --port 8080      specify port\n"
            "  python launch.py --no-window      standalone server (dev/debug)\n"
            "  python launch.py --version        show version\n"
        ),
    )
    parser.add_argument("--port", type=int, default=None, help="Backend listen port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Listen address")
    parser.add_argument("--no-window", action="store_true", help="Standalone server mode")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (with --no-window)")
    parser.add_argument("--version", action="version", version=f"Pangu Nebula v{VERSION}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # -- Standalone server mode --
    if args.no_window:
        port = args.port if args.port else find_available_port()
        print(f"Pangu Nebula v{VERSION}")
        print(f"Backend: http://{args.host}:{port}")
        print("[standalone mode] Press Ctrl+C to exit")
        start_server(args.host, port, reload=args.reload)
        return

    # -- Default: Tauri sidecar mode --
    run_sidecar(host=args.host, port=args.port)


if __name__ == "__main__":
    main()