from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_session
from ..services.dag_service import DAGService

router = APIRouter(prefix="/dag", tags=["dag"])
_service = DAGService()


class DAGNodeSpec(BaseModel):
    node_id: str
    title: str = ""
    node_type: str = "task"  # task/decision/approval
    status: str = "pending"
    model: str | None = None
    brief: str | None = None
    config: dict = {}


class DAGEdgeSpec(BaseModel):
    source_node_id: str
    target_node_id: str
    edge_type: str = "sequence"  # sequence/condition/parallel
    condition: str | None = None


class DAGCreate(BaseModel):
    dag_id: str
    nodes: list[DAGNodeSpec]
    edges: list[DAGEdgeSpec] = []


class DAGNodeUpdate(BaseModel):
    status: str
    result: str | None = None


class DAGReject(BaseModel):
    reason: str


class DAGNodePrecheck(BaseModel):
    """节点级预检请求 (T2.4) - 覆盖单个节点的 model 和 brief"""

    model: str | None = None
    brief: str | None = None


@router.get("", summary="DAG 模块信息", description="返回 DAG 编排数据模型的模块信息和端点列表")
async def module_info():
    return {
        "ok": True,
        "data": {
            "module": "dag",
            "description": "DAG 编排数据模型",
            "endpoints": [
                "POST /dag", "GET /dag/list", "GET /dag/{dag_id}",
                "PUT /dag/{dag_id}/node/{node_id}",
                "POST /dag/{dag_id}/approve", "POST /dag/{dag_id}/reject",
                "GET /dag/{dag_id}/approval-status",
                "POST /dag/{dag_id}/reset-planning",
                "POST /dag/{dag_id}/precheck",
            ],
        },
        "error": None,
    }


@router.post("", summary="创建 DAG", description="创建一个新的 DAG 工作流,包含节点和边定义")
async def create_dag(req: DAGCreate, session: AsyncSession = Depends(get_session)):
    data = await _service.create_dag(
        session,
        req.dag_id,
        [n.model_dump() for n in req.nodes],
        [e.model_dump() for e in req.edges],
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/list", summary="列出 DAG", description="列出所有 DAG 工作流")
async def list_dags(session: AsyncSession = Depends(get_session)):
    data = await _service.list_dags(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/{dag_id}", summary="获取 DAG", description="根据 ID 获取单个 DAG 工作流详情")
async def get_dag(dag_id: str, session: AsyncSession = Depends(get_session)):
    data = await _service.get_dag(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{dag_id}/node/{node_id}", summary="更新节点状态", description="更新 DAG 中指定节点的状态和结果")
async def update_node(
    dag_id: str,
    node_id: str,
    req: DAGNodeUpdate,
    session: AsyncSession = Depends(get_session),
):
    data = await _service.update_node_status(
        session, dag_id, node_id, req.status, req.result
    )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Node not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{dag_id}/approve", summary="审批通过 DAG", description="审批通过指定的 DAG 工作流")
async def approve_dag(dag_id: str, session: AsyncSession = Depends(get_session)):
    data = await _service.approve_dag(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{dag_id}/reject", summary="驳回 DAG", description="驳回指定的 DAG 工作流,并提交驳回原因")
async def reject_dag(
    dag_id: str, req: DAGReject, session: AsyncSession = Depends(get_session)
):
    data = await _service.reject_dag(session, dag_id, req.reason)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get(
    "/{dag_id}/approval-status",
    summary="获取审批状态",
    description="返回 DAG 的审批状态,包括 plan_ready、待审批节点列表、整体状态",
)
async def get_approval_status(
    dag_id: str, session: AsyncSession = Depends(get_session)
):
    data = await _service.get_approval_status(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post(
    "/{dag_id}/reset-planning",
    summary="回退到规划状态",
    description="将 DAG 中所有 skipped 节点重置为 pending,以便重新规划",
)
async def reset_to_planning(
    dag_id: str, session: AsyncSession = Depends(get_session)
):
    data = await _service.reset_to_planning(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post(
    "/{dag_id}/node/{node_id}/precheck",
    summary="节点级预检",
    description="为指定节点设置 model/brief override 并执行预检,通过后才可执行",
)
async def precheck_node(
    dag_id: str,
    node_id: str,
    req: DAGNodePrecheck,
    session: AsyncSession = Depends(get_session),
):
    data = await _service.precheck_node(
        session, dag_id, node_id, req.model, req.brief
    )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Node not found"},
        )
    return {"ok": True, "data": data, "error": None}
