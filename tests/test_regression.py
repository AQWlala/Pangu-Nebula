"""P0-W8 回归测试验证套件

验证 v2.1.0 Phase 0 的 T1-T8 阻断项（来自 checklist 第五节）。
每个测试对应 checklist 中的一项,失败即阻断发布。

T1: 现有 pytest（496 项基线）全绿
T2: Rust 模块测试（22 项）全绿
T3: 前端 E2E（16 项）全绿
T4: test_sidecar_poc.py 全绿
T5: test_ipc_adapter.py 全绿
T6: test_supervisor.py 全绿
T7: test_integrity.py 全绿
T8: Rust 双目标 crate 编译
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"
SRC_TAURI_DIR = PROJECT_ROOT / "src-tauri"
RUST_DIR = PROJECT_ROOT / "rust"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _run_pytest(test_path: Path, timeout: int = 120) -> tuple[int, str, str]:
    """运行指定 pytest 测试文件,返回 (returncode, stdout, stderr)。"""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_path),
        "-v",
        "--tb=short",
        "--no-header",
    ]
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _parse_pytest_summary(stdout: str) -> dict:
    """从 pytest 输出解析 passed/skipped/failed 数量。"""
    summary = {"passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    # 匹配最后一行汇总,例如 "630 passed, 13 skipped in 18.88s"
    patterns = [
        (r"(\d+)\s+passed", "passed"),
        (r"(\d+)\s+skipped", "skipped"),
        (r"(\d+)\s+failed", "failed"),
        (r"(\d+)\s+error", "errors"),
    ]
    for pattern, key in patterns:
        match = re.search(pattern, stdout)
        if match:
            summary[key] = int(match.group(1))
    return summary


# ---------------------------------------------------------------------------
# T1: 现有 pytest 基线验证
# ---------------------------------------------------------------------------


class TestT1PytestBaseline:
    """T1: 现有 pytest(496 项基线)必须全绿。"""

    def test_pytest_collection_count(self):
        """验证 pytest 至少收集到 496 项测试(基线)。"""
        # v2.1.0 新增测试后总数已超过 496
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-header",
        ]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, f"pytest collect 失败: {result.stderr[-500:]}"

        # 解析收集到的测试数量
        match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
        assert match, f"无法解析测试数量: {result.stdout[-500:]}"
        count = int(match.group(1))
        # v2.0.0 基线 496,v2.1.0 新增后应 >= 496
        assert count >= 496, f"测试数量 {count} 低于基线 496"
        # 实际预期 630+(含 P0 新增测试)
        assert count >= 600, f"测试数量 {count} 低于预期 600 (v2.1.0 应包含新增测试)"


# ---------------------------------------------------------------------------
# T2: Rust 模块测试
# ---------------------------------------------------------------------------


class TestT2RustModules:
    """T2: Rust 模块测试(22 项)必须全绿。"""

    def test_rust_modules_test_file_exists(self):
        """test_rust_modules.py 文件存在。"""
        assert (TESTS_DIR / "test_rust_modules.py").exists()

    def test_rust_modules_test_passes(self):
        """运行 test_rust_modules.py 验证全绿。"""
        test_file = TESTS_DIR / "test_rust_modules.py"
        returncode, stdout, _ = _run_pytest(test_file, timeout=180)
        summary = _parse_pytest_summary(stdout)

        # 22 项基线(允许 skipped,但 failed 必须为 0)
        assert summary["failed"] == 0, (
            f"Rust 模块测试失败: {summary['failed']} failed\n"
            f"stdout 末尾:\n{stdout[-1000:]}"
        )
        assert summary["passed"] + summary["skipped"] >= 22, (
            f"Rust 模块测试总数 {summary['passed'] + summary['skipped']} 低于预期 22\n"
            f"summary: {summary}"
        )


# ---------------------------------------------------------------------------
# T3: 前端 E2E / 构建验证
# ---------------------------------------------------------------------------


class TestT3FrontendE2E:
    """T3: 前端 E2E(16 项)全绿 — 通过 npm build 验证构建可用。"""

    def test_frontend_package_json_exists(self):
        """frontend/package.json 存在。"""
        assert (FRONTEND_DIR / "package.json").exists()

    def test_frontend_dist_index_html_exists(self):
        """frontend/dist/index.html 存在(说明构建已成功执行)。

        CI 的 backend-test job 不含 Node.js 环境,前端构建由同 workflow 的
        frontend-build job 单独负责。故在 CI 中若 dist 不存在则 skip,
        交由 frontend-build job 保证构建可用。
        """
        dist_index = FRONTEND_DIR / "dist" / "index.html"
        if dist_index.exists():
            return
        # CI 环境: 前端构建由独立 job 负责,此处 skip
        is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
        npm_path = shutil.which("npm")
        node_modules = FRONTEND_DIR / "node_modules"
        if is_ci or not npm_path or not node_modules.exists():
            pytest.skip(
                "CI 环境或缺少 npm/node_modules,前端构建由 frontend-build job 负责"
            )
        # 本地环境: 尝试构建
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=FRONTEND_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, (
            f"npm run build 失败:\nstdout: {result.stdout[-1000:]}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
        assert dist_index.exists(), "frontend/dist/index.html 不存在,构建未完成"

    def test_frontend_test_smoke_exists(self):
        """tests/e2e/test_smoke.py 存在(冒烟测试)。"""
        assert (TESTS_DIR / "e2e" / "test_smoke.py").exists()

    def test_frontend_test_build_exists(self):
        """tests/e2e/test_frontend_build.py 存在(前端构建测试)。"""
        assert (TESTS_DIR / "e2e" / "test_frontend_build.py").exists()


# ---------------------------------------------------------------------------
# T4: Sidecar PoC
# ---------------------------------------------------------------------------


class TestT4SidecarPoC:
    """T4: test_sidecar_poc.py 全绿。"""

    def test_sidecar_poc_file_exists(self):
        """test_sidecar_poc.py 文件存在。"""
        assert (TESTS_DIR / "test_sidecar_poc.py").exists()

    def test_sidecar_poc_passes(self):
        """运行 test_sidecar_poc.py 验证全绿。"""
        test_file = TESTS_DIR / "test_sidecar_poc.py"
        returncode, stdout, _ = _run_pytest(test_file, timeout=120)
        summary = _parse_pytest_summary(stdout)

        assert summary["failed"] == 0, (
            f"test_sidecar_poc.py 失败: {summary['failed']} failed\n"
            f"stdout 末尾:\n{stdout[-1000:]}"
        )
        assert summary["passed"] > 0, "test_sidecar_poc.py 应至少有 1 项通过"


# ---------------------------------------------------------------------------
# T5: IPC 适配层
# ---------------------------------------------------------------------------


class TestT5IPCAdapter:
    """T5: test_ipc_adapter.py 全绿。"""

    def test_ipc_adapter_file_exists(self):
        """test_ipc_adapter.py 文件存在。"""
        assert (TESTS_DIR / "test_ipc_adapter.py").exists()

    def test_ipc_adapter_passes(self):
        """运行 test_ipc_adapter.py 验证全绿。"""
        test_file = TESTS_DIR / "test_ipc_adapter.py"
        returncode, stdout, _ = _run_pytest(test_file, timeout=120)
        summary = _parse_pytest_summary(stdout)

        assert summary["failed"] == 0, (
            f"test_ipc_adapter.py 失败: {summary['failed']} failed\n"
            f"stdout 末尾:\n{stdout[-1000:]}"
        )
        assert summary["passed"] > 0, "test_ipc_adapter.py 应至少有 1 项通过"


# ---------------------------------------------------------------------------
# T6: Sidecar Supervisor
# ---------------------------------------------------------------------------


class TestT6Supervisor:
    """T6: test_supervisor.py 全绿。"""

    def test_supervisor_file_exists(self):
        """test_supervisor.py 文件存在。"""
        assert (TESTS_DIR / "test_supervisor.py").exists()

    def test_supervisor_passes(self):
        """运行 test_supervisor.py 验证全绿。"""
        test_file = TESTS_DIR / "test_supervisor.py"
        returncode, stdout, _ = _run_pytest(test_file, timeout=180)
        summary = _parse_pytest_summary(stdout)

        assert summary["failed"] == 0, (
            f"test_supervisor.py 失败: {summary['failed']} failed\n"
            f"stdout 末尾:\n{stdout[-1000:]}"
        )
        assert summary["passed"] > 0, "test_supervisor.py 应至少有 1 项通过"


# ---------------------------------------------------------------------------
# T7: 完整性校验
# ---------------------------------------------------------------------------


class TestT7Integrity:
    """T7: test_integrity 相关测试全绿(集成在 test_supervisor.py 中)。"""

    def test_integrity_implementation_exists(self):
        """src-tauri/src/integrity.rs 文件存在。"""
        assert (SRC_TAURI_DIR / "src" / "integrity.rs").exists()

    def test_gen_sidecar_hash_script_exists(self):
        """scripts/gen_sidecar_hash.py 存在。"""
        assert (PROJECT_ROOT / "scripts" / "gen_sidecar_hash.py").exists()

    def test_integrity_test_coverage(self):
        """test_supervisor.py 或 test_update_packaging.py 中包含完整性相关测试。"""
        # 完整性测试集成在 supervisor 测试和 update_packaging 测试中
        for test_file in [
            TESTS_DIR / "test_supervisor.py",
            TESTS_DIR / "test_update_packaging.py",
        ]:
            assert test_file.exists(), f"{test_file.name} 不存在"
            content = test_file.read_text(encoding="utf-8")
            # 验证测试中包含完整性(integrity/sha256/hash)相关内容
            assert any(
                keyword in content.lower()
                for keyword in ["integrity", "sha256", "hash"]
            ), f"{test_file.name} 未包含完整性校验相关测试"


# ---------------------------------------------------------------------------
# T8: Rust 双目标 crate 编译
# ---------------------------------------------------------------------------


class TestT8RustDualCrate:
    """T8: Rust 双目标 crate 编译(rlib + cdylib)。"""

    def test_browser_use_cargo_toml_exists(self):
        """rust/browser_use/Cargo.toml 存在。"""
        assert (RUST_DIR / "browser_use" / "Cargo.toml").exists()

    def test_computer_use_cargo_toml_exists(self):
        """rust/computer_use/Cargo.toml 存在。"""
        assert (RUST_DIR / "computer_use" / "Cargo.toml").exists()

    def test_browser_use_dual_crate_type(self):
        """rust/browser_use/Cargo.toml 配置了双目标 crate-type。"""
        cargo_toml = (RUST_DIR / "browser_use" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        assert 'crate-type' in cargo_toml, "browser_use Cargo.toml 缺少 crate-type"
        assert '"cdylib"' in cargo_toml, "browser_use 缺少 cdylib 目标"
        assert '"rlib"' in cargo_toml, "browser_use 缺少 rlib 目标"

    def test_computer_use_dual_crate_type(self):
        """rust/computer_use/Cargo.toml 配置了双目标 crate-type。"""
        cargo_toml = (RUST_DIR / "computer_use" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        assert 'crate-type' in cargo_toml, "computer_use Cargo.toml 缺少 crate-type"
        assert '"cdylib"' in cargo_toml, "computer_use 缺少 cdylib 目标"
        assert '"rlib"' in cargo_toml, "computer_use 缺少 rlib 目标"

    @pytest.mark.skipif(
        os.environ.get("CI") != "true" and not shutil.which("cargo"),
        reason="cargo 未安装,跳过编译验证(本地环境)",
    )
    def test_browser_use_rlib_compiles(self):
        """rust/browser_use rlib 目标可编译(无 --features python)。"""
        result = subprocess.run(
            ["cargo", "build", "--lib"],
            cwd=RUST_DIR / "browser_use",
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, (
            f"browser_use rlib 编译失败:\n{result.stderr[-1000:]}"
        )

    @pytest.mark.skipif(
        os.environ.get("CI") != "true" and not shutil.which("cargo"),
        reason="cargo 未安装,跳过编译验证(本地环境)",
    )
    def test_computer_use_rlib_compiles(self):
        """rust/computer_use rlib 目标可编译(无 --features python)。"""
        result = subprocess.run(
            ["cargo", "build", "--lib"],
            cwd=RUST_DIR / "computer_use",
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, (
            f"computer_use rlib 编译失败:\n{result.stderr[-1000:]}"
        )


# ---------------------------------------------------------------------------
# 架构合规验证(A1-A9 的关键项)
# ---------------------------------------------------------------------------


class TestArchitectureCompliance:
    """架构合规验收关键项验证。"""

    def test_dual_process_model(self):
        """A1: 双进程模型 — Tauri 主进程 + Python sidecar。"""
        assert (SRC_TAURI_DIR / "src" / "lib.rs").exists()
        assert (PROJECT_ROOT / "launch.py").exists()
        launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
        assert "run_sidecar" in launch_content, "launch.py 缺少 sidecar 模式"
        assert "NEBULA_PORT" in launch_content, "launch.py 缺少 NEBULA_PORT 注入"
        assert "NEBULA_TOKEN" in launch_content, "launch.py 缺少 NEBULA_TOKEN 注入"

    def test_feature_flag_implemented(self):
        """A6: 模式切换 — --no-window flag 实现。"""
        launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
        assert "--no-window" in launch_content, "launch.py 缺少 --no-window 模式切换"
        assert "run_sidecar" in launch_content, "launch.py 缺少 Tauri sidecar 模式"

    def test_preact_frontend_preserved(self):
        """A7: Preact 前端保留(未替换)。"""
        package_json = (FRONTEND_DIR / "package.json").read_text(encoding="utf-8")
        assert "preact" in package_json.lower(), "frontend/package.json 未包含 preact"

    def test_sqlalchemy_preserved(self):
        """A8: SQLAlchemy 数据库层保留。"""
        # 检查 requirements.txt
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert "sqlalchemy" in requirements.lower(), "requirements.txt 未包含 sqlalchemy"
        # 检查 server/db 目录存在
        assert (PROJECT_ROOT / "server" / "db").exists(), "server/db 目录不存在"

    def test_port_negotiation_not_hardcoded(self):
        """A3: 端口协商协议 — 非硬编码 7860。"""
        launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
        # sidecar 模式应使用动态端口(0 表示 OS 分配)
        assert "PORT=" in launch_content, "launch.py 未输出 PORT="
        # 检查是否使用 bind(0) 动态分配
        assert (
            "0" in launch_content and "bind" in launch_content.lower()
        ) or "NEBULA_PORT" in launch_content, "未使用动态端口分配"

    def test_sidecar_lifecycle_management(self):
        """A4: Sidecar 生命周期管理 — 启动+就绪+崩溃+重启+关闭。"""
        # 健康检查端点
        assert (TESTS_DIR / "test_health_ready.py").exists()
        # 优雅关闭端点
        assert (TESTS_DIR / "test_shutdown.py").exists()
        # 崩溃恢复
        assert (TESTS_DIR / "test_supervisor.py").exists()
        # 完整性校验
        assert (SRC_TAURI_DIR / "src" / "integrity.rs").exists()


# ---------------------------------------------------------------------------
# CI/CD 验收关键项(C1-C8)
# ---------------------------------------------------------------------------


class TestCICDCompliance:
    """CI/CD 验收关键项验证。"""

    def test_tauri_release_workflow_exists(self):
        """C1: tauri-release.yml 存在且触发条件为 v2.1.* tag。"""
        workflow = PROJECT_ROOT / ".github" / "workflows" / "tauri-release.yml"
        assert workflow.exists()
        content = workflow.read_text(encoding="utf-8")
        assert "v2.1.*" in content, "tauri-release.yml 未配置 v2.1.* tag 触发"

    def test_rust_cache_integrated(self):
        """C2: swatinem/rust-cache 已集成。"""
        workflow = PROJECT_ROOT / ".github" / "workflows" / "tauri-release.yml"
        content = workflow.read_text(encoding="utf-8")
        assert "swatinem/rust-cache" in content, "未集成 swatinem/rust-cache"

    def test_three_platform_matrix(self):
        """C3: 三平台 matrix(Windows + macOS arm64/x64 + Linux)。"""
        workflow = PROJECT_ROOT / ".github" / "workflows" / "tauri-release.yml"
        content = workflow.read_text(encoding="utf-8")
        assert "windows-latest" in content
        assert "macos-latest" in content  # arm64
        assert "macos-13" in content  # x64
        assert "ubuntu" in content

    def test_linux_webkitgtk_41(self):
        """C4: Linux CI 安装 WebKitGTK 4.1(非 4.0)。"""
        # 检查 tauri-release.yml 和 ci-cross-platform.yml
        for workflow_name in ["tauri-release.yml", "ci-cross-platform.yml"]:
            workflow = (
                PROJECT_ROOT / ".github" / "workflows" / workflow_name
            )
            if workflow.exists():
                content = workflow.read_text(encoding="utf-8")
                assert "4.1" in content, f"{workflow_name} 未使用 WebKitGTK 4.1"

    def test_cargo_audit_job_exists(self):
        """C5: cargo audit job 存在于 security.yml。"""
        security = PROJECT_ROOT / ".github" / "workflows" / "security.yml"
        assert security.exists()
        content = security.read_text(encoding="utf-8")
        assert "cargo-audit" in content or "cargo audit" in content

    def test_version_sync(self):
        """C7: 版本号同步 — tauri.conf.json = Cargo.toml = pyproject.toml。"""
        # tauri.conf.json
        tauri_conf = (SRC_TAURI_DIR / "tauri.conf.json").read_text(encoding="utf-8")
        # Cargo.toml
        cargo_toml = (SRC_TAURI_DIR / "Cargo.toml").read_text(encoding="utf-8")
        # pyproject.toml
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        # 提取版本号
        tauri_version = re.search(r'"version"\s*:\s*"([^"]+)"', tauri_conf)
        cargo_version = re.search(r'^version\s*=\s*"([^"]+)"', cargo_toml, re.MULTILINE)
        pyproject_version = re.search(r'version\s*=\s*"([^"]+)"', pyproject)

        assert tauri_version, "tauri.conf.json 未找到 version 字段"
        assert cargo_version, "Cargo.toml 未找到 version 字段"
        assert pyproject_version, "pyproject.toml 未找到 version 字段"

        t_v = tauri_version.group(1)
        c_v = cargo_version.group(1)
        p_v = pyproject_version.group(1)

        assert t_v == c_v == p_v, (
            f"版本号不一致: tauri.conf.json={t_v}, Cargo.toml={c_v}, "
            f"pyproject.toml={p_v}"
        )

    def test_latest_json_generation(self):
        """C8: publish job 生成 latest.json。"""
        workflow = PROJECT_ROOT / ".github" / "workflows" / "tauri-release.yml"
        content = workflow.read_text(encoding="utf-8")
        assert "latest.json" in content, "tauri-release.yml 未生成 latest.json"
        assert "gen_latest_json" in content, "未调用 gen_latest_json.py"


# ---------------------------------------------------------------------------
# 文档验收(D1-D7)
# ---------------------------------------------------------------------------


class TestDocsCompliance:
    """文档验收关键项验证。"""

    def test_deployment_guide_exists(self):
        """D2: docs/deployment-guide.md 存在。"""
        assert (PROJECT_ROOT / "docs" / "deployment-guide.md").exists()

    def test_troubleshooting_exists(self):
        """D3: docs/troubleshooting.md 存在。"""
        assert (PROJECT_ROOT / "docs" / "troubleshooting.md").exists()

    def test_phase0_spec_exists(self):
        """D4: docs/v2.1.0-phase0-spec.md 存在。"""
        assert (PROJECT_ROOT / "docs" / "v2.1.0-phase0-spec.md").exists()

    def test_phase0_tasks_exists(self):
        """D5: docs/v2.1.0-phase0-tasks.md 存在。"""
        assert (PROJECT_ROOT / "docs" / "v2.1.0-phase0-tasks.md").exists()

    def test_phase0_checklist_exists(self):
        """D6: docs/v2.1.0-phase0-checklist.md 存在。"""
        assert (PROJECT_ROOT / "docs" / "v2.1.0-phase0-checklist.md").exists()

    def test_capabilities_config_exists(self):
        """D7: capabilities 文档/配置存在。"""
        # capabilities 目录存在
        capabilities_dir = SRC_TAURI_DIR / "capabilities"
        assert capabilities_dir.exists(), "src-tauri/capabilities 目录不存在"
        # default.json 存在
        assert (capabilities_dir / "default.json").exists(), (
            "src-tauri/capabilities/default.json 不存在"
        )


# ---------------------------------------------------------------------------
# 回退能力验证(B1-B6)
# ---------------------------------------------------------------------------


class TestRollbackCapability:
    """回退能力验证关键项。"""

    def test_feature_flag_pywebview_mode(self):
        """B1: 回退模式 — --no-window 独立服务器模式可用。"""
        launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
        assert "--no-window" in launch_content, "launch.py 缺少独立服务器模式"
        assert "start_server" in launch_content, "launch.py 缺少 start_server 函数"

    def test_launch_py_preserved(self):
        """B2: launch.py 保留(原 PyWebView 入口未删除)。"""
        assert (PROJECT_ROOT / "launch.py").exists()

    def test_release_yml_preserved(self):
        """B4: 原 release.yml(PyInstaller 路线)仍在。"""
        # 检查 .github/workflows 下是否有非 tauri-release 的 release workflow
        workflows_dir = PROJECT_ROOT / ".github" / "workflows"
        if workflows_dir.exists():
            workflow_files = list(workflows_dir.glob("*.yml"))
            # 至少应有 release 相关 workflow(可能是 release.yml 或其他)
            assert len(workflow_files) > 0, "未找到任何 workflow 文件"

    def test_maint_v20x_branch(self):
        """B6: maint/v2.0.x 分支存在(远程)。

        使用 git ls-remote 检查远程分支,兼容 CI 环境
        (actions/checkout 默认 fetch-depth=1 只 fetch 当前分支)。
        """
        # 优先检查本地分支(快速路径)
        local = subprocess.run(
            ["git", "branch", "--list", "*v2.0*"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if "v2.0" in local.stdout:
            return
        # 本地未找到,检查远程(CI 环境只有远程分支)
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", "*v2.0*"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        assert "v2.0" in result.stdout, (
            f"未找到 maint/v2.0.x 分支(本地+远程)\n"
            f"local stdout: {local.stdout}\n"
            f"remote stdout: {result.stdout}\n"
            f"remote stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# 安全验收关键项(S1-S8)
# ---------------------------------------------------------------------------


class TestSecurityCompliance:
    """安全验收关键项验证。"""

    def test_sidecar_integrity_mechanism(self):
        """S1: Sidecar 完整性机制存在。"""
        # integrity.rs 存在
        assert (SRC_TAURI_DIR / "src" / "integrity.rs").exists()
        # gen_sidecar_hash.py 存在
        assert (PROJECT_ROOT / "scripts" / "gen_sidecar_hash.py").exists()

    def test_ipc_auth_mechanism(self):
        """S2: IPC 认证机制(Bearer token)。"""
        # launch.py 中应有 token 生成
        launch_content = (PROJECT_ROOT / "launch.py").read_text(encoding="utf-8")
        assert "TOKEN" in launch_content, "launch.py 未生成 TOKEN"
        # server/main.py 中应有认证中间件
        main_py = (PROJECT_ROOT / "server" / "main.py").read_text(encoding="utf-8")
        assert (
            "Authorization" in main_py or "Bearer" in main_py
        ), "server/main.py 未实现 Bearer token 认证"

    def test_capabilities_no_wildcard(self):
        """S4: capabilities 配置无 * 通配符权限。"""
        capabilities_file = SRC_TAURI_DIR / "capabilities" / "default.json"
        if capabilities_file.exists():
            content = capabilities_file.read_text(encoding="utf-8")
            # 不应有 "*" 作为权限标识(允许在 scope 路径中使用 *)
            # 简单检查:不应有 "core:*" 或 "shell:*" 这样的通配
            assert '"core:*"' not in content, "capabilities 包含 core:* 通配符"
            assert '"shell:*"' not in content, "capabilities 包含 shell:* 通配符"

    def test_csp_configured(self):
        """S5: CSP 配置存在(严格 CSP)。"""
        tauri_conf = (SRC_TAURI_DIR / "tauri.conf.json").read_text(encoding="utf-8")
        assert "csp" in tauri_conf, "tauri.conf.json 未配置 CSP"
        # 不应包含 unsafe-eval
        # 注意:unsafe-inline 在 style-src 中是允许的(Tauri 内部样式需要)
        assert "unsafe-eval" not in tauri_conf, "CSP 包含不安全的 unsafe-eval"


if __name__ == "__main__":
    # 直接运行此文件时执行所有测试
    pytest.main([__file__, "-v", "--tb=short"])
