"""Python 沙箱执行引擎 - 在隔离环境中安全执行技能代码"""

import asyncio
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    duration_ms: int
    timed_out: bool
    memory_exceeded: bool
    error: str | None
    peak_memory_mb: int = 0
    output: Any = None  # execute_skill 解析后的结构化输出


class PythonSandbox:
    """Python 代码沙箱,支持超时/内存监控/网络限制"""

    def __init__(self, timeout: int = 60, memory_limit_mb: int = 256, allow_network: bool = False):
        self.timeout = timeout
        self.memory_limit_mb = memory_limit_mb
        self.allow_network = allow_network

    def _build_script(self, code: str) -> str:
        """构建完整沙箱脚本: 前置限制 + 用户代码 + 后置输出收集"""
        preamble = (
            "import os, json\n"
            "INPUT = json.loads(os.environ.get('SANDBOX_INPUT', '{}'))\n"
            "OUTPUT = None\n"
        )
        if not self.allow_network:
            preamble += (
                "import socket\n"
                "socket.socket = lambda *a, **k: (_ for _ in ()).throw("
                "PermissionError('Network disabled in sandbox'))\n"
            )
        postamble = (
            "\nif OUTPUT is not None:\n"
            "    print('__SANDBOX_OUTPUT__:' + json.dumps(OUTPUT, ensure_ascii=False, default=str))\n"
        )
        return preamble + "\n" + code + "\n" + postamble

    async def execute(self, code: str, input_data: dict) -> SandboxResult:
        """执行 Python 代码并返回结果"""
        full_script = self._build_script(code)
        env = os.environ.copy()
        env["SANDBOX_INPUT"] = json.dumps(input_data, ensure_ascii=False, default=str)

        # 写入临时文件
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(full_script)
        tmp.flush()
        tmp.close()
        tmp_path = tmp.name

        start = time.monotonic()
        timed_out = False
        peak_memory_mb = 0
        memory_exceeded = False

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # 内存监控(可选,依赖 psutil)
            monitor_task = None
            try:
                import psutil

                proc = psutil.Process(process.pid)

                async def _monitor():
                    nonlocal peak_memory_mb, memory_exceeded
                    while True:
                        try:
                            rss = proc.memory_info().rss / (1024 * 1024)
                            if rss > peak_memory_mb:
                                peak_memory_mb = rss
                            if rss > self.memory_limit_mb:
                                memory_exceeded = True
                                process.kill()
                                return
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            return
                        await asyncio.sleep(0.1)

                monitor_task = asyncio.create_task(_monitor())
            except ImportError:
                pass

            # 读取输出流
            stdout_task = asyncio.create_task(process.stdout.read())
            stderr_task = asyncio.create_task(process.stderr.read())

            try:
                await asyncio.wait_for(process.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                timed_out = True
                process.kill()
                await process.wait()

            # 取消内存监控
            if monitor_task:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

            stdout_bytes = await stdout_task
            stderr_bytes = await stderr_task

            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            return_code = process.returncode if process.returncode is not None else -1

            duration_ms = int((time.monotonic() - start) * 1000)

            error = None
            if timed_out:
                error = f"Execution timed out after {self.timeout}s"
            elif memory_exceeded:
                error = f"Memory limit exceeded ({self.memory_limit_mb}MB)"
            elif return_code != 0:
                error = f"Process exited with code {return_code}"

            success = return_code == 0 and not timed_out and not memory_exceeded

            return SandboxResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
                duration_ms=duration_ms,
                timed_out=timed_out,
                memory_exceeded=memory_exceeded,
                error=error,
                peak_memory_mb=int(peak_memory_mb),
            )
        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _check_type(data: Any, type_name: str) -> tuple[bool, str]:
        """检查数据类型是否符合 schema 要求"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
            "null": type(None),
        }
        expected = type_map.get(type_name)
        if expected is None:
            return True, ""  # 未知类型,跳过检查
        # bool 是 int 的子类,需要特殊处理
        if type_name in ("number", "integer") and isinstance(data, bool):
            return False, f"Expected {type_name}, got boolean"
        if not isinstance(data, expected):
            return False, f"Expected {type_name}, got {type(data).__name__}"
        return True, ""

    @staticmethod
    async def validate_schema(data: Any, schema: dict) -> tuple[bool, str]:
        """验证数据是否符合 JSON Schema(基础实现,不引入 jsonschema 库)"""
        if not schema:
            return True, ""

        # 类型检查
        schema_type = schema.get("type")
        if schema_type:
            valid, msg = PythonSandbox._check_type(data, schema_type)
            if not valid:
                return False, msg

        # 对象类型: 检查 required 和 properties
        if schema_type == "object" and isinstance(data, dict):
            required = schema.get("required", [])
            for field_name in required:
                if field_name not in data:
                    return False, f"Missing required field: {field_name}"
            properties = schema.get("properties", {})
            for key, value in data.items():
                if key in properties:
                    valid, msg = await PythonSandbox.validate_schema(value, properties[key])
                    if not valid:
                        return False, f"Field '{key}': {msg}"

        # 数组类型: 检查 items
        if schema_type == "array" and isinstance(data, list):
            items_schema = schema.get("items")
            if items_schema:
                for i, item in enumerate(data):
                    valid, msg = await PythonSandbox.validate_schema(item, items_schema)
                    if not valid:
                        return False, f"Item[{i}]: {msg}"

        return True, ""

    def _parse_output(self, stdout: str) -> tuple[bool, Any, str]:
        """从 stdout 解析 JSON 输出,优先寻找 __SANDBOX_OUTPUT__ 标记行"""
        for line in stdout.splitlines():
            if line.startswith("__SANDBOX_OUTPUT__:"):
                json_str = line[len("__SANDBOX_OUTPUT__:"):]
                try:
                    return True, json.loads(json_str), ""
                except json.JSONDecodeError as e:
                    return False, None, f"Failed to parse output JSON: {e}"
        # 回退: 尝试解析最后一行非空内容
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        if lines:
            try:
                return True, json.loads(lines[-1]), ""
            except json.JSONDecodeError:
                pass
        return False, None, "No valid JSON output found in stdout"

    async def execute_skill(
        self,
        code: str,
        input_data: dict,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
    ) -> SandboxResult:
        """执行技能代码: 验证输入 -> 执行 -> 解析输出 -> 验证输出"""
        # 验证输入
        if input_schema:
            valid, msg = await self.validate_schema(input_data, input_schema)
            if not valid:
                return SandboxResult(
                    success=False,
                    stdout="",
                    stderr="",
                    return_code=0,
                    duration_ms=0,
                    timed_out=False,
                    memory_exceeded=False,
                    error=f"Input validation failed: {msg}",
                )

        # 执行代码
        result = await self.execute(code, input_data)
        if not result.success:
            return result

        # 解析输出
        parsed, output, parse_error = self._parse_output(result.stdout)
        if not parsed:
            if output_schema:
                # 需要结构化输出但解析失败
                return SandboxResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    return_code=result.return_code,
                    duration_ms=result.duration_ms,
                    timed_out=result.timed_out,
                    memory_exceeded=result.memory_exceeded,
                    error=parse_error,
                    peak_memory_mb=result.peak_memory_mb,
                )
            # 不需要结构化输出,返回原始结果
            return result

        # 验证输出
        if output_schema:
            valid, msg = await self.validate_schema(output, output_schema)
            if not valid:
                return SandboxResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    return_code=result.return_code,
                    duration_ms=result.duration_ms,
                    timed_out=result.timed_out,
                    memory_exceeded=result.memory_exceeded,
                    error=f"Output validation failed: {msg}",
                    peak_memory_mb=result.peak_memory_mb,
                )

        return SandboxResult(
            success=True,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.return_code,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            memory_exceeded=result.memory_exceeded,
            error=None,
            peak_memory_mb=result.peak_memory_mb,
            output=output,
        )
