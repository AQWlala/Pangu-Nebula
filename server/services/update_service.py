"""自动更新服务 (T4.9)

实现 Pangu Nebula 应用的自动更新机制:
- 版本检查: 调用 update_manifest URL 比对当前版本与最新版本
- 下载安装: 下载新版本包,校验哈希,解压到临时目录,切换目录(原子)
- 回滚机制: 保留上一版本,失败或用户触发时回滚

注意:
- 实际下载/安装使用 mock 实现 (不实际下载,避免测试时网络依赖)
- API 和逻辑完整,可在生产环境替换 mock 为真实 HTTP 下载
- 配置项: NEBULA_UPDATE_MANIFEST_URL (默认空,即不自动检查)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import APP_DIR


# 当前应用版本 (与 launch.py 中 VERSION 保持一致)
CURRENT_VERSION = "2.1.3"

# 更新相关目录
UPDATE_DIR = APP_DIR / "data" / "updates"
BACKUP_DIR = UPDATE_DIR / "backup"
DOWNLOAD_DIR = UPDATE_DIR / "downloads"

# 状态文件 (记录当前版本 / 历史版本 / 回滚信息)
STATE_FILE = UPDATE_DIR / "state.json"

# 默认 manifest URL (可通过环境变量 NEBULA_UPDATE_MANIFEST_URL 覆盖)
DEFAULT_MANIFEST_URL = ""


# ----------------------------------------------------------------------
# 模拟下载器 (生产环境可替换为真实 HTTP 下载)
# ----------------------------------------------------------------------

class MockDownloader:
    """模拟下载器 - 不实际下载,仅用于测试和开发

    生产环境替换为真实 HTTP 下载实现,例如:
        class HttpDownloader:
            async def download(self, url: str, dest: Path, progress_cb=None):
                async with httpx.AsyncClient() as client:
                    async with client.stream("GET", url) as resp:
                        ...
    """

    async def download(
        self,
        url: str,
        dest: Path,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Path:
        """模拟下载 - 创建一个虚拟文件"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 模拟下载的文件内容 (实际为 JSON 状态)
        mock_content = json.dumps({
            "mock": True,
            "url": url,
            "downloaded_at": datetime.utcnow().isoformat(),
        }).encode("utf-8")
        dest.write_bytes(mock_content)
        # 进度回调
        if progress_cb is not None:
            progress_cb(len(mock_content), len(mock_content))
        return dest

    async def verify_hash(self, file_path: Path, expected_sha256: str) -> bool:
        """校验文件 SHA-256 (mock 模式下永远返回 True)"""
        if not expected_sha256:
            return True
        # 实际生产: 计算文件哈希并比对
        # mock 模式: 仅校验文件存在
        return file_path.exists()


# ----------------------------------------------------------------------
# 更新服务
# ----------------------------------------------------------------------

class UpdateService:
    """自动更新服务

    生命周期:
        1. check_for_updates() - 拉取 manifest, 比对版本
        2. download_update() - 下载新版本包 (mock)
        3. install_update() - 解压并切换目录 (mock)
        4. rollback_update() - 回滚到上一版本

    状态文件 (state.json):
        {
            "current_version": "1.0.0",
            "previous_version": null,  // 上一次安装的版本(用于回滚)
            "last_check_at": "2026-...",
            "last_update_at": null,
            "history": [...]  // 更新历史
        }
    """

    def __init__(
        self,
        manifest_url: str | None = None,
        downloader: MockDownloader | None = None,
    ):
        self.manifest_url = manifest_url or os.environ.get(
            "NEBULA_UPDATE_MANIFEST_URL", DEFAULT_MANIFEST_URL
        )
        self.downloader = downloader or MockDownloader()
        self._state: dict | None = None

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        """加载状态文件"""
        if self._state is not None:
            return self._state
        if STATE_FILE.exists():
            try:
                self._state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._state = self._default_state()
        else:
            self._state = self._default_state()
        return self._state

    def _save_state(self, state: dict) -> None:
        """保存状态文件"""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._state = state

    @staticmethod
    def _default_state() -> dict:
        return {
            "current_version": CURRENT_VERSION,
            "previous_version": None,
            "last_check_at": None,
            "last_update_at": None,
            "history": [],
        }

    # ------------------------------------------------------------------
    # 版本比较
    # ------------------------------------------------------------------

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """比较两个语义化版本号

        Returns:
            1 if v1 > v2
            0 if v1 == v2
            -1 if v1 < v2
        """
        def parse(v: str) -> tuple[int, ...]:
            # 去除前缀 v
            v = v.lstrip("vV")
            # 仅保留数字部分
            parts = []
            for p in v.split("."):
                num = ""
                for ch in p:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                parts.append(int(num) if num else 0)
            return tuple(parts)

        p1 = parse(v1)
        p2 = parse(v2)
        # 补齐长度
        max_len = max(len(p1), len(p2))
        p1 = p1 + (0,) * (max_len - len(p1))
        p2 = p2 + (0,) * (max_len - len(p2))
        if p1 > p2:
            return 1
        elif p1 < p2:
            return -1
        return 0

    # ------------------------------------------------------------------
    # 版本检查
    # ------------------------------------------------------------------

    async def check_for_updates(self) -> dict:
        """检查是否有新版本可用

        Returns:
            {
                "current_version": str,
                "latest_version": str,
                "update_available": bool,
                "manifest": dict,  // 完整 manifest
                "checked_at": str,
            }
        """
        state = self._load_state()
        state["last_check_at"] = datetime.utcnow().isoformat()
        self._save_state(state)

        # 拉取 manifest (mock 模式下使用默认值)
        manifest = await self._fetch_manifest()

        latest_version = manifest.get("version", CURRENT_VERSION)
        update_available = self._compare_versions(latest_version, CURRENT_VERSION) > 0

        return {
            "current_version": CURRENT_VERSION,
            "latest_version": latest_version,
            "update_available": update_available,
            "manifest": manifest,
            "checked_at": state["last_check_at"],
        }

    async def _fetch_manifest(self) -> dict:
        """获取远程 manifest (mock 实现)

        生产环境: 通过 httpx 拉取 self.manifest_url
        mock 模式: 返回固定 manifest (模拟有新版本可用)
        """
        if not self.manifest_url:
            # 未配置 URL - 返回当前版本 (无更新)
            return {
                "version": CURRENT_VERSION,
                "release_notes": "未配置更新源",
                "download_url": "",
                "sha256": "",
                "size_bytes": 0,
            }

        # mock: 总是返回比当前版本更高的版本号 (用于测试)
        # 生产环境替换为真实 HTTP 请求
        return {
            "version": "1.0.1",  # 模拟新版本
            "release_notes": "Bug fixes and performance improvements",
            "download_url": f"{self.manifest_url}/pangu-nebula-1.0.1.zip",
            "sha256": "mock_sha256_hash_value",
            "size_bytes": 50_000_000,
        }

    # ------------------------------------------------------------------
    # 下载更新
    # ------------------------------------------------------------------

    async def download_update(self, manifest: dict | None = None) -> dict:
        """下载新版本包

        Args:
            manifest: 可选,如未提供则自动拉取

        Returns:
            {
                "downloaded": bool,
                "file_path": str,
                "size_bytes": int,
                "sha256_verified": bool,
            }
        """
        if manifest is None:
            check_result = await self.check_for_updates()
            manifest = check_result["manifest"]

        download_url = manifest.get("download_url", "")
        if not download_url:
            return {
                "downloaded": False,
                "error": "Manifest 中无 download_url",
                "file_path": None,
            }

        # 生成下载文件路径
        version = manifest.get("version", "unknown")
        file_name = f"pangu-nebula-{version}.zip"
        dest_path = DOWNLOAD_DIR / file_name

        # 执行下载
        await self.downloader.download(download_url, dest_path)

        # 校验哈希
        expected_hash = manifest.get("sha256", "")
        hash_verified = await self.downloader.verify_hash(dest_path, expected_hash)

        return {
            "downloaded": True,
            "file_path": str(dest_path),
            "size_bytes": dest_path.stat().st_size if dest_path.exists() else 0,
            "sha256_verified": hash_verified,
            "version": version,
        }

    # ------------------------------------------------------------------
    # 安装更新
    # ------------------------------------------------------------------

    async def install_update(self, downloaded_file: str | Path | None = None) -> dict:
        """安装新版本

        流程:
            1. 备份当前版本目录到 BACKUP_DIR
            2. 解压新版本到目标目录 (mock: 仅创建标记文件)
            3. 更新状态文件 (current_version / previous_version)
            4. 返回安装结果

        注意:
            - mock 模式下不会实际替换可执行文件
            - 生产环境需要停止服务 → 替换文件 → 重启
        """
        if downloaded_file is None:
            # 自动下载
            dl_result = await self.download_update()
            if not dl_result.get("downloaded"):
                return {"installed": False, "error": "下载失败"}
            downloaded_file = dl_result["file_path"]

        downloaded_path = Path(downloaded_file)
        if not downloaded_path.exists():
            return {"installed": False, "error": f"文件不存在: {downloaded_path}"}

        state = self._load_state()
        previous_version = state["current_version"]

        # 备份当前版本 (mock: 仅创建标记文件)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_marker = BACKUP_DIR / f"backup_{previous_version}.marker"
        backup_marker.write_text(
            json.dumps({
                "version": previous_version,
                "backed_up_at": datetime.utcnow().isoformat(),
            }),
            encoding="utf-8",
        )

        # 解压新版本 (mock: 仅创建标记文件)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        version_marker = DOWNLOAD_DIR / "installed_version.txt"
        version_marker.write_text(
            json.dumps({
                "version": "1.0.1",
                "installed_at": datetime.utcnow().isoformat(),
                "source_file": str(downloaded_path),
            }),
            encoding="utf-8",
        )

        # 更新状态
        new_version = "1.0.1"  # mock 版本号
        state["previous_version"] = previous_version
        state["current_version"] = new_version
        state["last_update_at"] = datetime.utcnow().isoformat()
        state["history"].append({
            "from": previous_version,
            "to": new_version,
            "installed_at": state["last_update_at"],
            "source_file": str(downloaded_path),
        })
        self._save_state(state)

        return {
            "installed": True,
            "previous_version": previous_version,
            "new_version": new_version,
            "installed_at": state["last_update_at"],
            "restart_required": True,
        }

    # ------------------------------------------------------------------
    # 回滚机制
    # ------------------------------------------------------------------

    async def rollback_update(self) -> dict:
        """回滚到上一版本

        流程:
            1. 检查 previous_version 是否存在
            2. 从 BACKUP_DIR 恢复上一版本
            3. 更新状态文件 (交换 current_version / previous_version)
            4. 返回回滚结果

        注意:
            - mock 模式下不会实际恢复文件
            - 生产环境需要停止服务 → 恢复备份 → 重启
        """
        state = self._load_state()
        previous_version = state.get("previous_version")

        if not previous_version:
            return {
                "rolled_back": False,
                "error": "无可回滚的上一版本",
            }

        # 检查备份是否存在
        backup_marker = BACKUP_DIR / f"backup_{previous_version}.marker"
        if not backup_marker.exists():
            return {
                "rolled_back": False,
                "error": f"备份不存在: {backup_marker}",
            }

        # 执行回滚 (mock: 仅更新状态)
        current_version = state["current_version"]
        state["previous_version"] = current_version  # 当前版本变为可回滚的版本
        state["current_version"] = previous_version
        state["last_rollback_at"] = datetime.utcnow().isoformat()
        state["history"].append({
            "action": "rollback",
            "from": current_version,
            "to": previous_version,
            "rolled_back_at": state["last_rollback_at"],
        })
        self._save_state(state)

        return {
            "rolled_back": True,
            "from_version": current_version,
            "to_version": previous_version,
            "rolled_back_at": state["last_rollback_at"],
            "restart_required": True,
        }

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """获取当前更新状态"""
        state = self._load_state()
        return {
            "current_version": state["current_version"],
            "previous_version": state.get("previous_version"),
            "last_check_at": state.get("last_check_at"),
            "last_update_at": state.get("last_update_at"),
            "last_rollback_at": state.get("last_rollback_at"),
            "history_count": len(state.get("history", [])),
            "manifest_url": self.manifest_url or None,
        }

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取更新历史"""
        state = self._load_state()
        history = state.get("history", [])
        return history[-limit:]


# 模块级单例
update_service = UpdateService()
