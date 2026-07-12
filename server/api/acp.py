"""ACP (Agent Communication Protocol) API (T3.4-T3.6)

允许外部 Agent (Claude Code, Codex, Gemini CLI) 借用 Pangu Nebula 的:
- 记忆系统 (读写记忆)
- 蜂群能力 (发起蜂群任务)
- 技能系统 (调用技能)

端点总览:
- GET    /acp                   - 模块信息
- POST   /acp/agents            - 注册外部 Agent
- GET    /acp/agents            - 列出 Agent
- GET    /acp/agents/{id}       - 获取 Agent
- POST   /acp/agents/{id}/enable - 启用 Agent
- POST   /acp/agents/{id}/disable - 禁用 Agent
- DELETE /acp/agents/{id}       - 删除 Agent
- POST   /acp/call/memory       - 调用记忆系统
- POST   /acp/call/swarm        - 调用蜂群
- POST   /acp/call/skill        - 调用技能
- GET    /acp/logs              - 调用日志
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.acp_service import ACPService

router = APIRouter(prefix="/acp", tags=["acp"])
_service = ACPService()


# ===== Pydantic 请求模型 =====


class AgentRegisterRequest(BaseModel):
    """注册外部 Agent 请求"""

    name: str
    agent_type: str = "generic"  # generic/claude_code/codex/gemini_cli
    endpoint: str | None = None
    capabilities: list[str] = []
    auth_token: str | None = None


class ACPCallMemoryRequest(BaseModel):
    """ACP 调用记忆系统请求"""

    agent_id: int
    action: str  # read/write/search
    params: dict = {}


class ACPCallSwarmRequest(BaseModel):
    """ACP 调用蜂群请求"""

    agent_id: int
    task: str
    config: dict = {}


class ACPCallSkillRequest(BaseModel):
    """ACP 调用技能请求"""

    agent_id: int
    skill_name: str
    params: dict = {}


# ===== 模块信息 =====


@router.get("", summary="ACP 模块信息", description="获取 Agent Communication Protocol 模块信息,包括支持的 Agent 类型和可用能力")
async def get_acp_module():
    """获取 ACP 模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "acp",
            "name": "Agent Communication Protocol",
            "phase": "T3.4-T3.6",
            "supported_agent_types": list(ACPService.SUPPORTED_AGENT_TYPES),
            "capabilities": ["call_memory", "call_swarm", "call_skill"],
            "features": [
                "register_agent",
                "list_agents",
                "get_agent",
                "enable_agent",
                "disable_agent",
                "delete_agent",
                "call_memory",
                "call_swarm",
                "call_skill",
                "get_call_logs",
            ],
        },
        "error": None,
    }


# ===== Agent CRUD =====


@router.post("/agents", summary="注册 Agent", description="注册外部 Agent (Claude Code/Codex/Gemini CLI 等),支持指定类型、端点、能力和认证令牌")
async def register_agent(req: AgentRegisterRequest):
    """注册外部 Agent"""
    data = await _service.register_agent(
        name=req.name,
        agent_type=req.agent_type,
        endpoint=req.endpoint,
        capabilities=req.capabilities,
        auth_token=req.auth_token,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/agents", summary="列出 Agent", description="列出已注册的外部 Agent,可选仅返回启用的 Agent")
async def list_agents(enabled_only: bool = Query(True)):
    """列出已注册的外部 Agent"""
    data = await _service.list_agents(enabled_only=enabled_only)
    return {"ok": True, "data": data, "error": None}


@router.get("/agents/{agent_id}", summary="获取 Agent", description="获取单个外部 Agent 的详细信息")
async def get_agent(agent_id: int):
    """获取单个 Agent"""
    data = await _service.get_agent(agent_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Agent not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/agents/{agent_id}/enable", summary="启用 Agent", description="启用指定的外部 Agent")
async def enable_agent(agent_id: int):
    """启用 Agent"""
    result = await _service.enable_agent(agent_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result["agent"], "error": None}


@router.post("/agents/{agent_id}/disable", summary="禁用 Agent", description="禁用指定的外部 Agent")
async def disable_agent(agent_id: int):
    """禁用 Agent"""
    result = await _service.disable_agent(agent_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": result["agent"], "error": None}


@router.delete("/agents/{agent_id}", summary="删除 Agent", description="删除指定的外部 Agent")
async def delete_agent(agent_id: int):
    """删除 Agent"""
    result = await _service.delete_agent(agent_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": result.get("error")},
        )
    return {"ok": True, "data": {"id": agent_id, "deleted": True}, "error": None}


# ===== ACP 调用 =====


@router.post("/call/memory", summary="调用记忆系统", description="外部 Agent 调用 Pangu Nebula 记忆系统,支持 read/write/search 操作")
async def call_memory(req: ACPCallMemoryRequest):
    """调用记忆系统

    - action: read/write/search
    - params: {memory_id, layer, title, content, query, auth_token, ...}
    """
    data = await _service.call_memory(req.agent_id, req.action, req.params)
    if not data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": data.get("error")},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/call/swarm", summary="调用蜂群", description="外部 Agent 调用蜂群能力,发起一个蜂群任务")
async def call_swarm(req: ACPCallSwarmRequest):
    """调用蜂群 - 发起蜂群任务

    - task: 蜂群任务目标
    - config: {persona_id, worker_count, auth_token, ...}
    """
    data = await _service.call_swarm(req.agent_id, req.task, req.config)
    if not data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": data.get("error")},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/call/skill", summary="调用技能", description="外部 Agent 调用 Pangu Nebula 技能系统,按名称执行技能")
async def call_skill(req: ACPCallSkillRequest):
    """调用技能系统

    - skill_name: 技能名称
    - params: 技能参数(可包含 auth_token)
    """
    data = await _service.call_skill(req.agent_id, req.skill_name, req.params)
    if not data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "data": None, "error": data.get("error")},
        )
    return {"ok": True, "data": data, "error": None}


# ===== 调用日志 =====


@router.get("/logs", summary="获取调用日志", description="获取 ACP 调用日志,可按 agent_id 过滤并限制返回条数")
async def get_call_logs(
    agent_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """获取 ACP 调用日志"""
    data = await _service.get_call_logs(agent_id=agent_id, limit=limit)
    return {"ok": True, "data": data, "error": None}
