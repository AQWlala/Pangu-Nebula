"""Phase 6C: Loop 循环迭代 API。

路由顺序说明:
  /loop/{loop_id}/run 和 /loop/{loop_id}/cancel 使用 POST 方法,
  /loop/{loop_id} 使用 GET / DELETE 方法,路径深度不同,不会冲突。
  为清晰起见,将带子路径的路由放在 {loop_id} 路由之前定义。
"""

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..services.loop_engine import LoopEngine
from .models import LoopCreateRequest, LoopUpdateRequest

router = APIRouter(prefix="/loop", tags=["loop"])
_engine = LoopEngine()


@router.post("")
async def create_loop(req: LoopCreateRequest):
    """创建循环任务"""
    data = await _engine.create_loop(
        persona_id=req.persona_id,
        goal=req.goal,
        max_iterations=req.max_iterations,
    )
    return {"ok": True, "data": data, "error": None}


@router.get("")
async def list_loops(
    persona_id: int | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出循环任务(支持按 persona_id / status 过滤)"""
    data = await _engine.list_loops(
        persona_id=persona_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {"ok": True, "data": data, "error": None}


# 注意: 带 /run 和 /cancel 子路径的路由必须在 /{loop_id} 之前定义,
# 以避免路径参数匹配冲突(虽然此处方法不同,但保持顺序一致性)
@router.post("/{loop_id}/run")
async def run_loop(loop_id: int):
    """执行循环(SSE 流式响应)"""
    loop = await _engine.get_loop(loop_id)
    if loop is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Loop not found"},
        )

    async def event_stream():
        async for event in _engine.run_loop(loop_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{loop_id}/cancel")
async def cancel_loop(loop_id: int):
    """取消循环"""
    data = await _engine.cancel_loop(loop_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Loop not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/{loop_id}")
async def get_loop(loop_id: int):
    """获取循环详情"""
    data = await _engine.get_loop(loop_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Loop not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/{loop_id}")
async def update_loop(loop_id: int, req: LoopUpdateRequest):
    """更新循环状态(目前仅支持取消:status="cancelled")"""
    if req.status == "cancelled":
        data = await _engine.cancel_loop(loop_id)
        if data is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "data": None, "error": "Loop not found"},
            )
        return {"ok": True, "data": data, "error": None}
    # 其他状态更新暂不支持
    raise HTTPException(
        status_code=400,
        detail={
            "ok": False,
            "data": None,
            "error": "Only status='cancelled' is supported",
        },
    )


@router.delete("/{loop_id}")
async def delete_loop(loop_id: int):
    """删除循环任务"""
    deleted = await _engine.delete_loop(loop_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "Loop not found"},
        )
    return {"ok": True, "data": {"id": loop_id, "deleted": True}, "error": None}
