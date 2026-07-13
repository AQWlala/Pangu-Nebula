# -*- coding: utf-8 -*-
"""Pangu Nebula 一键构建脚本 (v2.1.0 — Tauri 2 桌面壳 + Python 后端)

执行完整构建流程:
1. 检查 Python 版本 (3.11+)
2. 检查 Node.js 版本
3. 安装后端依赖: pip install -r requirements.txt
4. 安装前端依赖: cd frontend && npm install
5. 构建前端: cd frontend && npm run build
6. 运行测试: python -m pytest tests/ -q
7. [可选] 构建 Python sidecar: python scripts/build_sidecar.py
8. [可选] Tauri 桌面打包: cargo tauri build

使用方式:
    python scripts/build.py                    # 开发构建 (前端 + 测试，不打包)
    python scripts/build.py --skip-tests       # 跳过测试
    python scripts/build.py --skip-frontend    # 跳过前端构建
    python scripts/build.py --skip-deps        # 跳过依赖安装
    python scripts/build.py --desktop          # 完整桌面打包 (含 Tauri build)
    python scripts/build.py --docker           # Docker 镜像构建
"""

import argparse
import functools
import os
import shutil
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def step(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            print(f"\n{'=' * 60}")
            print(f">>> {name}")
            print(f"{'=' * 60}")
            start = time.time()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                elapsed = time.time() - start
                print(f"[失败] {name} (耗时 {elapsed:.1f}s): {exc}")
                raise
            elapsed = time.time() - start
            print(f"[完成] {name} (耗时 {elapsed:.1f}s)")
            return result
        return wrapper
    return decorator


def run_cmd(cmd, cwd=None, check=True, shell=False):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}"
          + (f"  (cwd={cwd})" if cwd else ""))
    try:
        result = subprocess.run(cmd, cwd=cwd, shell=shell, check=False,
                                capture_output=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"命令未找到: {cmd[0] if isinstance(cmd, list) else cmd}") from exc
    if check and result.returncode != 0:
        raise RuntimeError(
            f"命令退出码 {result.returncode}: "
            f"{' '.join(cmd) if isinstance(cmd, list) else cmd}"
        )
    return result


@step("步骤 1/7: 检查 Python 版本 (要求 3.11+)")
def check_python():
    major, minor = sys.version_info[0], sys.version_info[1]
    print(f"当前 Python 版本: {major}.{minor}.{sys.version_info[2]}")
    if (major, minor) < (3, 11):
        raise RuntimeError(f"需要 Python 3.11+, 当前为 {major}.{minor}")


@step("步骤 2/7: 检查 Node.js 版本")
def check_node():
    node_cmd = "node.exe" if os.name == "nt" else "node"
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    if not shutil.which(node_cmd):
        raise RuntimeError("未找到 Node.js, 请先安装 (https://nodejs.org/)")
    if not shutil.which(npm_cmd):
        raise RuntimeError("未找到 npm, 请先安装 Node.js (https://nodejs.org/)")


@step("步骤 3/7: 安装后端依赖 (pip install -r requirements.txt)")
def install_backend_deps():
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.isfile(req_file):
        raise RuntimeError(f"未找到 requirements.txt: {req_file}")
    run_cmd([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)


@step("步骤 4/7: 安装前端依赖 (npm install)")
def install_frontend_deps():
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    if not os.path.isdir(frontend_dir):
        raise RuntimeError(f"未找到 frontend 目录: {frontend_dir}")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    run_cmd([npm_cmd, "install"], cwd=frontend_dir, check=True)


@step("步骤 5/7: 构建前端 (npm run build)")
def build_frontend():
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    run_cmd([npm_cmd, "run", "build"], cwd=frontend_dir, check=True)
    dist_index = os.path.join(frontend_dir, "dist", "index.html")
    if not os.path.isfile(dist_index):
        raise RuntimeError(f"前端构建产物缺失: {dist_index}")
    print(f"前端构建产物: {dist_index}")


@step("步骤 6/7: 运行测试 (pytest tests/ -q)")
def run_tests():
    tests_dir = os.path.join(BASE_DIR, "tests")
    if not os.path.isdir(tests_dir):
        print(f"警告: 未找到 tests 目录, 跳过测试: {tests_dir}")
        return
    result = run_cmd(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=BASE_DIR, check=False,
    )
    if result.returncode != 0:
        print(f"警告: 部分测试未通过 (退出码 {result.returncode}), 继续构建...")


@step("步骤 7/7: 构建 Python sidecar + Tauri 桌面打包")
def build_desktop():
    # Build Python sidecar
    sidecar_script = os.path.join(BASE_DIR, "scripts", "build_sidecar.py")
    if os.path.isfile(sidecar_script):
        run_cmd([sys.executable, sidecar_script], cwd=BASE_DIR, check=True)
    else:
        print("警告: build_sidecar.py 未找到, 跳过 sidecar 构建")

    # Tauri build
    cargo = "cargo.exe" if os.name == "nt" else "cargo"
    if shutil.which(cargo):
        run_cmd([cargo, "tauri", "build"], cwd=BASE_DIR, check=True)
        print("Tauri 桌面打包完成, 产物在 src-tauri/target/release/bundle/")
    else:
        raise RuntimeError("未找到 cargo, 请先安装 Rust (https://rustup.rs)")


def main():
    parser = argparse.ArgumentParser(prog="pangu-build", description="Pangu Nebula 一键构建")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    parser.add_argument("--desktop", action="store_true", help="完整桌面打包 (含 Tauri build)")
    parser.add_argument("--docker", action="store_true", help="Docker 镜像构建 (仅后端)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Pangu Nebula 构建 (v2.1.0 — Tauri 2)")
    print(f"  项目根目录: {BASE_DIR}")
    if args.desktop:
        print("  [桌面打包模式]")
    if args.docker:
        print("  [Docker 构建模式]")
    print("=" * 60)

    build_start = time.time()
    try:
        check_python()
        check_node()
        if not args.skip_deps:
            install_backend_deps()
            install_frontend_deps()
        if not args.skip_frontend:
            build_frontend()
        if not args.skip_tests:
            run_tests()
        if args.desktop:
            build_desktop()
        elif args.docker:
            run_cmd(["docker", "compose", "build"], cwd=BASE_DIR, check=True)
            print("Docker 镜像构建完成: docker compose up -d")
    except Exception as exc:
        total_elapsed = time.time() - build_start
        print(f"\n{'!' * 60}")
        print(f"构建失败: {exc}")
        print(f"总耗时: {total_elapsed:.1f}s")
        print(f"{'!' * 60}")
        sys.exit(1)

    total_elapsed = time.time() - build_start
    print(f"\n{'*' * 60}")
    print(f"  构建成功! 总耗时: {total_elapsed:.1f}s")
    if args.desktop:
        print(f"  桌面安装包: src-tauri/target/release/bundle/")
    print(f"{'*' * 60}")


if __name__ == "__main__":
    main()