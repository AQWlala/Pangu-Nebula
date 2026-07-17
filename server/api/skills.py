import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..core.event_bus import get_event_bus
from ..db.engine import async_session
from ..db.orm import Skill as SkillRow
from ..services.skill_loader import SkillLoader
from ..services.sandbox_engine import PythonSandbox
from .models import SandboxExecuteRequest
from ..services.skill_engine import PromptSkillEngine
from ..services.marketplace import SkillMarketplace
from ..services.skill_package import (
    SkillManifest,
    SkillPackager,
    SkillInstaller,
)
from .models import SkillCreate, SkillUpdate, SkillExecuteRequest, SkillImportMarkdownRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

_loader = SkillLoader()
_engine = PromptSkillEngine(_loader)
_installer = SkillInstaller()


# ===== v2.3.0 Phase 3-C: enabled 持久化 + 事件发布 =====


async def _load_enabled_map() -> dict[str, bool]:
    """从 DB 读取所有 Skill 行的 {name: enabled} 映射

    DB 失败时返回空 dict (best-effort, 不阻塞技能列表加载)。
    """
    try:
        async with async_session() as session:
            rows = (await session.execute(select(SkillRow))).scalars().all()
            return {row.name: bool(row.enabled) for row in rows}
    except Exception:
        logger.debug("加载 Skill.enabled 映射失败 (DB 不可用?)", exc_info=True)
        return {}


async def _persist_skill_enabled(name: str, enabled: bool) -> None:
    """持久化单个技能的 enabled 状态到 DB

    策略: upsert — 按 name 查询, 存在则更新, 不存在则插入新行。
    DB 失败仅记录日志, 不抛异常 (CRUD 主流程不被阻断)。
    """
    try:
        async with async_session() as session:
            row = (
                await session.execute(select(SkillRow).where(SkillRow.name == name))
            ).scalar_one_or_none()
            if row is None:
                # 插入新行 (source/path 仅作占位, 实际由 loader 管理)
                row = SkillRow(name=name, enabled=enabled, source="custom")
                session.add(row)
            else:
                row.enabled = enabled
            await session.commit()
    except Exception:
        logger.warning("持久化 Skill.enabled 失败 name=%s", name, exc_info=True)


async def _publish_skill_toggled(name: str, enabled: bool) -> None:
    """发布 skill.enabled.toggled 事件

    异常不阻断主流程 (事件丢失可由下次全量加载修正)。
    """
    try:
        bus = get_event_bus()
        await bus.publish(
            "skill.enabled.toggled",
            {"skill_id": name, "enabled": enabled},
            source="skills_api",
        )
    except Exception:
        logger.debug("publish skill.enabled.toggled 失败 name=%s", name, exc_info=True)


class ImportRequest(BaseModel):
    path: str


# ===== 技能包 (.skill) 端点 (T5.3) =====


class PackRequest(BaseModel):
    """打包技能请求"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    capabilities: list[str] = ["text"]
    config: dict = {}
    entry_point: str = "main.handler"
    code: str = ""  # base64 encoded (可选)
    code_path: str | None = None  # 服务端读取的代码文件路径(可选)


class UnpackRequest(BaseModel):
    """解包请求"""

    data: str  # base64 编码的 .skill 文件内容


class ValidateRequest(BaseModel):
    """验证请求"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    capabilities: list[str] = ["text"]
    config: dict = {}
    entry_point: str = "main.handler"
    code: str = ""
    checksum: str = ""


class InstallRequest(BaseModel):
    """安装请求"""

    data: str  # base64 编码的 .skill 文件内容


class UninstallRequest(BaseModel):
    """卸载请求"""

    name: str


class ExportRequest(BaseModel):
    """导出请求"""

    name: str


def _skill_to_dict(skill) -> dict:
    return {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "path": skill.path,
        "enabled": skill.enabled,
        "tags": skill.tags,
    }


@router.get("", summary="列出技能", description="扫描并返回所有可用的提示词技能(builtin + custom)")
async def list_skills():
    skills = await _loader.scan_all()
    # Phase 3-C: 合并 DB 中的 enabled 状态 (DB 为权威源, loader 默认 True 仅作 fallback)
    enabled_map = await _load_enabled_map()
    result = []
    for s in skills:
        d = _skill_to_dict(s)
        if s.name in enabled_map:
            d["enabled"] = enabled_map[s.name]
        result.append(d)
    return {"ok": True, "data": result, "error": None}


@router.post("", summary="创建技能", description="创建新提示词技能,写入 data/skills/{name}.md")
async def create_skill(req: SkillCreate):
    """创建新提示词技能,写入 data/skills/{name}.md"""
    try:
        skill = await _loader.create_skill(
            name=req.name,
            description=req.description,
            category=req.category,
            prompt_template=req.prompt_template,
            tags=req.tags,
        )
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": _skill_to_dict(skill), "error": None}


@router.post("/import", summary="导入技能", description="从指定路径导入技能文件")
async def import_skill(req: ImportRequest):
    try:
        skill = await _loader.import_skill(req.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": _skill_to_dict(skill), "error": None}


@router.post("/sandbox/execute", summary="沙箱执行代码", description="在隔离的 Python 沙箱中执行代码,支持输入输出 schema 校验")
async def sandbox_execute(req: SandboxExecuteRequest):
    """执行Python沙箱代码"""
    sandbox = PythonSandbox(timeout=req.timeout)
    result = await sandbox.execute_skill(
        code=req.code,
        input_data=req.input_data,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
    )
    return {
        "ok": result.success,
        "data": {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.return_code,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "memory_exceeded": result.memory_exceeded,
            "peak_memory_mb": result.peak_memory_mb,
            "output": result.output,
        },
        "error": result.error,
    }


@router.post("/{name}/execute", summary="执行提示词技能", description="执行提示词技能,渲染模板并返回 prompt")
async def execute_skill(name: str, req: SkillExecuteRequest):
    """执行提示词技能,渲染模板并返回 prompt"""
    try:
        result = await _engine.execute_skill(name, req.variables)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/{name}/variables", summary="获取技能变量", description="返回该技能所需的变量列表")
async def get_skill_variables(name: str):
    """返回该技能所需的变量列表"""
    skill = await _loader.load_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Skill not found"})
    template = _engine._get_prompt_template(skill)
    variables = _engine.extract_variables(template)
    return {"ok": True, "data": {"name": name, "variables": variables}, "error": None}


# ===== 技能市场端点 (Phase 5D) =====
# 注意: 静态路径 /market/list 与 /import-markdown 必须注册在 /{name} 之前,
# 以免被路径参数捕获


@router.get("/market/list", summary="列出技能市场", description="列出技能市场所有可分享技能(builtin + custom)")
async def list_marketplace():
    """列出技能市场所有可分享技能(builtin + custom)"""
    marketplace = SkillMarketplace(_loader)
    skills = await marketplace.list_marketplace()
    return {"ok": True, "data": skills, "error": None}


@router.post("/import-markdown", summary="从 Markdown 导入", description="从 SKILL.md 内容导入技能")
async def import_from_markdown(req: SkillImportMarkdownRequest):
    """从 SKILL.md 内容导入技能"""
    marketplace = SkillMarketplace(_loader)
    try:
        info = await marketplace.import_from_markdown(req.content, overwrite=req.overwrite)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail={"ok": False, "data": None, "error": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": info, "error": None}


@router.post("/{name}/export", summary="导出技能", description="导出技能为标准 SKILL.md 格式")
async def export_skill(name: str):
    """导出技能为标准 SKILL.md 格式"""
    marketplace = SkillMarketplace(_loader)
    try:
        content = await marketplace.export_skill(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {
        "ok": True,
        "data": {"content": content, "filename": f"{name}.md"},
        "error": None,
    }


# ===== 技能包 (.skill) 操作端点 (T5.3) =====
# 注意: 静态路径 /pack /unpack /validate /install /uninstall /installed /export-package
# 必须注册在 /{name} 之前, 以免被路径参数捕获


def _b64decode(data: str) -> bytes:
    """安全解码 base64 字符串(允许带 padding 或不带 padding)"""
    import base64 as _b64

    pad = "=" * (-len(data) % 4)
    return _b64.b64decode(data + pad)


def _b64encode(data: bytes) -> str:
    import base64 as _b64

    return _b64.b64encode(data).decode("ascii")


@router.post("/pack", summary="打包技能", description="打包技能为 .skill 格式(JSON, base64 编码返回)")
async def pack_skill(req: PackRequest):
    """打包技能为 .skill 格式(JSON, base64 编码返回)"""
    manifest = SkillManifest(
        name=req.name,
        version=req.version,
        description=req.description,
        author=req.author,
        dependencies=req.dependencies,
        capabilities=req.capabilities,
        config=req.config,
        entry_point=req.entry_point,
        code=req.code,
    )
    code_path = Path(req.code_path) if req.code_path else None
    try:
        packed = SkillPackager.pack(manifest, code_path=code_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {
        "ok": True,
        "data": {
            "data": _b64encode(packed),
            "size": len(packed),
            "checksum": SkillPackager.calculate_checksum(packed),
        },
        "error": None,
    }


@router.post("/unpack", summary="解包技能", description="解包 .skill 格式")
async def unpack_skill(req: UnpackRequest):
    """解包 .skill 格式"""
    try:
        raw = _b64decode(req.data)
        manifest, code_bytes = SkillPackager.unpack(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    data = {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "dependencies": manifest.dependencies,
        "capabilities": manifest.capabilities,
        "config": manifest.config,
        "entry_point": manifest.entry_point,
        "checksum": manifest.checksum,
        "has_code": code_bytes is not None,
        "code_size": len(code_bytes) if code_bytes is not None else 0,
    }
    if code_bytes is not None:
        data["code"] = _b64encode(code_bytes)
    return {"ok": True, "data": data, "error": None}


@router.post("/validate", summary="验证技能包", description="验证技能包清单")
async def validate_skill(req: ValidateRequest):
    """验证技能包清单"""
    manifest = SkillManifest(
        name=req.name,
        version=req.version,
        description=req.description,
        author=req.author,
        dependencies=req.dependencies,
        capabilities=req.capabilities,
        config=req.config,
        entry_point=req.entry_point,
        code=req.code,
        checksum=req.checksum,
    )
    valid, err = SkillPackager.validate(manifest)
    return {"ok": True, "data": {"valid": valid, "error": err}, "error": None}


@router.post("/install", summary="安装技能包", description="安装技能包")
async def install_skill(req: InstallRequest):
    """安装技能包"""
    try:
        raw = _b64decode(req.data)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": f"invalid base64: {e}"})
    result = await _installer.install(raw)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/uninstall", summary="卸载技能包", description="卸载技能包")
async def uninstall_skill(req: UninstallRequest):
    """卸载技能包"""
    result = await _installer.uninstall(req.name)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/installed", summary="列出已安装技能包", description="列出已安装的 .skill 技能包")
async def list_installed_skills():
    """列出已安装的 .skill 技能包"""
    items = await _installer.list_installed()
    return {"ok": True, "data": items, "error": None}


@router.post("/export-package", summary="导出技能包", description="导出 .skill 技能包(返回 base64 编码内容)")
async def export_skill_package(req: ExportRequest):
    """导出 .skill 技能包(返回 base64 编码内容)"""
    try:
        raw = await _installer.export(req.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {
        "ok": True,
        "data": {
            "name": req.name,
            "data": _b64encode(raw),
            "size": len(raw),
            "filename": f"{req.name}.skill",
        },
        "error": None,
    }


# ===== 以下为按名称操作的端点 =====


@router.get("/{name}", summary="获取技能", description="根据名称获取技能详情(含内容)")
async def get_skill(name: str):
    skill = await _loader.load_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Skill not found"})
    data = {**_skill_to_dict(skill), "content": skill.content}
    # Phase 3-C: 合并 DB 中的 enabled 状态
    enabled_map = await _load_enabled_map()
    if name in enabled_map:
        data["enabled"] = enabled_map[name]
    return {"ok": True, "data": data, "error": None}


@router.put("/{name}", summary="更新技能", description="更新技能内容(部分更新,含 enabled 持久化)")
async def update_skill(name: str, req: SkillUpdate):
    """更新技能内容(部分更新)

    Phase 3-C: 若请求包含 enabled 字段, 仅更新 DB 中的 enabled 状态并发布事件,
    不触发 loader 的 markdown 重写 (避免 enabled toggle 误覆盖 prompt_template)。
    其他字段仍走 loader.update_skill 持久化到 markdown 文件。
    """
    # 1. 处理 enabled 持久化 (独立于 markdown 内容更新)
    if req.enabled is not None:
        await _persist_skill_enabled(name, req.enabled)
        await _publish_skill_toggled(name, req.enabled)
        # 同步更新 loader 内存缓存, 保证后续 load_skill 立即反映新状态
        cached = _loader._cache.get(name)
        if cached is not None:
            cached.enabled = req.enabled

    # 2. 处理 markdown 内容更新 (description/category/prompt_template/tags)
    # 若除 enabled 外还有其他字段需要更新, 走 loader
    has_content_update = any(
        v is not None
        for v in (req.description, req.category, req.prompt_template, req.tags)
    )
    if has_content_update:
        try:
            skill = await _loader.update_skill(
                name=name,
                description=req.description,
                category=req.category,
                prompt_template=req.prompt_template,
                tags=req.tags,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    else:
        # 仅 enabled 更新: 重新加载当前技能返回
        skill = await _loader.load_skill(name)
        if not skill:
            raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Skill not found"})

    data = {**_skill_to_dict(skill), "content": skill.content}
    # 合并 DB enabled (优先 DB 权威值)
    if req.enabled is not None:
        data["enabled"] = req.enabled
    else:
        enabled_map = await _load_enabled_map()
        if name in enabled_map:
            data["enabled"] = enabled_map[name]
    return {"ok": True, "data": data, "error": None}


@router.delete("/{name}", summary="删除技能", description="删除指定名称的技能(仅 custom 可删除)")
async def delete_skill(name: str):
    deleted = await _loader.delete_skill(name)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Skill not found or not deletable"},
        )
    return {"ok": True, "data": {"name": name, "deleted": True}, "error": None}
