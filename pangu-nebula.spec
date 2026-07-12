# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller packaging config - Pangu Nebula

Packages Pangu Nebula as a Windows desktop app:
- Entry: launch.py (PyWebView starts uvicorn backend + desktop window)
- Mode: onedir (fast startup, supports incremental updates)
- GUI app (console=False, windowed subsystem)

Usage:
    pyinstaller pangu-nebula.spec --noconfirm
"""

import os

block_cipher = None

BASE_DIR = os.path.abspath(SPECPATH)

# ---------- data files ----------
datas = []

# Frontend build output
frontend_dist = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.isdir(frontend_dist):
    datas.append((frontend_dist, "frontend/dist"))

# .env file (if exists)
env_file = os.path.join(BASE_DIR, ".env")
if os.path.isfile(env_file):
    datas.append((env_file, "."))

# data/ is runtime data (DB, keys, etc.) — NOT bundled in package.
# It is created on first run at the exe location.

# ---------- hidden imports ----------
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("server")

hiddenimports += [
    # uvicorn submodules (dynamic import)
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # SQLAlchemy SQLite dialect + async driver
    "sqlalchemy.dialects.sqlite",
    "aiosqlite",
    # FastAPI / Starlette middleware + static files
    "fastapi.middleware.cors",
    "starlette.staticfiles",
    # pydantic-settings
    "pydantic_settings",
    # python-dotenv
    "dotenv",
] + collect_submodules("webview")

# ---------- excludes ----------
excludes = [
    "tkinter",
    "matplotlib",
    "pytest",
    "_pytest",
    "pytest_asyncio",
]

# ---------- icon ----------
icon_path = os.path.join(BASE_DIR, "frontend", "public", "app.ico")
if not os.path.isfile(icon_path):
    for candidate in ["app.ico", "icon.ico", "logo.ico"]:
        p = os.path.join(BASE_DIR, candidate)
        if os.path.isfile(p):
            icon_path = p
            break
    else:
        icon_path = None

a = Analysis(
    ["launch.py"],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PanguNebula",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if (icon_path and os.path.isfile(icon_path)) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PanguNebula",
)
