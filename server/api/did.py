"""DID 去中心化身份 + 敏感信息脱敏 API(Phase 8C)

端点总览:
- DID: GET /did, POST /did/create, POST /did/sign, POST /did/verify,
        GET /did/list, GET /did/{did_id}, DELETE /did/{did_id},
        POST /did/{did_id}/deactivate
- 脱敏: POST /did/redact, POST /did/detect, GET /did/redact/rules

路由顺序注意: 所有静态路径(/create, /sign, /verify, /list, /redact, /detect,
/redact/rules)必须在动态路径 /{did_id} 之前注册。
"""

from fastapi import APIRouter, HTTPException, Query

from ..services.did_service import did_service
from ..services.redactor import redactor
from .models import DidCreateRequest, DidSignRequest, DidVerifyRequest, RedactRequest

router = APIRouter(prefix="/did", tags=["did"])


# ===== 模块信息 =====


@router.get("")
async def get_did():
    """获取 DID 模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "did",
            "method": "did:key",
            "key_type": "Ed25519",
            "features": [
                "create_did",
                "list_dids",
                "get_did",
                "sign",
                "verify",
                "deactivate_did",
                "delete_did",
                "redact",
                "detect",
            ],
        },
        "error": None,
    }


# ===== DID 端点(静态路径在前) =====


@router.post("/create")
async def create_did(req: DidCreateRequest):
    """创建 DID(Ed25519 + did:key)"""
    try:
        data = await did_service.create_did(
            persona_id=req.persona_id, key_type=req.key_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "data": None, "error": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.post("/sign")
async def sign_did(req: DidSignRequest):
    """用 DID 的私钥对消息签名"""
    try:
        data = await did_service.sign(req.did_id, req.message)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"ok": False, "data": None, "error": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.post("/verify")
async def verify_did(req: DidVerifyRequest):
    """验证签名(无需 DB,直接从 did 解析公钥)"""
    try:
        data = await did_service.verify(req.did, req.message, req.signature)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"ok": False, "data": None, "error": str(e)})
    return {"ok": True, "data": data, "error": None}


@router.get("/list")
async def list_dids(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
):
    """列出 DID"""
    data = await did_service.list_dids(persona_id=persona_id)
    return {"ok": True, "data": data, "error": None}


# ===== 脱敏端点(静态路径,在 /{did_id} 之前) =====


@router.post("/redact")
async def redact_text(req: RedactRequest):
    """脱敏处理:对文本中的敏感信息进行替换"""
    data = redactor.redact(
        text=req.text,
        rules=req.rules,
        replacement=req.replacement,
    )
    return {"ok": True, "data": data, "error": None}


@router.post("/detect")
async def detect_sensitive(
    req: RedactRequest,
):
    """检测敏感信息(不脱敏,返回原始匹配内容)

    复用 RedactRequest 以支持 rules 过滤;replacement 字段被忽略
    """
    data = redactor.detect(text=req.text, rules=req.rules)
    return {"ok": True, "data": data, "error": None}


@router.get("/redact/rules")
async def list_redact_rules():
    """列出所有可用脱敏规则"""
    data = redactor.list_rules()
    return {"ok": True, "data": data, "error": None}


# ===== DID 端点(动态路径) =====


@router.get("/{did_id}")
async def get_did_by_id(did_id: int):
    """获取单个 DID"""
    data = await did_service.get_did(did_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "DID not found"}
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/{did_id}")
async def delete_did(did_id: int):
    """删除 DID"""
    deleted = await did_service.delete_did(did_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "DID not found"}
        )
    return {"ok": True, "data": {"id": did_id, "deleted": True}, "error": None}


@router.post("/{did_id}/deactivate")
async def deactivate_did(did_id: int):
    """停用 DID(active=False)"""
    data = await did_service.deactivate_did(did_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail={"ok": False, "data": None, "error": "DID not found"}
        )
    return {"ok": True, "data": data, "error": None}
