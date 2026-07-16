# tests/test_p3_cjk_and_docs.py
"""v2.2.1 P3 修复测试

P3-3: computer_type_text CJK 输入支持 (pyperclip 剪贴板粘贴)
P3-4: computer_use_rust / browser_use_rust docstring 与实现一致性
"""
import inspect
import sys
from unittest.mock import MagicMock, patch

from server.tools.computer_tools import ComputerTypeTextTool


# ============================================================
# P3-3: CJK 输入支持
# ============================================================

class TestComputerTypeTextCJK:
    """computer_type_text 的 CJK 输入分支测试。"""

    async def test_type_text_ascii_uses_typewrite(self):
        """ASCII 文本走 typewrite 路径,不调用剪贴板。"""
        tool = ComputerTypeTextTool()
        mock_pa = MagicMock()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            with patch.dict(sys.modules, {"pyautogui": mock_pa}):
                result = await tool.execute(text="hello world")

        assert result.success is True
        assert "hello world" in result.output
        mock_pa.typewrite.assert_called_once_with("hello world", interval=0.0)
        mock_pa.hotkey.assert_not_called()

    async def test_type_text_cjk_uses_clipboard(self):
        """CJK 文本走剪贴板粘贴路径。"""
        tool = ComputerTypeTextTool()
        mock_pa = MagicMock()
        mock_clip = MagicMock()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            with patch.dict(sys.modules, {"pyautogui": mock_pa, "pyperclip": mock_clip}):
                result = await tool.execute(text="你好世界")

        assert result.success is True
        assert "CJK" in result.output
        mock_clip.copy.assert_called_once_with("你好世界")
        # Windows 平台用 ctrl+v
        mock_pa.hotkey.assert_called_once_with("ctrl", "v")
        mock_pa.typewrite.assert_not_called()

    async def test_type_text_cjk_without_pyperclip(self):
        """无 pyperclip 时返回明确错误,不崩溃。"""
        tool = ComputerTypeTextTool()
        mock_pa = MagicMock()
        # sys.modules["pyperclip"] = None 会让 `import pyperclip` 抛 ImportError
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            with patch.dict(sys.modules, {"pyautogui": mock_pa, "pyperclip": None}):
                result = await tool.execute(text="你好")

        assert result.success is False
        assert "pyperclip" in result.error
        mock_pa.hotkey.assert_not_called()
        mock_pa.typewrite.assert_not_called()

    async def test_type_text_mixed(self):
        """中英混合文本走剪贴板路径。"""
        tool = ComputerTypeTextTool()
        mock_pa = MagicMock()
        mock_clip = MagicMock()
        mixed = "你好 hello 世界"
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            with patch.dict(sys.modules, {"pyautogui": mock_pa, "pyperclip": mock_clip}):
                result = await tool.execute(text=mixed)

        assert result.success is True
        assert "CJK" in result.output
        mock_clip.copy.assert_called_once_with(mixed)
        mock_pa.hotkey.assert_called_once_with("ctrl", "v")
        mock_pa.typewrite.assert_not_called()

    async def test_type_text_empty(self):
        """空文本不报错,走 typewrite 路径(no-op)。"""
        tool = ComputerTypeTextTool()
        mock_pa = MagicMock()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            with patch.dict(sys.modules, {"pyautogui": mock_pa}):
                result = await tool.execute(text="")

        assert result.success is True
        mock_pa.typewrite.assert_called_once_with("", interval=0.0)
        mock_pa.hotkey.assert_not_called()


# ============================================================
# P3-4: docstring 与实现一致性
# ============================================================

class TestDocstringAccuracy:
    """Rust mock 模块 docstring 与实现一致性检查。"""

    def test_computer_use_rust_docstring_accurate(self):
        """computer_use_rust docstring 中 HAS_RUST 描述与代码一致。"""
        from server.services import computer_use_rust as cur_module
        from server.services.computer_use_rust import ComputerUseRust

        doc = cur_module.__doc__ or ""
        # docstring 应提及 get_status 为 Python 状态查询(无 Rust 对应)
        assert "get_status" in doc, "docstring 应提及 get_status"
        assert "状态查询" in doc or "Python 状态" in doc, (
            "docstring 应说明 get_status 是 Python 状态查询"
        )
        # 验证 get_status 方法确实存在
        assert hasattr(ComputerUseRust, "get_status")
        # get_status 仅返回状态字段,不返回 mock 数据分支(tree/items 等)
        inst = ComputerUseRust()
        status = inst.get_status()
        assert "rust_available" in status
        assert "mock" in status
        # docstring 不应声称"所有方法"都走 Rust/mock 数据分支
        # (get_status 是例外:仅查询状态)
        assert "所有方法" not in doc or "get_status" in doc

    def test_browser_use_rust_docstring_accurate(self):
        """browser_use_rust docstring 中 HAS_RUST 描述与代码一致。"""
        from server.services import browser_use_rust as bur_module
        from server.services.browser_use_rust import BrowserUseRust

        doc = bur_module.__doc__ or ""
        # docstring 应提及 cdp_close(实现中存在但原 docstring 遗漏)
        assert "cdp_close" in doc, "docstring 应提及 cdp_close"
        assert hasattr(BrowserUseRust, "cdp_close"), "cdp_close 方法应存在"
        # docstring 应说明 launch 即使 HAS_RUST 也返回 mock
        assert "launch" in doc
        assert "mock" in doc.lower() or "PyO3" in doc, (
            "docstring 应说明 launch 当前返回 mock"
        )
        # 验证 cdp_close 实现不检查 HAS_RUST(纯 Python 会话管理)
        cdp_close_src = inspect.getsource(BrowserUseRust.cdp_close)
        assert "HAS_RUST" not in cdp_close_src, (
            "cdp_close 实现不检查 HAS_RUST,docstring 应反映这一点"
        )
        # 验证 launch 方法 docstring 提及 launch_chromium 未通过 PyO3 暴露
        launch_doc = BrowserUseRust.launch.__doc__ or ""
        assert "launch_chromium" in launch_doc or "PyO3" in launch_doc, (
            "launch 方法 docstring 应说明 launch_chromium 尚未通过 PyO3 暴露"
        )
