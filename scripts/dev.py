# -*- coding: utf-8 -*-
"""一键启动开发环境 - Pangu Nebula (Phase 11D)

同时启动后端 (uvicorn) 和前端 (vite dev server):
1. 后端: uvicorn server.main:app --reload --port 7860
2. 前端: cd frontend && npm run dev (默认 http://localhost:5173)
3. 等待两个服务就绪
4. 打印访问地址
5. Ctrl+C 退出时同时终止两个进程

使用方式:
    python scripts/dev.py                          # 默认端口启动
    python scripts/dev.py --backend-port 9000      # 指定后端端口
    python scripts/dev.py --frontend-port 3000     # 指定前端端口
    python scripts/dev.py --no-frontend            # 仅后端
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time

# 项目根目录(脚本位于 scripts/ 下)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 默认端口配置
DEFAULT_BACKEND_PORT = 7860
DEFAULT_FRONTEND_PORT = 5173  # Vite 默认端口

# 子进程列表
_processes = []


def find_python():
    """返回 Python 可执行文件路径。"""
    return sys.executable


def find_npm():
    """返回 npm 命令(Windows 用 npm.cmd)。"""
    return "npm.cmd" if os.name == "nt" else "npm"


def is_port_open(host, port, timeout=0.5):
    """检查端口是否可连接。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def wait_for_port(host, port, name, timeout=30):
    """等待端口就绪,超时返回 False。"""
    print(f"等待 {name} 就绪 ({host}:{port}) ...")
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(host, port):
            print(f"[就绪] {name} ({host}:{port})")
            return True
        time.sleep(0.3)
    print(f"[超时] {name} 在 {timeout}s 内未就绪")
    return False


def start_backend(backend_port):
    """启动后端 uvicorn 服务。"""
    python_exe = find_python()
    cmd = [
        python_exe, "-m", "uvicorn",
        "server.main:app",
        "--reload",
        "--port", str(backend_port),
        "--host", "127.0.0.1",
    ]
    print(f"启动后端: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        # 让子进程输出直接流入当前终端
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    _processes.append(proc)
    return proc


def start_frontend(frontend_port):
    """启动前端 Vite dev server。"""
    npm_cmd = find_npm()
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    # 通过 --port 参数指定前端端口
    cmd = [npm_cmd, "run", "dev", "--", "--port", str(frontend_port)]
    print(f"启动前端: {' '.join(cmd)} (cwd={frontend_dir})")
    proc = subprocess.Popen(
        cmd,
        cwd=frontend_dir,
        stdout=sys.stdout,
        stderr=sys.stderr,
        # Windows 下需要 shell=True 才能找到 .cmd
        shell=(os.name == "nt"),
    )
    _processes.append(proc)
    return proc


def cleanup():
    """终止所有子进程。"""
    print("\n正在关闭服务...")
    for proc in _processes:
        if proc.poll() is None:  # 仍在运行
            try:
                proc.terminate()
            except OSError:
                pass
    # 等待退出,超时强制 kill
    for proc in _processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
    print("所有服务已停止")


def signal_handler(signum, frame):
    """信号处理: SIGINT/SIGTERM 时清理子进程。"""
    print(f"\n收到信号 {signum},正在退出...")
    cleanup()
    sys.exit(0)


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        prog="pangu-dev",
        description="Pangu Nebula 开发环境启动 (后端 + 前端并发)",
    )
    parser.add_argument(
        "--backend-port", type=int, default=DEFAULT_BACKEND_PORT,
        help=f"后端服务端口 (默认 {DEFAULT_BACKEND_PORT})",
    )
    parser.add_argument(
        "--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT,
        help=f"前端 Vite dev server 端口 (默认 {DEFAULT_FRONTEND_PORT})",
    )
    parser.add_argument(
        "--no-frontend", action="store_true",
        help="仅启动后端,不启动前端",
    )
    args = parser.parse_args()

    backend_port = args.backend_port
    frontend_port = args.frontend_port

    print("=" * 60)
    print("  Pangu Nebula 开发环境启动 (Phase 11D)")
    print(f"  项目根目录: {BASE_DIR}")
    print(f"  后端端口: {backend_port}")
    if not args.no_frontend:
        print(f"  前端端口: {frontend_port}")
    print("=" * 60)

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        start_backend(backend_port)
        if not args.no_frontend:
            start_frontend(frontend_port)

        # 等待服务就绪
        backend_ok = wait_for_port("127.0.0.1", backend_port, "后端", timeout=30)
        frontend_ok = False
        if not args.no_frontend:
            frontend_ok = wait_for_port("127.0.0.1", frontend_port, "前端", timeout=30)

        print("\n" + "=" * 60)
        print("  开发环境已启动")
        print("-" * 60)
        if backend_ok:
            print(f"  后端 API:  http://127.0.0.1:{backend_port}")
            print(f"  健康检查:  http://127.0.0.1:{backend_port}/health")
        else:
            print(f"  后端未就绪(请检查日志)")
        if not args.no_frontend:
            if frontend_ok:
                print(f"  前端 Dev:  http://localhost:{frontend_port}")
            else:
                print(f"  前端未就绪(请检查日志,可能使用了其他端口)")
        print("-" * 60)
        print("  按 Ctrl+C 退出(同时终止所有进程)")
        print("=" * 60)

        # 主循环: 等待任一子进程退出
        try:
            while True:
                for proc in _processes:
                    if proc.poll() is not None:
                        raise RuntimeError("子进程已退出")
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass

    except Exception as exc:
        print(f"\n启动失败: {exc}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
