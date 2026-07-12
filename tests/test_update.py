"""T4.9 自动更新测试

测试范围:
- 版本比较逻辑
- 版本检查 (mock manifest)
- 下载更新 (mock 下载器)
- 安装更新 (备份 + 状态切换)
- 回滚机制 (状态恢复)
- API 端点 (注册到测试 app, 不修改 main.py)

注意:
- 下载/安装使用 mock,不实际下载文件
- 状态文件使用临时目录隔离,不污染真实数据
"""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.update import router as update_router
from server.services.update_service import (
    UpdateService,
    MockDownloader,
    CURRENT_VERSION,
)


# ----------------------------------------------------------------------
# 测试用 fixture: 隔离的临时目录 + 更新服务实例
# ----------------------------------------------------------------------

@pytest.fixture
def isolated_update_service(tmp_path, monkeypatch):
    """创建使用临时目录的 UpdateService 实例,避免污染真实数据"""
    from server.services import update_service as us_module

    # 临时目录
    update_dir = tmp_path / "updates"
    backup_dir = update_dir / "backup"
    download_dir = update_path = update_dir / "downloads"
    state_file = update_dir / "state.json"

    # patch 全局常量
    monkeypatch.setattr(us_module, "UPDATE_DIR", update_dir)
    monkeypatch.setattr(us_module, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(us_module, "DOWNLOAD_DIR", download_dir)
    monkeypatch.setattr(us_module, "STATE_FILE", state_file)

    # 创建服务实例 (使用 mock URL 触发"有更新"分支)
    service = UpdateService(manifest_url="https://mock.test/manifest.json")

    # 同时 patch 全局单例 (供 API 测试使用)
    from server.api import update as api_module
    monkeypatch.setattr(api_module, "update_service", service)

    yield service


@pytest.fixture
def update_client(isolated_update_service):
    """创建测试客户端 (注册 update router)"""
    app = FastAPI()
    app.include_router(update_router)
    return TestClient(app)


# ----------------------------------------------------------------------
# 版本比较逻辑测试
# ----------------------------------------------------------------------

class TestVersionComparison:
    """版本比较逻辑测试"""

    def test_compare_equal_versions(self):
        """相同版本应返回 0"""
        assert UpdateService._compare_versions("1.0.0", "1.0.0") == 0

    def test_compare_higher_version(self):
        """更高版本应返回 1"""
        assert UpdateService._compare_versions("1.0.1", "1.0.0") == 1
        assert UpdateService._compare_versions("2.0.0", "1.9.9") == 1
        assert UpdateService._compare_versions("1.1.0", "1.0.9") == 1

    def test_compare_lower_version(self):
        """更低版本应返回 -1"""
        assert UpdateService._compare_versions("1.0.0", "1.0.1") == -1
        assert UpdateService._compare_versions("1.9.9", "2.0.0") == -1

    def test_compare_with_v_prefix(self):
        """带 v 前缀的版本号应正确比较"""
        assert UpdateService._compare_versions("v1.0.0", "1.0.0") == 0
        assert UpdateService._compare_versions("v1.0.1", "v1.0.0") == 1

    def test_compare_different_length(self):
        """不同长度的版本号应正确比较 (补 0)"""
        assert UpdateService._compare_versions("1.0", "1.0.0") == 0
        assert UpdateService._compare_versions("1.0.1", "1.0") == 1

    def test_compare_with_suffix(self):
        """带后缀的版本号应正确比较 (仅数字部分)"""
        assert UpdateService._compare_versions("1.0.0-beta", "1.0.0") == 0
        assert UpdateService._compare_versions("1.0.1-rc1", "1.0.0") == 1


# ----------------------------------------------------------------------
# 版本检查测试
# ----------------------------------------------------------------------

class TestVersionCheck:
    """版本检查测试"""

    @pytest.mark.asyncio
    async def test_check_for_updates_no_manifest_url(self, tmp_path, monkeypatch):
        """未配置 manifest URL 时应返回无更新"""
        from server.services import update_service as us_module
        monkeypatch.setattr(us_module, "UPDATE_DIR", tmp_path / "updates")
        monkeypatch.setattr(us_module, "STATE_FILE", tmp_path / "updates" / "state.json")

        service = UpdateService(manifest_url="")
        result = await service.check_for_updates()

        assert result["current_version"] == CURRENT_VERSION
        assert result["update_available"] is False
        assert result["latest_version"] == CURRENT_VERSION
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_check_for_updates_with_manifest_url(self, isolated_update_service):
        """配置 manifest URL 时应返回有更新"""
        result = await isolated_update_service.check_for_updates()

        assert result["current_version"] == CURRENT_VERSION
        assert result["update_available"] is True
        assert result["latest_version"] == "1.0.1"
        assert "manifest" in result
        assert result["manifest"]["version"] == "1.0.1"


# ----------------------------------------------------------------------
# 下载更新测试
# ----------------------------------------------------------------------

class TestDownloadUpdate:
    """下载更新测试"""

    @pytest.mark.asyncio
    async def test_download_update_success(self, isolated_update_service):
        """下载新版本成功 (mock)"""
        result = await isolated_update_service.download_update()

        assert result["downloaded"] is True
        assert "file_path" in result
        assert Path(result["file_path"]).exists()
        assert result["sha256_verified"] is True
        assert result["version"] == "1.0.1"

    @pytest.mark.asyncio
    async def test_download_update_no_url(self, tmp_path, monkeypatch):
        """manifest 中无 download_url 时应失败"""
        from server.services import update_service as us_module
        monkeypatch.setattr(us_module, "UPDATE_DIR", tmp_path / "updates")
        monkeypatch.setattr(us_module, "STATE_FILE", tmp_path / "updates" / "state.json")

        service = UpdateService(manifest_url="")
        result = await service.download_update()

        assert result["downloaded"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_download_with_custom_manifest(self, isolated_update_service, tmp_path):
        """使用自定义 manifest 下载"""
        # 创建临时文件作为下载目标
        custom_manifest = {
            "version": "2.0.0",
            "download_url": "https://mock.test/v2.0.0.zip",
            "sha256": "",
            "size_bytes": 100,
        }
        result = await isolated_update_service.download_update(manifest=custom_manifest)

        assert result["downloaded"] is True
        assert result["version"] == "2.0.0"


# ----------------------------------------------------------------------
# 安装更新测试
# ----------------------------------------------------------------------

class TestInstallUpdate:
    """安装更新测试"""

    @pytest.mark.asyncio
    async def test_install_update_full_flow(self, isolated_update_service):
        """完整安装流程: 检查 → 下载 → 安装"""
        # 1. 安装 (会自动下载)
        result = await isolated_update_service.install_update()

        assert result["installed"] is True
        assert result["previous_version"] == CURRENT_VERSION
        assert result["new_version"] == "1.0.1"
        assert result["restart_required"] is True

        # 2. 验证状态已更新
        status = isolated_update_service.get_status()
        assert status["current_version"] == "1.0.1"
        assert status["previous_version"] == CURRENT_VERSION
        assert status["last_update_at"] is not None

    @pytest.mark.asyncio
    async def test_install_update_with_existing_file(self, isolated_update_service, tmp_path):
        """使用已有文件安装"""
        # 创建虚拟下载文件
        file_path = tmp_path / "pangu-nebula-1.0.1.zip"
        file_path.write_bytes(b"mock update package")

        result = await isolated_update_service.install_update(downloaded_file=str(file_path))

        assert result["installed"] is True
        assert result["previous_version"] == CURRENT_VERSION

    @pytest.mark.asyncio
    async def test_install_update_nonexistent_file(self, isolated_update_service):
        """文件不存在时应失败"""
        result = await isolated_update_service.install_update(
            downloaded_file="/nonexistent/path/file.zip"
        )

        assert result["installed"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_install_creates_backup(self, isolated_update_service):
        """安装时应创建备份"""
        await isolated_update_service.install_update()

        from server.services.update_service import BACKUP_DIR
        backup_files = list(BACKUP_DIR.glob("backup_*.marker"))
        assert len(backup_files) == 1
        assert f"backup_{CURRENT_VERSION}.marker" in [f.name for f in backup_files]

    @pytest.mark.asyncio
    async def test_install_records_history(self, isolated_update_service):
        """安装应在历史中记录"""
        await isolated_update_service.install_update()

        history = isolated_update_service.get_history()
        assert len(history) == 1
        assert history[0]["from"] == CURRENT_VERSION
        assert history[0]["to"] == "1.0.1"


# ----------------------------------------------------------------------
# 回滚机制测试
# ----------------------------------------------------------------------

class TestRollback:
    """回滚机制测试"""

    @pytest.mark.asyncio
    async def test_rollback_without_previous_version(self, isolated_update_service):
        """未安装过新版本时回滚应失败"""
        result = await isolated_update_service.rollback_update()

        assert result["rolled_back"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rollback_after_install(self, isolated_update_service):
        """安装后回滚应成功"""
        # 1. 安装新版本
        install_result = await isolated_update_service.install_update()
        assert install_result["installed"] is True

        # 2. 回滚
        rollback_result = await isolated_update_service.rollback_update()

        assert rollback_result["rolled_back"] is True
        assert rollback_result["from_version"] == "1.0.1"
        assert rollback_result["to_version"] == CURRENT_VERSION
        assert rollback_result["restart_required"] is True

        # 3. 验证状态已恢复
        status = isolated_update_service.get_status()
        assert status["current_version"] == CURRENT_VERSION
        assert status["previous_version"] == "1.0.1"

    @pytest.mark.asyncio
    async def test_rollback_records_history(self, isolated_update_service):
        """回滚应在历史中记录"""
        await isolated_update_service.install_update()
        await isolated_update_service.rollback_update()

        history = isolated_update_service.get_history()
        assert len(history) == 2
        # 第二条应为回滚记录
        assert history[1]["action"] == "rollback"
        assert history[1]["from"] == "1.0.1"
        assert history[1]["to"] == CURRENT_VERSION


# ----------------------------------------------------------------------
# 状态查询测试
# ----------------------------------------------------------------------

class TestStatusQuery:
    """状态查询测试"""

    def test_get_status_initial(self, isolated_update_service):
        """初始状态正确"""
        status = isolated_update_service.get_status()

        assert status["current_version"] == CURRENT_VERSION
        assert status["previous_version"] is None
        assert status["last_check_at"] is None
        assert status["last_update_at"] is None
        assert status["history_count"] == 0

    @pytest.mark.asyncio
    async def test_get_status_after_check(self, isolated_update_service):
        """检查后状态应包含 last_check_at"""
        await isolated_update_service.check_for_updates()

        status = isolated_update_service.get_status()
        assert status["last_check_at"] is not None

    def test_get_history_empty(self, isolated_update_service):
        """初始历史为空"""
        history = isolated_update_service.get_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_with_limit(self, isolated_update_service):
        """历史记录 limit 参数有效"""
        # 多次安装 + 回滚
        for _ in range(3):
            await isolated_update_service.install_update()
            await isolated_update_service.rollback_update()

        history = isolated_update_service.get_history(limit=3)
        assert len(history) == 3  # 仅返回最后 3 条


# ----------------------------------------------------------------------
# API 端点测试
# ----------------------------------------------------------------------

class TestUpdateAPI:
    """API 端点测试 (注册到测试 app)"""

    def test_update_info_endpoint(self, update_client):
        """GET /update/info 返回模块信息"""
        response = update_client.get("/update/info")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["module"] == "update"
        assert data["data"]["current_version"] == CURRENT_VERSION

    def test_update_status_endpoint(self, update_client):
        """GET /update/status 返回当前状态"""
        response = update_client.get("/update/status")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["current_version"] == CURRENT_VERSION

    def test_update_check_endpoint(self, update_client):
        """GET /update/check 检查新版本"""
        response = update_client.get("/update/check")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["current_version"] == CURRENT_VERSION
        assert data["data"]["latest_version"] == "1.0.1"
        assert data["data"]["update_available"] is True

    def test_update_download_endpoint(self, update_client):
        """POST /update/download 下载新版本"""
        response = update_client.post("/update/download")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["downloaded"] is True

    def test_update_install_endpoint(self, update_client):
        """POST /update/install 安装新版本"""
        response = update_client.post("/update/install")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["installed"] is True
        assert data["data"]["previous_version"] == CURRENT_VERSION
        assert data["data"]["new_version"] == "1.0.1"

    def test_update_rollback_endpoint_without_previous(self, update_client):
        """POST /update/rollback 无上一版本时应返回 400"""
        response = update_client.post("/update/rollback")
        # 无 previous_version,应返回 400
        assert response.status_code == 400
        data = response.json()
        detail = data["detail"]
        assert detail["ok"] is False
        assert "error" in detail

    def test_update_rollback_after_install(self, update_client):
        """完整流程: 安装 → 回滚"""
        # 1. 安装
        install_resp = update_client.post("/update/install")
        assert install_resp.status_code == 200

        # 2. 回滚
        rollback_resp = update_client.post("/update/rollback")
        assert rollback_resp.status_code == 200
        rb_data = rollback_resp.json()
        assert rb_data["ok"] is True
        assert rb_data["data"]["rolled_back"] is True
        assert rb_data["data"]["from_version"] == "1.0.1"
        assert rb_data["data"]["to_version"] == CURRENT_VERSION

    def test_update_history_endpoint(self, update_client):
        """GET /update/history 返回历史记录"""
        # 先安装一次产生历史
        update_client.post("/update/install")

        response = update_client.get("/update/history")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["count"] >= 1
        assert len(data["data"]["history"]) >= 1


# ----------------------------------------------------------------------
# Mock 下载器测试
# ----------------------------------------------------------------------

class TestMockDownloader:
    """Mock 下载器测试"""

    @pytest.mark.asyncio
    async def test_download_creates_file(self, tmp_path):
        """下载应创建文件"""
        downloader = MockDownloader()
        dest = tmp_path / "test.zip"
        result = await downloader.download("https://mock.test/file.zip", dest)

        assert result == dest
        assert dest.exists()
        content = dest.read_bytes()
        assert b"mock" in content or b"url" in content

    @pytest.mark.asyncio
    async def test_download_progress_callback(self, tmp_path):
        """下载应触发进度回调"""
        downloader = MockDownloader()
        dest = tmp_path / "test.zip"
        progress_calls = []

        await downloader.download(
            "https://mock.test/file.zip",
            dest,
            progress_cb=lambda current, total: progress_calls.append((current, total)),
        )

        assert len(progress_calls) >= 1
        assert progress_calls[-1][0] == progress_calls[-1][1]  # current == total

    @pytest.mark.asyncio
    async def test_verify_hash_with_empty_hash(self, tmp_path):
        """空哈希应直接通过"""
        downloader = MockDownloader()
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(b"test")

        result = await downloader.verify_hash(file_path, "")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_hash_existing_file(self, tmp_path):
        """已有文件应通过哈希校验"""
        downloader = MockDownloader()
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(b"test")

        result = await downloader.verify_hash(file_path, "any_hash")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_hash_nonexistent_file(self, tmp_path):
        """不存在的文件应不通过哈希校验"""
        downloader = MockDownloader()
        result = await downloader.verify_hash(tmp_path / "nonexistent", "any_hash")
        assert result is False
