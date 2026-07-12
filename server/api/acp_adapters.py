"""ACP 适配器管理 API (T3.5)

提供外部 Agent 适配器的查询与调用端点。
注意:本路由不注册到 main.py(由主线程统一管理路由注册),
但可被测试通过直接挂载到 app 上进行验证。

端点总览:
- GET    /acp-adapters                - 列出所有可用适配器类型
- GET    /acp-adapters/{name}         - 获取适配器详情
- POST   /acp-adapters/{name}/register - 注册适配器为外部 Agent
- POST   /acp-adapters/{name}/call/memory  - 通过适配器调用记忆
- POST   /acp-adapters/{name}/call/swarm   - 通过适配器调用蜂群
- POST   /acp-adapters/{name}/call/skill   - 通过适配器调用技能
- GET    /acp-adapters/{name}/logs    - 获取适配器调用日志
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.acp_adapters import get_adapter, list_adapters
from ..services.acp_service import ACPService

router = APIRouter(prefix="/acp-adapters", tags=["acp-adapters"])
_service = ACPService()

# 已注册适配器实例缓存: name -> (adapter, agent_id)
# 用于在多次调用间保持注册状态
_adapter_cache: dict[str, object] = {}


# ===== 请求模型 =====


class AdapterRegisterRequest(BaseModel):
    """适配器注册请求"""

    name_override: str | None = None  # 自定义 Agent 名称
    endpoint_override: str | None = None  # 自定义端点
    auth_token: str | None = None


class AdapterCallMemoryRequest(BaseModel):
    """适配器调用记忆请求"""

    query: str
    action: str = "search"  # read/write/search


class AdapterCallSwarmRequest(BaseModel):
    """适配器调用蜂群请求"""

    task: str
    config: dict = {}


class AdapterCallSkillRequest(BaseModel):
    """适配器调用技能请求"""

    skill_id: str
    input: dict = {}


# ===== 端点 =====


@router.get("", summary="列出适配器", description="列出所有可用的外部 Agent 适配器类型")
async def list_all_adapters():
    """列出所有可用适配器类型"""
    return {"ok": True, "data": list_adapters(), "error": None}


@router.get("/{name}", summary="获取适配器", description="获取指定适配器的详细信息")
async def get_adapter_info(name: str):
    """获取适配器详情"""
    try:
        adapter = get_adapter(name, service=_service)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": adapter.info(), "error": None}


@router.post("/{name}/register", summary="注册适配器", description="将适配器注册为外部 Agent")
async def register_adapter_endpoint(name: str, req: AdapterRegisterRequest):
    """注册适配器为外部 Agent"""
    try:
        adapter = get_adapter(name, service=_service, auth_token=req.auth_token)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    agent = await adapter.register(
        name=req.name_override, endpoint=req.endpoint_override
    )
    _adapter_cache[name] = adapter
    return {"ok": True, "data": agent, "error": None}


@router.post("/{name}/call/memory", summary="调用记忆", description="通过适配器调用 Pangu Nebula 记忆系统")
async def call_memory_via_adapter(name: str, req: AdapterCallMemoryRequest):
    """通过适配器调用记忆系统"""
    adapter = _get_or_404(name)
    try:
        result = await adapter.call_memory(req.query, req.action)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.post("/{name}/call/swarm", summary="调用蜂群", description="通过适配器调用蜂群能力")
async def call_swarm_via_adapter(name: str, req: AdapterCallSwarmRequest):
    """通过适配器调用蜂群"""
    adapter = _get_or_404(name)
    try:
        result = await adapter.call_swarm(req.task, req.config)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.post("/{name}/call/skill", summary="调用技能", description="通过适配器调用技能系统")
async def call_skill_via_adapter(name: str, req: AdapterCallSkillRequest):
    """通过适配器调用技能"""
    adapter = _get_or_404(name)
    try:
        result = await adapter.call_skill(req.skill_id, req.input)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": result, "error": None}


@router.get("/{name}/logs", summary="适配器调用日志", description="获取指定适配器的调用日志")
async def get_adapter_logs(name: str, limit: int = 100):
    """获取适配器调用日志"""
    adapter = _get_or_404(name)
    try:
        logs = await adapter.get_logs(limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": logs, "error": None}


# ===== 内部辅助 =====


def _get_or_404(name: str):
    """从缓存获取已注册适配器,否则 404"""
    if name not in _adapter_cache:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "data": None,
                "error": f"适配器 {name} 尚未注册,请先 POST /acp-adapters/{name}/register",
            },
        )
    return _adapter_cache[name]
