"""Phase 9B: 设备配对 + 中继同步 Pydantic 模型

独立于 models.py,避免与 Phase 9A(CRDT/E2EE)修改冲突。
"""

from pydantic import BaseModel


# ===== Phase 9B: 设备配对 + 中继 =====


class PairingInitiateRequest(BaseModel):
    """发起配对请求"""

    device_name: str = "default"


class PairingConfirmRequest(BaseModel):
    """确认配对请求"""

    pairing_code: str
    peer_public_key: str
    peer_device_name: str = "peer"


class PairingStatusRequest(BaseModel):
    """查询配对状态请求"""

    pairing_code: str


class RelayStartRequest(BaseModel):
    """启动中继请求"""

    url: str
    device_id: str


class RelaySyncRequest(BaseModel):
    """手动触发同步请求"""

    device_id: str | None = None  # 指定设备,空则全部
