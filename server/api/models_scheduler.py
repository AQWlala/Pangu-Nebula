"""调度器与健康检查相关的 Pydantic 模型(Phase 10B)"""

from pydantic import BaseModel


class SchedulerJobCreateRequest(BaseModel):
    """创建定时任务请求"""

    name: str
    cron_expr: str
    action: dict
    enabled: bool = True


class SchedulerJobUpdateRequest(BaseModel):
    """更新定时任务请求(所有字段可选)"""

    name: str | None = None
    cron_expr: str | None = None
    action: dict | None = None
    enabled: bool | None = None


class MonitorStartRequest(BaseModel):
    """启动健康监控请求"""

    interval_seconds: int = 300


class HealthStartRequest(BaseModel):
    """v2.3.0 Phase 3-D: 全局启动健康检查请求"""

    interval_seconds: int = 300


class ProviderToggleRequest(BaseModel):
    """v2.3.0 Phase 3-D: 单 Provider 启停请求"""

    enabled: bool
