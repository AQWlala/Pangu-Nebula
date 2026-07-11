from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.skill_loader import SkillLoader
from ..services.sandbox_engine import PythonSandbox
from .models import SandboxExecuteRequest
from ..services.skill_engine import PromptSkillEngine
from ..services.marketplace import SkillMarketplace
from .models import SkillCreate, SkillUpdate, SkillExecuteRequest, SkillImportMarkdownRequest

router = APIRouter(prefix="/skills", tags=["skills"])

_loader = SkillLoader()
_engine = PromptSkillEngine(_loader)


class ImportRequest(BaseModel):
    path: str


def _skill_to_dict(skill) -> dict:
    return {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "path": skill.path,
        "enabled": skill.enabled,
        "tags": skill.tags,
    }


@router.get("")
async def list_skills():
    skills = await _loader.scan_all()
    return {"ok": True, "data": [_skill_to_dict(s) for s in skills], "error": None}


@router.post("")
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


@router.post("/import")
async def import_skill(req: ImportRequest):
    try:
        skill = await _loader.import_skill(req.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": _skill_to_dict(skill), "error": None}


@router.post("/sandbox/execute")
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


@router.post("/{name}/execute")
async def execute_skill(name: str, req: SkillExecuteRequest):
    """执行提示词技能,渲染模板并返回 prompt"""
    try:
        result = await _engine.execute_skill(name, req.variables)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/{name}/variables")
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


@router.get("/market/list")
async def list_marketplace():
    """列出技能市场所有可分享技能(builtin + custom)"""
    marketplace = SkillMarketplace(_loader)
    skills = await marketplace.list_marketplace()
    return {"ok": True, "data": skills, "error": None}


@router.post("/import-markdown")
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


@router.post("/{name}/export")
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


# ===== 以下为按名称操作的端点 =====


@router.get("/{name}")
async def get_skill(name: str):
    skill = await _loader.load_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": "Skill not found"})
    return {"ok": True, "data": {**_skill_to_dict(skill), "content": skill.content}, "error": None}


@router.put("/{name}")
async def update_skill(name: str, req: SkillUpdate):
    """更新技能内容(部分更新)"""
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
    return {"ok": True, "data": {**_skill_to_dict(skill), "content": skill.content}, "error": None}


@router.delete("/{name}")
async def delete_skill(name: str):
    deleted = await _loader.delete_skill(name)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Skill not found or not deletable"},
        )
    return {"ok": True, "data": {"name": name, "deleted": True}, "error": None}
