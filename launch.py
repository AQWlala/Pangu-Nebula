# -*- coding: utf-8 -*-
"""Pangu Nebula 桌面应用启动入口

启动后端 uvicorn 服务 + PyWebView 桌面窗口。

使用方式:
    python launch.py                    # 默认启动 (自动选择端口 + 桌面窗口)
    python launch.py --port 8080        # 指定端口
    python launch.py --host 0.0.0.0     # 指定监听地址
    python launch.py --no-window        # 仅后端模式 (无窗口,用于调试)
    python launch.py --version          # 显示版本号
"""
import argparse
import socket
import sys
import threading
import time

import uvicorn

# 版本号 (与 pyproject.toml 保持一致)
VERSION = "0.1.0"


def find_available_port(start_port=7860):
    """查找可用端口 (延迟导入避免 pywebview 未安装时影响 --version)。"""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
        port += 1
    raise RuntimeError("No available port found")


def create_window(port, server_shutdown_func):
    """创建 PyWebView 桌面窗口 (延迟导入,仅桌面模式需要)。

    pywebview 6.x 移除了 on_closed 参数,改为用 webview.start() 阻塞特性:
    窗口关闭后 start() 返回,再执行清理。
    """
    import webview  # 延迟导入: pywebview 是可选依赖,仅桌面模式需要

    url = f"http://localhost:{port}"
    webview.create_window(
        title="Pangu Nebula",
        url=url,
        width=1280,
        height=800,
        frameless=True,
    )
    webview.start()  # 阻塞直到窗口关闭
    server_shutdown_func()  # 窗口关闭后清理后端


def parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="pangu-nebula",
        description="Pangu Nebula AI Agent Platform - 桌面应用启动入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python launch.py                  默认启动\n"
            "  python launch.py --port 8080      指定端口\n"
            "  python launch.py --no-window      仅后端模式\n"
            "  python launch.py --version        显示版本\n"
        ),
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="后端服务监听端口 (默认自动选择 7860 起的可用端口)",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="后端服务监听地址 (默认 127.0.0.1,仅本机访问)",
    )
    parser.add_argument(
        "--no-window", action="store_true",
        help="仅启动后端服务,不打开桌面窗口 (用于调试或服务端部署)",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="启用 uvicorn 热重载 (仅 --no-window 模式下有效)",
    )
    parser.add_argument(
        "--version", action="version", version=f"Pangu Nebula v{VERSION}",
    )
    return parser.parse_args()


def start_server(host, port, reload=False):
    """启动 uvicorn 后端服务。

    reload 模式(开发时)用字符串导入以便热重载;
    非 reload 模式(打包后)直接传入 app 对象,避免 PyInstaller 环境下 importlib 动态导入失败。
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
    """等待后端服务就绪。"""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def main():
    """主入口: 解析参数 -> 启动后端 -> (可选)打开窗口。"""
    args = parse_args()

    # 选择端口: 优先用 --port 指定,否则自动查找
    port = args.port if args.port else find_available_port()
    print(f"Pangu Nebula v{VERSION}")
    print(f"后端地址: http://{args.host}:{port}")

    # 仅后端模式
    if args.no_window:
        print("[无窗口模式] 仅启动后端服务,按 Ctrl+C 退出")
        start_server(args.host, port, reload=args.reload)
        return

    # 桌面模式: 后端线程 + PyWebView 窗口
    server_thread = threading.Thread(
        target=start_server,
        args=(args.host, port),
        kwargs={"reload": False},
        daemon=True,
    )
    server_thread.start()

    if not wait_for_server(args.host, port):
        print("错误: 后端服务启动失败", file=sys.stderr)
        sys.exit(1)

    print(f"打开桌面窗口: http://{args.host}:{port}")
    create_window(port, lambda: None)


if __name__ == "__main__":
    main()
