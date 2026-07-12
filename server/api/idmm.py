"""IDMM 三层故障保活 API (T1.2 / T1.3 / T1.9)。

提供 HTTP 接口暴露 IDMM 引擎的三层保活能力:

- POST /idmm/execute         - L1 带超时检测和指数退避重试执行
- POST /idmm/execute-fallback - L2 主 provider 失败自动切换 backup
- GET  /idmm/stagnation/{conv_id} - L3 停滞检测
- POST /idmm/sidecar          - L3 sidecar 提示注入
- GET  /idmm/switch-logs      - L2 provider 切换日志查询(可追溯)
- GET  /idmm                  - 模块信息

说明: 由于 HTTP API 无法直接接收可调用对象,L1/L2 端点接收 task_payload 并在
服务端构造执行任务。真实生产环境应通过任务调度器/队列派发具体执行器,此处
提供可工作的演示实现以满足测试和验收要求。
"""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.idmm import IDMMEngine

router = APIRouter(prefix="/idmm", tags=["idmm"])
_engine = IDMMEngine()


# ===== 请求模型 =====


class L1ExecuteRequest(BaseModel):
    """L1 重试执行请求"""

    task_payload: dict = Field({}, description="任务载荷,透传给任务执行器")
    max_retries: int = Field(3, ge=0, le=10, description="最大重试次数(不含首次)")
    base_delay: float = Field(1.0, ge=0, description="基础退避延迟(秒)")
    max_delay: float = Field(30.0, ge=0, description="最大退避延迟(秒)")
    timeout: float = Field(30.0, gt=0, description="单次执行超时(秒)")
    # 模拟控制:用于测试故障注入。fail_first=N 表示前 N 次执行失败
    fail_first: int = Field(0, ge=0, description="模拟前 N 次执行失败(测试用)")


class L2ExecuteRequest(BaseModel):
    """L2 backup 执行请求"""

    primary_provider: str = Field(..., description="主 provider 名称")
    backup_providers: list[str] = Field([], description="备份 provider 名称列表")
    task_payload: dict = Field({}, description="任务载荷")
    # 模拟控制:用于测试故障注入。failing_providers 中列出的 provider 会失败
    failing_providers: list[str] = Field([], description="模拟失败的 provider 列表(测试用)")


class SidecarInjectRequest(BaseModel):
    """sidecar 注入请求"""

    conversation: list[dict] = Field(..., description="原对话消息列表")
    hint: str = Field(..., description="注入的 sidecar 提示文本")
    conv_id: str = Field("default", description="会话 ID")


# ===== 端点 =====


@router.get("", summary="IDMM 模块信息", description="返回 IDMM 三层故障保活引擎的模块信息和端点列表")
async def module_info():
    """返回 IDMM 模块信息和可用端点"""
    return {
        "ok": True,
        "data": {
            "module": "idmm",
            "description": "IDMM 三层故障保活引擎",
            "layers": {
                "L1": "规则层 - 超时检测+指数退避重试",
                "L2": "backup model 层 - provider 健康检查+自动切换",
                "L3": "sidecar 层 - 停滞检测+提示注入",
            },
            "endpoints": [
                "POST /idmm/execute",
                "POST /idmm/execute-fallback",
                "GET /idmm/stagnation/{conv_id}",
                "POST /idmm/sidecar",
                "GET /idmm/switch-logs",
                "GET /idmm",
            ],
        },
        "error": None,
    }


@router.post("/execute", summary="L1 带重试执行", description="L1 规则层: 带超时检测和指数退避重试执行任务")
async def execute_with_l1_retry(req: L1ExecuteRequest):
    """L1 规则层执行: 超时检测 + 指数退避重试

    验收: ① 超时任务自动重试 ② 重试次数可配
    """
    # 构造可重试任务:基于 fail_first 模拟前 N 次失败
    # 真实场景应通过 task_payload 派发到具体执行器
    call_count = {"n": 0}

    async def _task():
        call_count["n"] += 1
        if call_count["n"] <= req.fail_first:
            raise TimeoutError(f"模拟超时失败(第 {call_count['n']} 次)")
        return {"executed": True, "payload": req.task_payload, "attempt": call_count["n"]}

    result = await _engine.execute_with_l1_retry(
        _task,
        max_retries=req.max_retries,
        base_delay=req.base_delay,
        max_delay=req.max_delay,
        timeout=req.timeout,
    )
    return {
        "ok": result.success,
        "data": {
            "success": result.success,
            "result": result.result,
            "attempts": [a.__dict__ for a in result.attempts],
            "total_retries": result.total_retries,
            "last_error": result.last_error,
        },
        "error": result.last_error if not result.success else None,
    }


@router.post("/execute-fallback", summary="L2 backup 执行", description="L2 backup 层: 主 provider 失败自动切换 backup")
async def execute_with_l2_fallback(req: L2ExecuteRequest):
    """L2 backup 层执行: 主 provider 失败自动切换 backup

    验收: ① 主 provider 失败后自动切换 ② 切换日志可追溯
    """
    failing = set(req.failing_providers)

    async def _task_factory(provider_name: str):
        # 模拟: failing_providers 中的 provider 会失败
        # 真实场景应使用 provider_name 调用 LLM
        if provider_name in failing:
            raise RuntimeError(f"provider '{provider_name}' 调用失败")
        return {"provider": provider_name, "executed": True, "payload": req.task_payload}

    result = await _engine.execute_with_l2_fallback(
        _task_factory,
        primary_provider=req.primary_provider,
        backup_providers=req.backup_providers,
    )
    return {
        "ok": result.success,
        "data": {
            "success": result.success,
            "result": result.result,
            "primary_used": result.primary_used,
            "backup_used": result.backup_used,
            "switched": result.switched,
            "switches": [
                {
                    "from_provider": s.from_provider,
                    "to_provider": s.to_provider,
                    "reason": s.reason,
                    "timestamp": s.timestamp,
                }
                for s in result.switches
            ],
        },
        "error": result.last_error if not result.success else None,
    }


@router.get("/stagnation/{conv_id}", summary="L3 停滞检测", description="检测指定会话是否停滞(无进展 N 轮)")
async def check_stagnation(
    conv_id: str,
    conversation: str | None = Query(None, description="对话消息列表的 JSON 字符串"),
    threshold: int = Query(3, ge=1, description="停滞阈值(连续无进展轮数)"),
):
    """L3 停滞检测: 检测会话是否停滞

    验收: ① 停滞可检测
    """
    conversation_list: list[dict] = []
    if conversation:
        try:
            parsed = json.loads(conversation)
            if not isinstance(parsed, list):
                raise ValueError("conversation 必须是 JSON 数组")
            conversation_list = parsed
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "data": None, "error": f"Invalid conversation JSON: {exc}"},
            )

    report = await _engine.check_stagnation(
        conversation_list, threshold=threshold, conv_id=conv_id
    )
    return {
        "ok": True,
        "data": {
            "conv_id": report.conv_id,
            "stagnated": report.stagnated,
            "rounds_without_progress": report.rounds_without_progress,
            "threshold": report.threshold,
            "last_hint": report.last_hint,
        },
        "error": None,
    }


@router.post("/sidecar", summary="L3 sidecar 注入", description="在对话中注入 sidecar 提示以恢复停滞的 agent")
async def inject_sidecar(req: SidecarInjectRequest):
    """L3 sidecar 注入: 在对话中注入提示恢复停滞 agent

    验收: ② sidecar 注入后 agent 恢复
    """
    new_conv = await _engine.inject_sidecar(
        req.conversation, req.hint, conv_id=req.conv_id
    )
    return {
        "ok": True,
        "data": {
            "conversation": new_conv,
            "injected": True,
            "hint": req.hint,
            "conv_id": req.conv_id,
        },
        "error": None,
    }


@router.get("/switch-logs", summary="获取 provider 切换日志", description="返回 L2 backup 层的 provider 切换日志(可追溯)")
async def get_switch_logs():
    """获取 provider 切换日志(可追溯)"""
    logs = _engine.get_switch_logs()
    return {"ok": True, "data": logs, "error": None}
