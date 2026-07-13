# -*- coding: utf-8 -*-
"""Pangu Nebula desktop application entry point.

Launches uvicorn backend + PyWebView desktop window.

Shell modes (controlled by NEBULA_SHELL env var, v2.1.0 Phase 0):
- NEBULA_SHELL=pywebview (default): PyWebView 桌面窗口模式 (v2.0.x 原行为)
- NEBULA_SHELL=tauri: Tauri 2 sidecar 模式 (v2.1.0 Phase 0 新增)
  * 不开窗口, 仅启动 FastAPI 后端
  * 动态端口 (OS 分配) + stdout 输出 PORT=xxxxx + TOKEN=yyyy
  * 供 Tauri 主进程读取并通过 window.__NEBULA_PORT__/__NEBULA_TOKEN__ 注入前端

Usage:
    python launch.py                    # Default (auto port + desktop window)
    python launch.py --port 8080        # Specify port
    python launch.py --host 0.0.0.0     # Specify listen address
    python launch.py --no-window        # Backend-only mode (no window, for debugging)
    python launch.py --version          # Show version
    $env:NEBULA_SHELL="tauri"; python launch.py  # Tauri sidecar 模式
"""
import argparse
import os
import secrets
import socket
import sys
import threading
import time

import uvicorn

VERSION = "0.1.0"

# Shell mode: "pywebview" (default) or "tauri" (Phase 0 sidecar)
SHELL_MODE = os.environ.get("NEBULA_SHELL", "pywebview").lower()

# When running as a frozen PyInstaller app with console=False (windowed
# subsystem), stdout/stderr are not connected to any console.  Writing to
# them would raise OSError and crash the process.  Redirect to devnull
# early, before any print statement or library log output.
#
# EXCEPTION: Tauri sidecar mode (NEBULA_SHELL=tauri) requires stdout to
# communicate PORT= and TOKEN= to the Tauri parent process. In that mode
# stdout must NOT be redirected. Tauri sidecar is always launched with
# stdout piped, so writes are safe.
if getattr(sys, "frozen", False) and SHELL_MODE != "tauri":
    try:
        sys.stdout.write("")
    except (OSError, IOError):
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")


def find_available_port(start_port=7860):
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
        port += 1
    raise RuntimeError("No available port found")


def allocate_sidecar_port() -> int:
    """Allocate an OS-assigned free port for Tauri sidecar mode.

    Binds to ("127.0.0.1", 0) to let the OS pick a free port, then
    immediately releases it so uvicorn can rebind. There is a tiny race
    window between close() and uvicorn's bind(), but in practice the
    same port is reused because the socket is in TIME_WAIT only after
    a connection, not after a bare bind+close.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def emit_sidecar_handshake(port: int, token: str) -> None:
    """Emit PORT= and TOKEN= lines to stdout for the Tauri parent process.

    Format (one key per line, terminated with newline):
        PORT=12345
        TOKEN=<64 hex chars>
        READY
    The Tauri Rust parent reads stdout line-by-line and parses these.
    After READY, Tauri starts polling /health/ready.
    """
    sys.stdout.write(f"PORT={port}\n")
    sys.stdout.write(f"TOKEN={token}\n")
    sys.stdout.write("READY\n")
    sys.stdout.flush()


def run_sidecar_only(host: str = "127.0.0.1", port: int | None = None) -> None:
    """Tauri sidecar mode: start FastAPI backend only, no desktop window.

    Phase 0 (v2.1.0) entry point invoked when NEBULA_SHELL=tauri.
    1. Allocate dynamic port (OS-assigned) unless --port given
    2. Generate random Bearer token for IPC auth
    3. Emit PORT/TOKEN/READY to stdout
    4. Export NEBULA_PORT/NEBULA_TOKEN to env (read by server/main.py)
    5. Start uvicorn (blocking)
    """
    if port is None:
        port = allocate_sidecar_port()
    token = secrets.token_hex(32)
    # Export to env so server.config.Settings picks them up via env_prefix=NEBULA_
    os.environ["NEBULA_PORT"] = str(port)
    os.environ["NEBULA_TOKEN"] = token
    emit_sidecar_handshake(port, token)
    # Start uvicorn with app object (no reload in sidecar mode)
    from server.main import app
    uvicorn.run(app, host=host, port=port, log_level="warning")


def create_window(port, server_shutdown_func):
    """Create PyWebView desktop window (lazy import, desktop mode only).

    pywebview 6.x removed the on_closed parameter; webview.start() blocks
    until the window is closed, then we call the shutdown callback.
    """
    import webview  # lazy import: pywebview is optional, desktop mode only
    url = f"http://127.0.0.1:{port}"
    webview.create_window(
        title="Pangu Nebula",
        url=url,
        width=1280,
        height=800,
        frameless=True,
    )
    webview.start()  # blocks until window closed
    server_shutdown_func()  # cleanup backend after window closes


def parse_args():
    parser = argparse.ArgumentParser(
        prog="pangu-nebula",
        description="Pangu Nebula AI Agent Platform - desktop app entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python launch.py                  default launch\n"
            "  python launch.py --port 8080      specify port\n"
            "  python launch.py --no-window      backend-only mode\n"
            "  python launch.py --version        show version\n"
        ),
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Backend listen port (default: auto-select from 7860)",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Backend listen address (default 127.0.0.1, local only)",
    )
    parser.add_argument(
        "--no-window", action="store_true",
        help="Start backend only, no desktop window (for debugging / server deploy)",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable uvicorn hot reload (effective with --no-window)",
    )
    parser.add_argument(
        "--version", action="version", version=f"Pangu Nebula v{VERSION}",
    )
    return parser.parse_args()


def start_server(host, port, reload=False):
    """Start uvicorn backend.

    reload mode (dev): use string import for hot reload.
    Non-reload mode (packaged): pass app object directly, avoids PyInstaller
    importlib dynamic import failure.
    """
    if reload:
        uvicorn.run(
            "server.main:app",
            host=host,
            port=port,
            reload=True,
            log_level="info",
        )
    else:
        from server.main import app
        uvicorn.run(app, host=host, port=port, log_level="info")


def wait_for_server(host, port, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def main():
    args = parse_args()

    # Tauri sidecar mode: emit PORT/TOKEN to stdout, no window
    if SHELL_MODE == "tauri":
        run_sidecar_only(host=args.host, port=args.port)
        return

    port = args.port if args.port else find_available_port()
    print(f"Pangu Nebula v{VERSION}")
    print(f"Backend: http://{args.host}:{port}")

    # Backend-only mode
    if args.no_window:
        print("[no-window mode] Backend only, press Ctrl+C to exit")
        start_server(args.host, port, reload=args.reload)
        return

    # Desktop mode: backend thread + PyWebView window
    server_thread = threading.Thread(
        target=start_server,
        args=(args.host, port),
        kwargs={"reload": False},
        daemon=True,
    )
    server_thread.start()

    if not wait_for_server(args.host, port):
        print("Error: backend failed to start", file=sys.stderr)
        sys.exit(1)

    print(f"Opening desktop window: http://{args.host}:{port}")
    create_window(port, lambda: None)


if __name__ == "__main__":
    main()
