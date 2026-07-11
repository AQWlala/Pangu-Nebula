# -*- coding: utf-8 -*-
"""一键构建脚本 - Pangu Nebula (Phase 11D)

执行完整的构建流程:
1. 检查 Python 版本 (3.11+)
2. 检查 Node.js 版本
3. 安装后端依赖: pip install -r requirements.txt
4. 安装前端依赖: cd frontend && npm install
5. 构建前端: cd frontend && npm run build
6. 运行测试: python -m pytest tests/ -q
7. PyInstaller 打包: pyinstaller pangu-nebula.spec --noconfirm
8. 验证输出: 检查 dist/PanguNebula/ 目录
9. 打印构建结果(大小, 耗时)

使用方式:
    python scripts/build.py                    # 完整构建
    python scripts/build.py --skip-tests       # 跳过测试
    python scripts/build.py --skip-frontend    # 跳过前端构建
    python scripts/build.py --skip-deps        # 跳过依赖安装
    python scripts/build.py --skip-pyinstaller # 跳过打包 (仅测试+前端构建)
"""

import argparse
import functools
import os
import shutil
import subprocess
import sys
import time

# 项目根目录(脚本位于 scripts/ 下)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def step(name):
    """步骤装饰器: 打印步骤标题并计时。"""

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
    """运行外部命令,实时输出,失败时抛出 RuntimeError。"""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}"
          + (f"  (cwd={cwd})" if cwd else ""))
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=shell,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"命令未找到: {cmd[0] if isinstance(cmd, list) else cmd}") from exc
    if check and result.returncode != 0:
        raise RuntimeError(
            f"命令退出码 {result.returncode}: "
            f"{' '.join(cmd) if isinstance(cmd, list) else cmd}"
        )
    return result


@step("步骤 1/8: 检查 Python 版本 (要求 3.11+)")
def check_python():
    major, minor = sys.version_info[0], sys.version_info[1]
    print(f"当前 Python 版本: {major}.{minor}.{sys.version_info[2]}")
    if (major, minor) < (3, 11):
        raise RuntimeError(f"需要 Python 3.11+,当前为 {major}.{minor}")
    print("Python 版本符合要求")


@step("步骤 2/8: 检查 Node.js 版本")
def check_node():
    node_cmd = "node.exe" if os.name == "nt" else "node"
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    if not shutil.which(node_cmd):
        raise RuntimeError("未找到 Node.js,请先安装 Node.js (https://nodejs.org/)")
    if not shutil.which(npm_cmd):
        raise RuntimeError("未找到 npm,请先安装 Node.js (https://nodejs.org/)")
    result = run_cmd([node_cmd, "--version"], check=True)
    version = result.stdout.strip() if result.stdout else "(未知)"
    print(f"Node.js 版本: {version}")


@step("步骤 3/8: 安装后端依赖 (pip install -r requirements.txt)")
def install_backend_deps():
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.isfile(req_file):
        raise RuntimeError(f"未找到 requirements.txt: {req_file}")
    python_exe = sys.executable
    run_cmd([python_exe, "-m", "pip", "install", "-r", req_file], check=True)


@step("步骤 4/8: 安装前端依赖 (npm install)")
def install_frontend_deps():
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    if not os.path.isdir(frontend_dir):
        raise RuntimeError(f"未找到 frontend 目录: {frontend_dir}")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    run_cmd([npm_cmd, "install"], cwd=frontend_dir, check=True)


@step("步骤 5/8: 构建前端 (npm run build)")
def build_frontend():
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    run_cmd([npm_cmd, "run", "build"], cwd=frontend_dir, check=True)
    dist_index = os.path.join(frontend_dir, "dist", "index.html")
    if not os.path.isfile(dist_index):
        raise RuntimeError(f"前端构建产物缺失: {dist_index}")
    print(f"前端构建产物: {dist_index}")


@step("步骤 6/8: 运行测试 (pytest tests/ -q)")
def run_tests():
    tests_dir = os.path.join(BASE_DIR, "tests")
    if not os.path.isdir(tests_dir):
        print(f"警告: 未找到 tests 目录,跳过测试: {tests_dir}")
        return
    python_exe = sys.executable
    # 测试失败不阻断构建(允许部分测试失败),但打印结果
    result = run_cmd(
        [python_exe, "-m", "pytest", "tests/", "-q"],
        cwd=BASE_DIR,
        check=False,
    )
    if result.returncode != 0:
        print(f"警告: 部分测试未通过 (退出码 {result.returncode}),继续构建...")
    else:
        print("所有测试通过")


@step("步骤 7/8: PyInstaller 打包 (pyinstaller pangu-nebula.spec --noconfirm)")
def run_pyinstaller():
    spec_file = os.path.join(BASE_DIR, "pangu-nebula.spec")
    if not os.path.isfile(spec_file):
        raise RuntimeError(f"未找到 spec 文件: {spec_file}")
    python_exe = sys.executable
    # 确保 pyinstaller 已安装
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller 未安装,正在安装...")
        run_cmd([python_exe, "-m", "pip", "install", "pyinstaller>=6.0"], check=True)
    run_cmd(
        [python_exe, "-m", "PyInstaller", spec_file, "--noconfirm"],
        cwd=BASE_DIR,
        check=True,
    )


@step("步骤 8/8: 验证输出 (dist/PanguNebula/)")
def verify_output():
    dist_dir = os.path.join(BASE_DIR, "dist", "PanguNebula")
    if not os.path.isdir(dist_dir):
        raise RuntimeError(f"打包输出目录不存在: {dist_dir}")
    exe_name = "PanguNebula.exe" if os.name == "nt" else "PanguNebula"
    exe_path = os.path.join(dist_dir, exe_name)
    if not os.path.isfile(exe_path):
        raise RuntimeError(f"未找到可执行文件: {exe_path}")
    # 计算输出目录大小
    total_size = 0
    file_count = 0
    for root, _dirs, files in os.walk(dist_dir):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
                file_count += 1
            except OSError:
                pass
    size_mb = total_size / (1024 * 1024)
    print(f"输出目录: {dist_dir}")
    print(f"可执行文件: {exe_path}")
    print(f"文件数量: {file_count}")
    print(f"总大小: {size_mb:.2f} MB")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        prog="pangu-build",
        description="Pangu Nebula 一键构建 (前端 + 测试 + PyInstaller 打包)",
    )
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试步骤")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="跳过 PyInstaller 打包")
    args = parser.parse_args()

    print("=" * 60)
    print("  Pangu Nebula 一键构建 (Phase 11D)")
    print(f"  项目根目录: {BASE_DIR}")
    if args.skip_tests:
        print("  [跳过测试]")
    if args.skip_frontend:
        print("  [跳过前端构建]")
    if args.skip_deps:
        print("  [跳过依赖安装]")
    if args.skip_pyinstaller:
        print("  [跳过 PyInstaller 打包]")
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
        if not args.skip_pyinstaller:
            run_pyinstaller()
            verify_output()
    except Exception as exc:
        total_elapsed = time.time() - build_start
        print("\n" + "!" * 60)
        print(f"构建失败: {exc}")
        print(f"总耗时: {total_elapsed:.1f}s")
        print("!" * 60)
        sys.exit(1)

    total_elapsed = time.time() - build_start
    print("\n" + "*" * 60)
    print(f"  构建成功! 总耗时: {total_elapsed:.1f}s")
    if not args.skip_pyinstaller:
        dist_dir = os.path.join(BASE_DIR, "dist", "PanguNebula")
        print(f"  输出目录: {dist_dir}")
    print("*" * 60)


if __name__ == "__main__":
    main()
