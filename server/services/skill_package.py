"""技能包格式 — .skill 包定义

.skill 包是一个 JSON 文件，包含:
{
    "name": "skill-name",
    "version": "1.0.0",
    "description": "技能描述",
    "author": "作者",
    "dependencies": ["other-skill@1.0.0"],
    "capabilities": ["text", "vision"],
    "config": {...},
    "entry_point": "main.handler",
    "code": "base64 编码的 Python 代码 (可选)"
}

支持: 打包/解包/验证/安装/导出
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel


class SkillManifest(BaseModel):
    """技能包清单"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    capabilities: list[str] = ["text"]
    config: dict = {}
    entry_point: str = "main.handler"
    code: str = ""  # base64 encoded
    checksum: str = ""  # SHA256


# 简单语义版本号正则: MAJOR.MINOR.PATCH[-prerelease]
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
# 依赖格式: name@version (version 可选)
_DEP_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*(@\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)?$")
# 技能名只允许字母/数字/下划线/连字符
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")


class SkillPackager:
    """技能打包器"""

    @staticmethod
    def pack(manifest: SkillManifest, code_path: Path | None = None) -> bytes:
        """打包技能为 .skill 格式 (JSON)

        如果 code_path 提供，读取代码文件并 base64 编码到 manifest.code;
        否则保留 manifest.code 原值(可能为空字符串)。

        最终返回 JSON bytes (UTF-8 编码)。
        """
        # 拷贝一份,避免修改入参
        m = manifest.model_copy()
        if code_path is not None:
            code_bytes = Path(code_path).read_bytes()
            m.code = base64.b64encode(code_bytes).decode("ascii")
        # 计算整个 manifest(不含 checksum)的 SHA256 校验和
        m.checksum = ""
        payload = m.model_dump()
        # 排除 checksum 字段后计算校验和
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        m.checksum = hashlib.sha256(raw).hexdigest()
        return json.dumps(m.model_dump(), sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")

    @staticmethod
    def unpack(data: bytes) -> tuple[SkillManifest, bytes | None]:
        """解包 .skill 格式

        返回 (manifest, code_bytes)
        若 manifest.code 为空,code_bytes 为 None。
        """
        payload = json.loads(data.decode("utf-8"))
        manifest = SkillManifest(**payload)
        if manifest.code:
            try:
                code_bytes = base64.b64decode(manifest.code)
            except Exception as e:
                raise ValueError(f"invalid base64 code: {e}") from e
        else:
            code_bytes = None
        return manifest, code_bytes

    @staticmethod
    def validate(manifest: SkillManifest) -> tuple[bool, str]:
        """验证技能包

        检查:
        - name 非空且符合命名规范
        - version 符合 semver
        - dependencies 格式 (name@version)
        - capabilities 非空(至少包含 "text")

        返回 (valid, error_message);error_message 为空字符串表示通过。
        """
        if not manifest.name or not _NAME_RE.match(manifest.name):
            return False, f"invalid or empty name: {manifest.name!r}"
        if not _VERSION_RE.match(manifest.version):
            return False, f"invalid version format: {manifest.version!r}"
        for dep in manifest.dependencies:
            if not _DEP_RE.match(dep):
                return False, f"invalid dependency format: {dep!r} (expected name@version)"
        if not manifest.capabilities:
            return False, "capabilities must not be empty"
        return True, ""

    @staticmethod
    def calculate_checksum(data: bytes) -> str:
        """计算 SHA256 校验和"""
        return hashlib.sha256(data).hexdigest()


class SkillInstaller:
    """技能安装器"""

    def __init__(self, skills_dir: Path | None = None):
        self._skills_dir = Path(skills_dir) if skills_dir else Path("server/skills")

    async def install(self, data: bytes) -> dict:
        """安装技能包

        1. 解包
        2. 验证
        3. 检查依赖(目前仅校验格式,不做真实依赖解析)
        4. 写入 skills 目录 (name.skill + 可选 main.py)

        返回 {"ok": True, "data": {"name": ..., "version": ...}}
        或 {"ok": False, "data": None, "error": "..."}
        """
        try:
            manifest, code_bytes = SkillPackager.unpack(data)
        except Exception as e:
            return {"ok": False, "data": None, "error": f"unpack failed: {e}"}

        valid, err = SkillPackager.validate(manifest)
        if not valid:
            return {"ok": False, "data": None, "error": f"validation failed: {err}"}

        # 校验和验证(若 manifest 提供了 checksum,则重新计算并比对)
        if manifest.checksum:
            m_no_checksum = manifest.model_copy(update={"checksum": ""})
            payload = m_no_checksum.model_dump()
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            expected = hashlib.sha256(raw).hexdigest()
            if expected != manifest.checksum:
                return {"ok": False, "data": None, "error": "checksum mismatch"}

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        # 写入 .skill 清单文件
        skill_file = self._skills_dir / f"{manifest.name}.skill"
        skill_file.write_bytes(data)
        # 若包含代码,写入 main.py
        if code_bytes is not None:
            code_file = self._skills_dir / f"{manifest.name}.py"
            code_file.write_bytes(code_bytes)

        return {
            "ok": True,
            "data": {
                "name": manifest.name,
                "version": manifest.version,
                "path": str(skill_file),
                "has_code": code_bytes is not None,
            },
            "error": None,
        }

    async def uninstall(self, name: str) -> dict:
        """卸载技能

        删除 .skill 清单文件及对应的 .py 代码文件。
        """
        if not _NAME_RE.match(name):
            return {"ok": False, "data": None, "error": f"invalid skill name: {name!r}"}
        removed: list[str] = []
        for ext in (".skill", ".py"):
            f = self._skills_dir / f"{name}{ext}"
            if f.exists():
                f.unlink()
                removed.append(str(f))
        if not removed:
            return {"ok": False, "data": None, "error": f"skill not found: {name}"}
        return {"ok": True, "data": {"name": name, "removed": removed}, "error": None}

    async def list_installed(self) -> list[dict]:
        """列出已安装技能(扫描 .skill 文件)"""
        if not self._skills_dir.exists():
            return []
        result: list[dict] = []
        for f in self._skills_dir.glob("*.skill"):
            try:
                manifest, _ = SkillPackager.unpack(f.read_bytes())
                result.append({
                    "name": manifest.name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "author": manifest.author,
                    "capabilities": manifest.capabilities,
                    "dependencies": manifest.dependencies,
                    "path": str(f),
                    "has_code": bool(manifest.code),
                })
            except Exception:
                # 损坏的 .skill 文件跳过
                continue
        return result

    async def export(self, name: str) -> bytes:
        """导出技能为 .skill 包

        读取 skills_dir/{name}.skill 文件并返回其原始 bytes。
        若不存在则抛 FileNotFoundError。
        """
        f = self._skills_dir / f"{name}.skill"
        if not f.exists():
            raise FileNotFoundError(f"Skill package not found: {name}")
        return f.read_bytes()
