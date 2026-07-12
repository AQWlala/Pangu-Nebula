# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - Pangu Nebula (Phase 11D)

将 Pangu Nebula 打包为 Windows 桌面应用:
- 入口: launch.py (PyWebView 启动 uvicorn 后端 + 桌面窗口)
- 模式: onedir (减少启动时间,便于增量更新)
- GUI 应用 (console=False)

使用方式:
    pyinstaller pangu-nebula.spec --noconfirm
"""

import os

block_cipher = None

# 项目根目录(SPEC 文件所在目录)
BASE_DIR = os.path.abspath(SPECPATH)

# ---------- 数据文件(datas) ----------
datas = []

# 前端构建产物
frontend_dist = os.path.join(BASE_DIR, 'frontend', 'dist')
if os.path.isdir(frontend_dist):
    datas.append((frontend_dist, 'frontend/dist'))

# 环境变量配置文件(如果存在)
env_file = os.path.join(BASE_DIR, '.env')
if os.path.isfile(env_file):
    datas.append((env_file, '.'))

# 数据库初始目录(打包后用于运行时存储)
data_dir = os.path.join(BASE_DIR, 'data')
if os.path.isdir(data_dir):
    datas.append((data_dir, 'data'))

# ---------- 隐藏导入(hiddenimports) ----------
from PyInstaller.utils.hooks import collect_submodules

# 自动收集 server 包下所有子模块(避免遗漏动态导入)
hiddenimports = collect_submodules('server')

# 额外添加第三方动态导入
hiddenimports += [
    # uvicorn 子模块(动态导入)
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
    # SQLAlchemy SQLite 方言 + 异步驱动
    'sqlalchemy.dialects.sqlite',
    'aiosqlite',
    # FastAPI / Starlette 中间件与静态文件
    'fastapi.middleware.cors',
    'starlette.staticfiles',
    # pydantic-settings
    'pydantic_settings',
    # python-dotenv
    'dotenv',
    # webview (pywebview) - 用 collect_submodules 收集全部子模块
] + collect_submodules('webview')

# ---------- 排除模块(excludes) ----------
excludes = [
    'tkinter',
    'matplotlib',
    'pytest',
    '_pytest',
    'pytest_asyncio',
]

# ---------- 图标 ----------
# PyInstaller 需要 .ico 格式,SVG 不支持。有 .ico 时用,否则无图标。
icon_path = os.path.join(BASE_DIR, 'frontend', 'public', 'app.ico')
if not os.path.isfile(icon_path):
    # 降级: 尝试其他常见图标位置
    for candidate in ['app.ico', 'icon.ico', 'logo.ico']:
        p = os.path.join(BASE_DIR, candidate)
        if os.path.isfile(p):
            icon_path = p
            break
    else:
        icon_path = None  # 无可用图标

a = Analysis(
    ['launch.py'],
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
    name='PanguNebula',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
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
    name='PanguNebula',
)
