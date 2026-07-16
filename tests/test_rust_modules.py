"""Rust 模块骨架与 Python mock 测试 (T5.1 + T5.2)

覆盖:
1. Rust 项目结构存在性检查
2. Cargo.toml 内容检查
3. Rust 源文件骨架存在性检查
4. BrowserUseRust mock 状态查询
5. BrowserUseRust mock cdp_connect / aria_listen / launch
6. ComputerUseRust mock 状态查询
7. ComputerUseRust mock get_a11y_tree / generate_som_overlay / ocr_recognize
8. 切换到 Rust 实现的代码路径(用 mock 模块模拟 HAS_RUST=True)
9. 真实 Rust 编译测试(skip 标记,无 Rust 编译器)
"""

from __future__ import annotations

import base64
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent


# ===== 1. Rust 项目结构存在性检查 =====


def test_rust_browser_use_structure_exists():
    """Rust browser_use 项目结构应存在"""
    base = ROOT / "rust" / "browser_use"
    assert base.exists(), f"missing {base}"
    assert (base / "Cargo.toml").exists(), "missing Cargo.toml"
    src = base / "src"
    assert src.exists(), "missing src dir"
    assert (src / "lib.rs").exists(), "missing lib.rs"
    assert (src / "cdp.rs").exists(), "missing cdp.rs"
    assert (src / "aria.rs").exists(), "missing aria.rs"


def test_rust_computer_use_structure_exists():
    """Rust computer_use 项目结构应存在"""
    base = ROOT / "rust" / "computer_use"
    assert base.exists(), f"missing {base}"
    assert (base / "Cargo.toml").exists(), "missing Cargo.toml"
    src = base / "src"
    assert src.exists(), "missing src dir"
    assert (src / "lib.rs").exists(), "missing lib.rs"
    assert (src / "a11y.rs").exists(), "missing a11y.rs"
    assert (src / "som.rs").exists(), "missing som.rs"
    assert (src / "ocr.rs").exists(), "missing ocr.rs"


# ===== 2. Cargo.toml 内容检查 =====


def test_browser_use_cargo_toml_content():
    """browser_use Cargo.toml 应包含 PyO3 依赖与 cdylib crate-type"""
    cargo = (ROOT / "rust" / "browser_use" / "Cargo.toml").read_text(encoding="utf-8")
    assert 'name = "browser_use"' in cargo
    assert "pyo3" in cargo
    assert "cdylib" in cargo


def test_computer_use_cargo_toml_content():
    """computer_use Cargo.toml 应包含 PyO3 依赖与 cdylib crate-type"""
    cargo = (ROOT / "rust" / "computer_use" / "Cargo.toml").read_text(encoding="utf-8")
    assert 'name = "computer_use"' in cargo
    assert "pyo3" in cargo
    assert "cdylib" in cargo


# ===== 3. Rust 源文件骨架检查 =====


def test_browser_use_lib_rs_skeleton_markers():
    """lib.rs 应包含 cdp_connect / aria_listen / pymodule 入口"""
    lib = (ROOT / "rust" / "browser_use" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "fn cdp_connect" in lib
    assert "fn aria_listen" in lib
    assert "#[pymodule]" in lib
    assert "fn is_skeleton" in lib  # 骨架标记函数


def test_computer_use_lib_rs_skeleton_markers():
    """computer_use lib.rs 应包含 get_a11y_tree / generate_som_overlay / ocr_recognize"""
    lib = (ROOT / "rust" / "computer_use" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "fn get_a11y_tree" in lib
    assert "fn generate_som_overlay" in lib
    assert "fn ocr_recognize" in lib
    assert "#[pymodule]" in lib
    assert "fn is_skeleton" in lib


# ===== 4. BrowserUseRust mock 测试 =====


def test_browser_use_rust_module_importable():
    """server.services.browser_use_rust 模块应可导入"""
    from server.services.browser_use_rust import BrowserUseRust, browser_use_rust

    assert browser_use_rust is not None
    assert isinstance(browser_use_rust, BrowserUseRust)


def test_browser_use_rust_status_mock_mode():
    """Mock 模式下 get_status 应返回 mock=True"""
    # 重新加载模块确保干净状态
    if "server.services.browser_use_rust" in sys.modules:
        del sys.modules["server.services.browser_use_rust"]
    from server.services.browser_use_rust import browser_use_rust, HAS_RUST
    if HAS_RUST:
        pytest.skip("Rust 模块已编译，mock 模式测试不适用")

    status = browser_use_rust.get_status()
    # 在测试环境中 Rust 模块未编译,应为 mock 模式
    assert status["rust_available"] is False
    assert status["mock"] is True
    assert status["active_sessions"] == 0
    assert status["skeleton"] is False  # 无 Rust 模块时 skeleton 为 False


async def test_browser_use_rust_cdp_connect_mock():
    """cdp_connect 在 mock 模式下应返回 mock 会话 ID"""
    if "server.services.browser_use_rust" in sys.modules:
        del sys.modules["server.services.browser_use_rust"]
    from server.services.browser_use_rust import BrowserUseRust, HAS_RUST
    if HAS_RUST:
        pytest.skip("Rust 模块已编译，mock 模式测试不适用")

    svc = BrowserUseRust()
    result = await svc.cdp_connect("ws://127.0.0.1:9222/devtools/browser/test")
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    assert result["data"]["session_id"].startswith("mock-")
    assert result["data"]["url"] == "ws://127.0.0.1:9222/devtools/browser/test"
    # 会话已记录
    assert svc.get_status()["active_sessions"] == 1

    # 关闭会话
    closed = await svc.cdp_close(result["data"]["session_id"])
    assert closed["ok"] is True
    assert svc.get_status()["active_sessions"] == 0


async def test_browser_use_rust_aria_listen_mock():
    """aria_listen 在 mock 模式下应返回示例 ARIA 元素列表"""
    from server.services.browser_use_rust import BrowserUseRust, HAS_RUST
    if HAS_RUST:
        pytest.skip("Rust 模块已编译，mock 模式测试不适用")

    svc = BrowserUseRust()
    result = await svc.aria_listen("page-001")
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    assert result["data"]["page_id"] == "page-001"
    elements = result["data"]["elements"]
    assert isinstance(elements, list)
    assert len(elements) > 0
    # 每个 element 应是字符串描述
    for el in elements:
        assert isinstance(el, str)
        assert "[" in el and "]" in el  # 形如 [button] xxx


async def test_browser_use_rust_launch_mock():
    """launch 在 mock 模式下应返回 mock ws_url"""
    from server.services.browser_use_rust import BrowserUseRust

    svc = BrowserUseRust()
    result = await svc.launch(headless=True, port=9222)
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    assert result["data"]["headless"] is True
    assert result["data"]["port"] == 9222
    assert result["data"]["ws_url"].startswith("ws://127.0.0.1:9222/")


async def test_browser_use_rust_cdp_close_unknown_session():
    """关闭未知会话应返回错误"""
    from server.services.browser_use_rust import BrowserUseRust

    svc = BrowserUseRust()
    result = await svc.cdp_close("nonexistent-session")
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


# ===== 5. ComputerUseRust mock 测试 =====


def test_computer_use_rust_module_importable():
    """server.services.computer_use_rust 模块应可导入"""
    from server.services.computer_use_rust import ComputerUseRust, computer_use_rust

    assert computer_use_rust is not None
    assert isinstance(computer_use_rust, ComputerUseRust)


def test_computer_use_rust_status_mock_mode():
    """Mock 模式下 get_status 应返回 mock=True"""
    if "server.services.computer_use_rust" in sys.modules:
        del sys.modules["server.services.computer_use_rust"]
    from server.services.computer_use_rust import computer_use_rust

    status = computer_use_rust.get_status()
    assert status["rust_available"] is False
    assert status["mock"] is True


async def test_computer_use_rust_get_a11y_tree_mock():
    """get_a11y_tree 在 mock 模式下应返回示例 a11y 树"""
    from server.services.computer_use_rust import ComputerUseRust

    svc = ComputerUseRust()
    result = await svc.get_a11y_tree()
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    tree = result["data"]["tree"]
    assert tree is not None
    assert tree["role"] == "desktop"
    assert "children" in tree
    # 应至少有一个窗口
    assert len(tree["children"]) > 0
    # 子节点应有 actionable 标记
    win = tree["children"][0]
    assert win["role"] == "window"
    assert win["actionable"] is True


async def test_computer_use_rust_generate_som_overlay_mock():
    """generate_som_overlay 在 mock 模式下应返回 marks 列表"""
    from server.services.computer_use_rust import ComputerUseRust

    svc = ComputerUseRust()
    # 先获取 a11y 树(会缓存)
    await svc.get_a11y_tree()
    # 调用 SoM 标注
    result = await svc.generate_som_overlay(
        screenshot_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
        a11y_json=None,  # 使用缓存的 a11y 树
    )
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    marks = result["data"]["marks"]
    assert isinstance(marks, list)
    # mock a11y 树中 window 节点是 actionable,所以应有至少 1 个 mark
    assert len(marks) > 0
    for mark in marks:
        assert "mark_id" in mark
        assert "node_id" in mark
        assert "label" in mark


async def test_computer_use_rust_ocr_recognize_mock():
    """ocr_recognize 在 mock 模式下应返回示例 OCR 结果"""
    from server.services.computer_use_rust import ComputerUseRust

    svc = ComputerUseRust()
    result = await svc.ocr_recognize(
        image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
        lang="chi_sim",
    )
    assert result["ok"] is True
    assert result["data"]["mock"] is True
    items = result["data"]["items"]
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "text" in item
        assert "bbox" in item
        assert "confidence" in item
        assert 0.0 <= item["confidence"] <= 1.0


# ===== 6. 切换到 Rust 实现的代码路径(模拟 HAS_RUST=True) =====


def test_browser_use_rust_rust_path_simulation():
    """模拟 HAS_RUST=True 时,应走 Rust 调用路径"""
    # 构造 mock Rust 模块
    mock_rust_module = MagicMock()
    mock_rust_module.cdp_connect.return_value = True
    mock_rust_module.aria_listen.return_value = ["[button] Click me (actionable=Y visible=Y)"]
    mock_rust_module.version.return_value = "0.1.0"
    mock_rust_module.is_skeleton.return_value = False

    # 用 sys.modules 替换 browser_use 模块
    with patch.dict(sys.modules, {"browser_use": mock_rust_module}):
        # 清除已加载的包装模块,触发重新导入
        if "server.services.browser_use_rust" in sys.modules:
            del sys.modules["server.services.browser_use_rust"]
        from server.services.browser_use_rust import BrowserUseRust

        svc = BrowserUseRust()
        status = svc.get_status()
        assert status["rust_available"] is True
        assert status["mock"] is False
        assert status["rust_version"] == "0.1.0"
        assert status["skeleton"] is False

    # 清理: 再次重新导入,确保后续测试用 mock 模式
    if "server.services.browser_use_rust" in sys.modules:
        del sys.modules["server.services.browser_use_rust"]


async def test_browser_use_rust_cdp_connect_rust_path():
    """HAS_RUST=True 时 cdp_connect 应调用 Rust 真实实现"""
    mock_rust_module = MagicMock()
    mock_rust_module.cdp_connect.return_value = True
    mock_rust_module.is_skeleton.return_value = False

    with patch.dict(sys.modules, {"browser_use": mock_rust_module}):
        if "server.services.browser_use_rust" in sys.modules:
            del sys.modules["server.services.browser_use_rust"]
        from server.services.browser_use_rust import BrowserUseRust

        svc = BrowserUseRust()
        result = await svc.cdp_connect("ws://test")
        assert result["ok"] is True
        assert result["data"]["mock"] is False
        # 应调用了 Rust 模块的 cdp_connect
        mock_rust_module.cdp_connect.assert_called_once_with("ws://test")

    if "server.services.browser_use_rust" in sys.modules:
        del sys.modules["server.services.browser_use_rust"]


def test_computer_use_rust_rust_path_simulation():
    """模拟 HAS_RUST=True 时 ComputerUseRust 应走 Rust 路径"""
    mock_rust_module = MagicMock()
    mock_rust_module.get_a11y_tree.return_value = '{"node_id":"root","role":"desktop"}'
    mock_rust_module.generate_som_overlay.return_value = "annotated_image_b64"
    mock_rust_module.ocr_recognize.return_value = '[{"text":"hello"}]'
    mock_rust_module.version.return_value = "0.1.0"
    mock_rust_module.is_skeleton.return_value = True  # Rust 模块为骨架模式

    with patch.dict(sys.modules, {"computer_use": mock_rust_module}):
        if "server.services.computer_use_rust" in sys.modules:
            del sys.modules["server.services.computer_use_rust"]
        from server.services.computer_use_rust import ComputerUseRust

        svc = ComputerUseRust()
        status = svc.get_status()
        assert status["rust_available"] is True
        assert status["mock"] is False
        assert status["skeleton"] is True  # 骨架模式

    if "server.services.computer_use_rust" in sys.modules:
        del sys.modules["server.services.computer_use_rust"]


# ===== 7. 真实 Rust 编译测试(skip 标记,无 Rust 编译器) =====


def _can_cargo_compile() -> bool:
    """检查 cargo 是否能实际编译(不只是二进制存在)

    骨架任务的编译测试在以下情况跳过:
    - cargo 未安装
    - Windows 上缺少 MSVC linker(link.exe / cl.exe)
    - 任何环境异常
    """
    import shutil

    if not shutil.which("cargo"):
        return False
    # Windows 上 cargo 需要 MSVC linker 才能编译
    if sys.platform == "win32":
        # link.exe / cl.exe 通常只在 vcvarsall.bat 加载后才在 PATH 中
        # 没有它们时 cargo check 会失败,应跳过
        if not shutil.which("link.exe") and not shutil.which("cl.exe"):
            return False
    return True


@pytest.mark.skipif(
    not _can_cargo_compile(),
    reason="cargo 未安装或缺少 MSVC linker,跳过 Rust 实际编译测试(骨架任务)",
)
def test_browser_use_rust_compiles():
    """如果有完整 Rust 工具链,尝试编译 browser_use 模块(骨架任务通常跳过)"""
    import subprocess

    cargo_dir = ROOT / "rust" / "browser_use"
    result = subprocess.run(
        ["cargo", "check"],
        cwd=str(cargo_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"cargo check failed:\n{result.stderr}"


@pytest.mark.skipif(
    not _can_cargo_compile(),
    reason="cargo 未安装或缺少 MSVC linker,跳过 Rust 实际编译测试(骨架任务)",
)
def test_computer_use_rust_compiles():
    """如果有完整 Rust 工具链,尝试编译 computer_use 模块(骨架任务通常跳过)"""
    import subprocess

    cargo_dir = ROOT / "rust" / "computer_use"
    result = subprocess.run(
        ["cargo", "check"],
        cwd=str(cargo_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"cargo check failed:\n{result.stderr}"
