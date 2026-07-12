# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller macOS 打包配置 - Pangu Nebula

将 Pangu Nebula 打包为 macOS 桌面应用:
- 入口: launch.py (PyWebView 启动 uvicorn 后端 + 桌面窗口)
- 模式: onedir (启动快,支持增量更新)
- GUI 应用 (console=False, windowed subsystem)
- pywebview macOS 后端: 默认使用 Cocoa/WebKit (系统自带),无需额外依赖
- 主密钥: macOS 无 DPAPI,自动 fallback 到 0600 文件权限模式

macOS 特有说明:
- .app 后缀目录由 COLLECT 自动生成 (BUNDLE 选项)
- 代码签名: 通过 codesign_identity 参数配置 (CI 中可设置为 ad-hoc)
- pywebview 在 macOS 上使用系统 WebKit,无需打包 Chromium

Usage:
    pyinstaller pangu-nebula-mac.spec --noconfirm
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
# 首次运行时在 .app 同级目录创建

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
    # Linux 专有模块
    "gi",
    "Gtk",
]

# ---------- 图标 ----------
icon_path = os.path.join(BASE_DIR, "frontend", "public", "app.icns")
if not os.path.isfile(icon_path):
    for candidate in ["app.icns", "icon.icns", "logo.icns"]:
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
    upx=False,  # macOS 不使用 UPX (与代码签名冲突)
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # CI 中可设为 "-" (ad-hoc 签名)
    entitlements_file=None,
    icon=icon_path if (icon_path and os.path.isfile(icon_path)) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PanguNebula",
)

# 生成 .app bundle (macOS 应用程序包)
# 注意: BUNDLE 仅在 macOS 上有效,CI runner 为 macos-latest 时才会执行
app = BUNDLE(
    coll,
    name="PanguNebula.app",
    icon=icon_path if (icon_path and os.path.isfile(icon_path)) else None,
    bundle_identifier="com.pangu.nebula",
    info_plist={
        "CFBundleName": "Pangu Nebula",
        "CFBundleDisplayName": "Pangu Nebula",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.13",
    },
)
