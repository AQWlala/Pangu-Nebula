#!/usr/bin/env python3
"""Pangu Nebula Sidecar 打包脚本 (v2.1.0 Phase 0 — P0-W6.4)

使用 PyInstaller 将 launch.py 打包为 Python sidecar 可执行文件,
输出到 src-tauri/resources/pangu-sidecar/ 供 Tauri 打包时作为 resource 嵌入。

关键差异 (vs pangu-nebula.spec):
- 输出名称: pangu-nebula-sidecar (不是 PanguNebula)
- 输出路径: src-tauri/resources/pangu-sidecar/ (不是 dist/)
- console=True: sidecar 需要 stdout 输出 PORT=/TOKEN= 握手信息给 Tauri 主进程
- 不打包 frontend/dist: sidecar 仅负责后端,前端由 Tauri WebView 加载

用法:
    python scripts/build_sidecar.py
    python scripts/build_sidecar.py --clean  # 先清理旧产物
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# 强制 stdout/stderr 使用 UTF-8 编码
# Windows CI 默认 cp1252 无法输出 emoji (✅/❌等),导致 UnicodeEncodeError
# Python 3.7+ 支持 sys.stdout.reconfigure()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 输出目录: Tauri resources
SIDECAR_OUTPUT_DIR = BASE_DIR / "src-tauri" / "resources" / "pangu-sidecar"

# PyInstaller spec 输出目录
SPEC_DIR = BASE_DIR / "build"

# 工作目录
WORK_DIR = BASE_DIR / "build" / "sidecar-work"


def clean_old_build() -> None:
    """清理旧的 sidecar 构建产物"""
    paths_to_clean = [
        SIDECAR_OUTPUT_DIR,
        WORK_DIR,
    ]
    for p in paths_to_clean:
        if p.exists():
            print(f"Cleaning: {p}")
            shutil.rmtree(p, ignore_errors=True)


def build_sidecar() -> int:
    """运行 PyInstaller 打包 sidecar"""
    # 确保输出目录存在
    SIDECAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # 设置 NEBULA_SHELL=tauri 环境 (影响 launch.py 中的 stdout 行为)
    os.environ["NEBULA_SHELL"] = "tauri"

    # PyInstaller 参数
    # --onedir: 目录模式 (比 onefile 启动快,支持增量更新)
    # --console: 保留 console (sidecar 需要 stdout 输出 PORT=/TOKEN=)
    # --collect-submodules: 自动收集 server/webview 的所有子模块
    # --distpath: 输出到 Tauri resources 目录
    # --workpath: 工作目录
    # --specpath: spec 文件输出目录
    pyinstaller_args = [
        str(BASE_DIR / "launch.py"),
        "--name=pangu-nebula-sidecar",
        "--onedir",
        "--console",  # sidecar 需要 stdout (PORT=/TOKEN= 握手)
        f"--distpath={SIDECAR_OUTPUT_DIR}",  # 输出到 src-tauri/resources/pangu-sidecar/
        f"--workpath={WORK_DIR}",
        f"--specpath={SPEC_DIR}",
        "--noconfirm",
        "--clean",
        # 收集子模块 (避免 ModuleNotFoundError)
        "--collect-submodules=server",
        "--collect-submodules=webview",
        "--collect-submodules=pangu_memory_sdk",
        # 隐式导入 (PyInstaller 无法自动检测的动态导入)
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=aiosqlite",
        "--hidden-import=fastapi.middleware.cors",
        "--hidden-import=starlette.staticfiles",
        "--hidden-import=pydantic_settings",
        "--hidden-import=dotenv",
        # 排除不需要的模块 (减小体积)
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=pytest",
        "--exclude-module=_pytest",
        "--exclude-module=pytest_asyncio",
        # .env 文件 (如果存在)
    ]

    # 添加 .env 作为数据文件 (如果存在)
    env_file = BASE_DIR / ".env"
    if env_file.is_file():
        pyinstaller_args.append(f"--add-data={env_file}{os.pathsep}.")

    # 添加 icon (如果存在)
    for icon_candidate in [
        BASE_DIR / "frontend" / "public" / "app.ico",
        BASE_DIR / "app.ico",
        BASE_DIR / "icon.ico",
    ]:
        if icon_candidate.is_file():
            pyinstaller_args.append(f"--icon={icon_candidate}")
            break

    print("=" * 60)
    print("Pangu Nebula Sidecar Build (P0-W6.4)")
    print("=" * 60)
    print(f"  Entry:       launch.py")
    print(f"  Output:      {SIDECAR_OUTPUT_DIR}")
    print(f"  Mode:        onedir (console=True for stdout handshake)")
    print(f"  NEBULA_SHELL: tauri")
    print(f"  Args:        {' '.join(pyinstaller_args[:5])} ...")
    print("=" * 60)

    # 使用 PyInstaller Python API
    import PyInstaller.__main__ as pyinstaller

    try:
        pyinstaller.run(pyinstaller_args)
    except SystemExit as e:
        if e.code != 0:
            print(f"ERROR: PyInstaller failed with exit code {e.code}", file=sys.stderr)
            return e.code if isinstance(e.code, int) else 1

    # 验证产物
    # PyInstaller --onedir 在 --distpath 下创建以 --name 命名的子目录
    sidecar_exe = SIDECAR_OUTPUT_DIR / "pangu-nebula-sidecar" / "pangu-nebula-sidecar"
    if sys.platform == "win32":
        sidecar_exe = sidecar_exe.with_suffix(".exe")
    elif sys.platform == "darwin":
        pass  # macOS 无后缀

    if not sidecar_exe.exists():
        print(f"ERROR: Sidecar executable not found: {sidecar_exe}", file=sys.stderr)
        return 1

    size_mb = sidecar_exe.stat().st_size / (1024 * 1024)
    print(f"\n✅ Sidecar built successfully: {sidecar_exe}")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"   Directory: {SIDECAR_OUTPUT_DIR}")

    # 列出 sidecar 目录内容
    sidecar_subdir = SIDECAR_OUTPUT_DIR / "pangu-nebula-sidecar"
    print(f"\n   Contents of {sidecar_subdir.name}/:")
    for item in sorted(sidecar_subdir.iterdir()):
        if item.is_file():
            sz = item.stat().st_size / (1024 * 1024)
            print(f"     {item.name} ({sz:.1f} MB)")
        else:
            print(f"     {item.name}/")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Pangu Nebula Python sidecar for Tauri 2"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean old build artifacts before building",
    )
    args = parser.parse_args()

    if args.clean:
        clean_old_build()

    return build_sidecar()


if __name__ == "__main__":
    sys.exit(main())
