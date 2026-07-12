from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..tools.registry import get_tool, list_tools
from ..services.orchestrator import Orchestrator

router = APIRouter(prefix="/tools", tags=["tools"])

_orchestrator = Orchestrator()


class ToolExecuteRequest(BaseModel):
    parameters: dict = {}


@router.get("", summary="列出工具", description="列出所有已注册的内置工具")
async def get_tools():
    return {"ok": True, "data": list_tools(), "error": None}


@router.post("/{name}/execute", summary="执行工具", description="按名称执行指定工具,传入参数字典")
async def execute_tool(name: str, body: ToolExecuteRequest):
    try:
        get_tool(name)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": str(exc)},
        )
    result = await _orchestrator.execute_single(name, body.parameters)
    return {
        "ok": result.success,
        "data": {"output": result.output, "error": result.error},
        "error": result.error if not result.success else None,
    }
