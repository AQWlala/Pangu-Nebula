import socket
import webview


def find_available_port(start_port=7860):
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
        port += 1
    raise RuntimeError("No available port found")


def create_window(port, server_shutdown_func):
    url = f"http://localhost:{port}"

    def on_closed():
        server_shutdown_func()

    window = webview.create_window(
        title="Pangu Nebula",
        url=url,
        width=1280,
        height=800,
        frameless=True,
        on_closed=on_closed
    )
    webview.start()
