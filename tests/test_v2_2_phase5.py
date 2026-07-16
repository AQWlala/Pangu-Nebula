# tests/test_v2_2_phase5.py
"""v2.2.0 Phase 5 — Browser/Computer Use 工具测试

测试覆盖:
1. browser_tools 工具注册 + 执行 (mock browser_service)
2. computer_tools 工具注册 + 依赖检查 (mock pyautogui/PIL)
3. ToolExecutor 权限拦截 (browser_use_enabled)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.tools.registry import get_tool, is_registered, list_tools_schema


# ============================================================
# 1. browser_tools 工具注册
# ============================================================

class TestBrowserToolsRegistration:
    """测试 browser_* 工具是否正确注册。"""

    def test_browser_navigate_registered(self):
        assert is_registered("browser_navigate")

    def test_browser_screenshot_registered(self):
        assert is_registered("browser_screenshot")

    def test_browser_click_registered(self):
        assert is_registered("browser_click")

    def test_browser_type_registered(self):
        assert is_registered("browser_type")

    def test_browser_tools_in_schema(self):
        """工具 schema 应包含 browser_* 工具。"""
        schema = list_tools_schema()
        names = [s["function"]["name"] for s in schema]
        assert "browser_navigate" in names
        assert "browser_screenshot" in names
        assert "browser_click" in names
        assert "browser_type" in names

    def test_browser_navigate_schema_structure(self):
        """browser_navigate schema 应有 url 参数。"""
        tool = get_tool("browser_navigate")
        assert tool is not None
        assert "url" in tool.parameters["properties"]
        assert "url" in tool.parameters["required"]


# ============================================================
# 2. browser_tools 工具执行 (mock browser_service)
# ============================================================

class TestBrowserToolsExecution:
    """测试 browser_* 工具执行逻辑 (mock browser_service)。"""

    @pytest.mark.asyncio
    async def test_browser_navigate_success(self):
        """browser_navigate 成功导航。"""
        from server.tools.browser_tools import BrowserNavigateTool

        tool = BrowserNavigateTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.navigate = AsyncMock(return_value={
                "ok": True,
                "data": {"url": "https://example.com", "title": "Example", "status": 200},
                "error": None,
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute(url="https://example.com")
            assert result.success is True
            assert "Example" in result.output
            mock_svc.navigate.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_browser_navigate_session_failure(self):
        """browser_navigate 会话启动失败。"""
        from server.tools.browser_tools import BrowserNavigateTool

        tool = BrowserNavigateTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_ensure.return_value = (None, "playwright 未安装")

            result = await tool.execute(url="https://example.com")
            assert result.success is False
            assert "playwright 未安装" in result.error

    @pytest.mark.asyncio
    async def test_browser_navigate_navigation_failure(self):
        """browser_navigate 导航失败。"""
        from server.tools.browser_tools import BrowserNavigateTool

        tool = BrowserNavigateTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.navigate = AsyncMock(return_value={
                "ok": False, "data": None, "error": "网络超时",
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute(url="https://timeout.com")
            assert result.success is False
            assert "网络超时" in result.error

    @pytest.mark.asyncio
    async def test_browser_screenshot_success(self):
        """browser_screenshot 成功截图。"""
        from server.tools.browser_tools import BrowserScreenshotTool

        tool = BrowserScreenshotTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.execute_action = AsyncMock(return_value={
                "ok": True,
                "data": {"action": "screenshot", "image_base64": "aGVsbG8="},
                "error": None,
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute()
            assert result.success is True
            assert "截图成功" in result.output

    @pytest.mark.asyncio
    async def test_browser_click_success(self):
        """browser_click 成功点击。"""
        from server.tools.browser_tools import BrowserClickTool

        tool = BrowserClickTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.execute_action = AsyncMock(return_value={
                "ok": True,
                "data": {"action": "click", "selector": "button#submit"},
                "error": None,
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute(selector="button#submit")
            assert result.success is True
            assert "button#submit" in result.output

    @pytest.mark.asyncio
    async def test_browser_type_success(self):
        """browser_type 成功输入。"""
        from server.tools.browser_tools import BrowserTypeTool

        tool = BrowserTypeTool()
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.execute_action = AsyncMock(return_value={
                "ok": True,
                "data": {"action": "type", "selector": "input", "text": "hello"},
                "error": None,
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute(selector="input", text="hello")
            assert result.success is True
            assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_browser_type_long_text_truncated(self):
        """browser_type 长文本在输出中截断。"""
        from server.tools.browser_tools import BrowserTypeTool

        tool = BrowserTypeTool()
        long_text = "x" * 100
        with patch("server.tools.browser_tools._ensure_session", new_callable=AsyncMock) as mock_ensure:
            mock_svc = AsyncMock()
            mock_svc.execute_action = AsyncMock(return_value={
                "ok": True,
                "data": {"action": "type", "selector": "input", "text": long_text},
                "error": None,
            })
            mock_ensure.return_value = (mock_svc, None)

            result = await tool.execute(selector="input", text=long_text)
            assert result.success is True
            assert "..." in result.output


# ============================================================
# 3. computer_tools 工具注册
# ============================================================

class TestComputerToolsRegistration:
    """测试 computer_* 工具是否正确注册。"""

    def test_computer_screenshot_registered(self):
        assert is_registered("computer_screenshot")

    def test_computer_click_registered(self):
        assert is_registered("computer_click")

    def test_computer_type_text_registered(self):
        assert is_registered("computer_type_text")

    def test_computer_get_a11y_tree_registered(self):
        assert is_registered("computer_get_a11y_tree")

    def test_computer_tools_in_schema(self):
        schema = list_tools_schema()
        names = [s["function"]["name"] for s in schema]
        assert "computer_screenshot" in names
        assert "computer_click" in names
        assert "computer_type_text" in names
        assert "computer_get_a11y_tree" in names


# ============================================================
# 4. computer_tools 依赖检查
# ============================================================

class TestComputerToolsDependencyCheck:
    """测试 computer_* 工具的依赖检查逻辑。"""

    @pytest.mark.asyncio
    async def test_computer_screenshot_no_deps(self):
        """computer_screenshot 无依赖时返回错误。"""
        from server.tools.computer_tools import ComputerScreenshotTool

        tool = ComputerScreenshotTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(False, "依赖未安装")):
            result = await tool.execute()
            assert result.success is False
            assert "依赖未安装" in result.error

    @pytest.mark.asyncio
    async def test_computer_click_no_deps(self):
        """computer_click 无依赖时返回错误。"""
        from server.tools.computer_tools import ComputerClickTool

        tool = ComputerClickTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(False, "依赖未安装")):
            result = await tool.execute(x=100, y=200)
            assert result.success is False
            assert "依赖未安装" in result.error

    @pytest.mark.asyncio
    async def test_computer_type_text_no_deps(self):
        """computer_type_text 无依赖时返回错误。"""
        from server.tools.computer_tools import ComputerTypeTextTool

        tool = ComputerTypeTextTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(False, "依赖未安装")):
            result = await tool.execute(text="hello")
            assert result.success is False
            assert "依赖未安装" in result.error

    @pytest.mark.asyncio
    async def test_computer_screenshot_with_mock_deps(self):
        """computer_screenshot 有依赖时(mock pyautogui)成功截图。"""
        from server.tools.computer_tools import ComputerScreenshotTool

        tool = ComputerScreenshotTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            # mock pyautogui
            mock_img = MagicMock()
            mock_img.save = MagicMock(side_effect=lambda buf, format: buf.write(b"fake_png_data"))
            with patch.dict("sys.modules", {"pyautogui": MagicMock(screenshot=MagicMock(return_value=mock_img))}):
                result = await tool.execute()
                assert result.success is True
                assert "截图成功" in result.output

    @pytest.mark.asyncio
    async def test_computer_click_with_mock_deps(self):
        """computer_click 有依赖时(mock pyautogui)成功点击。"""
        from server.tools.computer_tools import ComputerClickTool

        tool = ComputerClickTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            mock_pa = MagicMock()
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute(x=100, y=200, button="left")
                assert result.success is True
                assert "(100, 200)" in result.output
                mock_pa.click.assert_called_once_with(x=100, y=200, button="left")

    @pytest.mark.asyncio
    async def test_computer_type_text_with_mock_deps(self):
        """computer_type_text 有依赖时(mock pyautogui)成功输入。"""
        from server.tools.computer_tools import ComputerTypeTextTool

        tool = ComputerTypeTextTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            mock_pa = MagicMock()
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute(text="hello world")
                assert result.success is True
                assert "hello world" in result.output
                mock_pa.typewrite.assert_called_once_with("hello world", interval=0.0)

    @pytest.mark.asyncio
    async def test_computer_click_exception_handling(self):
        """computer_click 执行异常时返回错误。"""
        from server.tools.computer_tools import ComputerClickTool

        tool = ComputerClickTool()
        with patch("server.tools.computer_tools._check_dependencies", return_value=(True, "")):
            mock_pa = MagicMock()
            mock_pa.click = MagicMock(side_effect=Exception("坐标越界"))
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute(x=99999, y=99999)
                assert result.success is False
                assert "点击失败" in result.error
                assert "坐标越界" in result.error


# ============================================================
# 5. ToolExecutor 权限拦截
# ============================================================

class TestToolExecutorBrowserPermissions:
    """测试 ToolExecutor 对 browser/computer 工具的权限拦截。"""

    @pytest.mark.asyncio
    async def test_browser_navigate_blocked_without_permission(self):
        """browser_use_enabled=False 时 browser_navigate 被拦截。"""
        from server.services.tool_executor import tool_executor
        from server.db.orm import Persona

        persona = Persona(
            id=1, name="test",
            tools_enabled=True,
            browser_use_enabled=False,  # 禁用 browser
        )
        result = await tool_executor.execute("browser_navigate", {"url": "https://example.com"}, persona)
        assert result["success"] is False
        assert "browser_use_enabled" in result["error"] or "权限" in result["error"]

    @pytest.mark.asyncio
    async def test_computer_screenshot_blocked_without_permission(self):
        """browser_use_enabled=False 时 computer_screenshot 被拦截。"""
        from server.services.tool_executor import tool_executor
        from server.db.orm import Persona

        persona = Persona(
            id=1, name="test",
            tools_enabled=True,
            browser_use_enabled=False,
        )
        result = await tool_executor.execute("computer_screenshot", {}, persona)
        assert result["success"] is False
        assert "browser_use_enabled" in result["error"] or "权限" in result["error"]

    @pytest.mark.asyncio
    async def test_browser_navigate_allowed_with_permission(self):
        """browser_use_enabled=True 时 browser_navigate 放行(执行层可能失败,但权限通过)。"""
        from server.services.tool_executor import tool_executor
        from server.db.orm import Persona

        persona = Persona(
            id=1, name="test",
            tools_enabled=True,
            browser_use_enabled=True,  # 允许 browser
        )
        # mock browser_service 避免真实启动
        with patch("server.services.browser_service.browser_service.start_session", new_callable=AsyncMock):
            with patch("server.services.browser_service.browser_service.get_status", new_callable=AsyncMock):
                with patch("server.services.browser_service.browser_service.navigate", new_callable=AsyncMock):
                    result = await tool_executor.execute("browser_navigate", {"url": "https://example.com"}, persona)
                    # 权限通过,但可能因 playwright 未装而失败
                    # 关键: 错误不应包含 "权限" 或 "browser_use_enabled"
                    if not result["success"]:
                        assert "browser_use_enabled" not in result.get("error", "")
                        assert "权限" not in result.get("error", "")
