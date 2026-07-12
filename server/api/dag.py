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


@router.get("")
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
            ],
        },
        "error": None,
    }


@router.post("")
async def create_dag(req: DAGCreate, session: AsyncSession = Depends(get_session)):
    data = await _service.create_dag(
        session,
        req.dag_id,
        [n.model_dump() for n in req.nodes],
        [e.model_dump() for e in req.edges],
    )
    return {"ok": True, "data": data, "error": None}


@router.get("/list")
async def list_dags(session: AsyncSession = Depends(get_session)):
    data = await _service.list_dags(session)
    return {"ok": True, "data": data, "error": None}


@router.get("/{dag_id}")
async def get_dag(dag_id: str, session: AsyncSession = Depends(get_session)):
    data = await _service.get_dag(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{dag_id}/node/{node_id}")
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


@router.post("/{dag_id}/approve")
async def approve_dag(dag_id: str, session: AsyncSession = Depends(get_session)):
    data = await _service.approve_dag(session, dag_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "DAG not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.post("/{dag_id}/reject")
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
