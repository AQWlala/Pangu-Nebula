# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller Linux 打包配置 - Pangu Nebula

将 Pangu Nebula 打包为 Linux 桌面应用:
- 入口: launch.py (PyWebView 启动 uvicorn 后端 + 桌面窗口)
- 模式: onedir (启动快,支持增量更新)
- GUI 应用 (console=False)
- pywebview Linux 后端: 优先使用 GTK/WebKitGTK,需系统安装 libgtk-3 libwebkit2gtk-4.0
- 主密钥: Linux 无 DPAPI,自动 fallback 到 0600 文件权限模式

Linux 特有说明:
- 需要系统依赖: libgtk-3-0, libwebkit2gtk-4.0-37, libglib2.0-0 (Debian/Ubuntu)
- 推荐使用 AppImage / Flatpak 二次封装以提升分发兼容性
- 输出目录: dist/PanguNebula/

Usage:
    pyinstaller pangu-nebula-linux.spec --noconfirm
"""

import os

block_cipher = None

BASE_DIR = os.path.abspath(SPECPATH)

# ---------- 数据文件 ----------
datas = []

# 前端构建产物
frontend_dist = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.isdir(frontend_dist):
    datas.append((frontend_dist, "frontend/dist"))

# .env 文件 (如存在)
env_file = os.path.join(BASE_DIR, ".env")
if os.path.isfile(env_file):
    datas.append((env_file, "."))

# data/ 为运行时数据 (DB、密钥等) - 不打包进应用
# 首次运行时在可执行文件同级目录创建

# ---------- 隐藏导入 ----------
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("server")

hiddenimports += [
    # uvicorn 动态子模块
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # SQLAlchemy SQLite 方言 + 异步驱动
    "sqlalchemy.dialects.sqlite",
    "aiosqlite",
    # FastAPI / Starlette 中间件 + 静态文件
    "fastapi.middleware.cors",
    "starlette.staticfiles",
    # pydantic-settings
    "pydantic_settings",
    # python-dotenv
    "dotenv",
] + collect_submodules("webview")

# ---------- 排除模块 ----------
excludes = [
    "tkinter",
    "matplotlib",
    "pytest",
    "_pytest",
    "pytest_asyncio",
    # Windows 专有模块
    "ctypes.wintypes",
    # macOS 专有模块
    "objc",
    "Foundation",
    "AppKit",
    "WebKit",
]

# ---------- 图标 ----------
icon_path = None  # Linux 不强制要求图标,可在 .desktop 文件中指定

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
    icon=icon_path,
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
