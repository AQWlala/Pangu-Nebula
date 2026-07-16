"""Rust Browser Use 模块的 Python mock 实现

Pangu Nebula v2.0.0 阶段5(T5.1):
Rust 端的 browser_use 模块尚未编译,此处提供 Python mock 作为功能占位。
当 Rust 模块编译完成并安装为 PyO3 扩展后,会自动切换到调用 Rust 实现。

切换机制:
- 检测到 `browser_use` PyO3 模块时,标记 HAS_RUST=True
- cdp_connect / aria_listen: 调用时若 HAS_RUST,走真实 Rust 调用路径;
  否则返回 mock 数据,字段结构与未来 Rust 返回值保持一致
- get_status: 仅查询并汇报 HAS_RUST 状态(无 Rust/mock 数据分支),
  返回 rust_available/rust_version/skeleton/active_sessions/mock 字段
- cdp_close: 纯 Python 会话管理(从内存字典删除会话),不检查 HAS_RUST,
  无 Rust 对应实现
- launch: 检查 HAS_RUST,但 launch_chromium 尚未通过 PyO3 暴露,
  因此当前始终返回 mock ws_url(待 Rust 端补齐后启用真实调用)

模块映射:
- Rust: rust/browser_use/src/lib.rs::cdp_connect
- Mock: BrowserUseRust.cdp_connect
- Rust: rust/browser_use/src/lib.rs::aria_listen
- Mock: BrowserUseRust.aria_listen
- (无 Rust 对应): BrowserUseRust.cdp_close — Python 会话管理
- (待 PyO3 暴露): BrowserUseRust.launch — 启动 Chromium
- (无 Rust 对应): BrowserUseRust.get_status — Python 状态查询
"""

from __future__ import annotations

from typing import Any

# 尝试导入 Rust 编译产物(PyO3 扩展模块)
# 编译完成后,模块名 `browser_use` 对应 rust/browser_use/Cargo.toml 中的 lib.name
try:
    import browser_use as _browser_use_rust  # type: ignore

    HAS_RUST = True
    RUST_VERSION: str | None = getattr(_browser_use_rust, "version", lambda: None)()
except ImportError:
    _browser_use_rust = None  # type: ignore
    HAS_RUST = False
    RUST_VERSION = None


class BrowserUseRust:
    """Browser Use Rust 模块的 Python 包装/mock

    提供与未来 Rust 实现一致的接口:
    - cdp_connect(url): 连接到 CDP websocket
    - cdp_close(session_id): 关闭 CDP 会话(纯 Python 会话管理,无 Rust 对应)
    - aria_listen(page_id): 监听 ARIA 树
    - launch(headless, port): 启动 Chromium(launch_chromium 尚未通过 PyO3 暴露,
      当前返回 mock ws_url)
    - get_status(): 获取模块状态(纯 Python 状态查询,无 Rust 对应)

    所有方法均返回 {"ok": bool, "data": ..., "error": ...} 统一格式,
    与 server/services/browser_service.py 风格保持一致。
    """

    def __init__(self) -> None:
        # 当前活跃的 CDP 会话(mock 模式下为内存字典)
        self._sessions: dict[str, dict[str, Any]] = {}

    # ===== 状态查询 =====

    def get_status(self) -> dict:
        """获取模块状态

        返回:
        - rust_available: Rust 模块是否已编译并加载
        - rust_version: Rust 模块版本(未加载时为 None)
        - skeleton: Rust 模块是否处于骨架模式
        - active_sessions: 当前活跃会话数
        """
        skeleton = False
        if HAS_RUST:
            # Rust 模块提供了 is_skeleton 函数,用于标记是否为骨架
            sk_fn = getattr(_browser_use_rust, "is_skeleton", None)
            if callable(sk_fn):
                skeleton = bool(sk_fn())
        return {
            "rust_available": HAS_RUST,
            "rust_version": RUST_VERSION,
            "skeleton": skeleton,
            "active_sessions": len(self._sessions),
            "mock": not HAS_RUST,
        }

    # ===== CDP 会话管理 =====

    async def cdp_connect(self, url: str) -> dict:
        """连接到 Chromium DevTools Protocol

        参数:
        - url: CDP websocket URL,例如 ws://127.0.0.1:9222/devtools/browser/...

        返回 data 字段:
        - session_id: 会话标识(成功时)
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            try:
                ok = bool(_browser_use_rust.cdp_connect(url))
                if not ok:
                    return {
                        "ok": False,
                        "data": None,
                        "error": "Rust cdp_connect returned False",
                    }
                # Rust 端连接成功,记录会话
                session_id = f"rust-{abs(hash(url)) % 10**10}"
                self._sessions[session_id] = {"url": url, "mock": False}
                return {
                    "ok": True,
                    "data": {"session_id": session_id, "mock": False, "url": url},
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"Rust 调用失败: {e}"}

        # Mock 模式: 不真正连接,但记录会话
        session_id = f"mock-{abs(hash(url)) % 10**10}"
        self._sessions[session_id] = {"url": url, "mock": True}
        return {
            "ok": True,
            "data": {
                "session_id": session_id,
                "mock": True,
                "url": url,
                "note": "Rust browser_use 模块未编译,使用 mock 占位",
            },
            "error": None,
        }

    async def cdp_close(self, session_id: str) -> dict:
        """关闭 CDP 会话"""
        if session_id not in self._sessions:
            return {
                "ok": False,
                "data": None,
                "error": f"session not found: {session_id}",
            }
        del self._sessions[session_id]
        return {"ok": True, "data": {"closed": True, "session_id": session_id}, "error": None}

    # ===== ARIA 监听 =====

    async def aria_listen(self, page_id: str) -> dict:
        """监听页面的 ARIA 可访问性树

        参数:
        - page_id: 目标页面 ID(由 cdp_connect 返回)

        返回 data 字段:
        - elements: ARIA 元素描述列表
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            try:
                elements = list(_browser_use_rust.aria_listen(page_id))
                return {
                    "ok": True,
                    "data": {
                        "elements": elements,
                        "mock": False,
                        "page_id": page_id,
                    },
                    "error": None,
                }
            except Exception as e:
                return {"ok": False, "data": None, "error": f"Rust 调用失败: {e}"}

        # Mock 模式: 返回一个示例 ARIA 元素列表,体现未来返回结构
        mock_elements = [
            "[button] Submit (actionable=Y visible=Y)",
            "[textbox] Email (actionable=Y visible=Y)",
            "[link] Forgot password? (actionable=Y visible=Y)",
        ]
        return {
            "ok": True,
            "data": {
                "elements": mock_elements,
                "mock": True,
                "page_id": page_id,
                "note": "Rust browser_use 模块未编译,返回 mock ARIA 数据",
            },
            "error": None,
        }

    # ===== Chromium 启动 =====

    async def launch(self, headless: bool = True, port: int = 9222) -> dict:
        """启动 Chromium 子进程并返回 CDP websocket URL

        注意: 即使 HAS_RUST=True,launch_chromium 尚未通过 PyO3 暴露,
        因此当前始终返回 mock ws_url。待 Rust 端补齐 launch_chromium 的
        PyO3 绑定后,才会走真实 Rust 调用路径。

        参数:
        - headless: 是否无头模式
        - port: 远程调试端口

        返回 data 字段:
        - ws_url: CDP websocket URL
        - mock: 是否为 mock 模式
        """
        if HAS_RUST:
            # Rust 实现的 launch_chromium 暂未通过 PyO3 暴露
            # 此处仅当 Rust 模块标记 is_skeleton=False 时才认为可用
            sk_fn = getattr(_browser_use_rust, "is_skeleton", None)
            if callable(sk_fn) and not sk_fn():
                # 实际调用(待 PyO3 暴露 launch_chromium 后启用)
                # ws_url = _browser_use_rust.launch_chromium(headless, port)
                pass

        # Mock 模式: 返回一个虚拟的 ws_url
        ws_url = f"ws://127.0.0.1:{port}/devtools/browser/mock-{abs(hash((headless, port))) % 10**8}"
        return {
            "ok": True,
            "data": {
                "ws_url": ws_url,
                "mock": True,
                "headless": headless,
                "port": port,
                "note": "Rust browser_use 模块未编译,返回 mock ws_url",
            },
            "error": None,
        }


# 模块级单例
browser_use_rust = BrowserUseRust()
