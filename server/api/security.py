"""安全防护 API (Phase 8A)

端点总览:
- GET  /security                     - 安全模块信息
- POST /security/acl/check            - 权限检查(静态路由在前)
- GET  /security/acl/rules            - 列出 ACL 规则
- POST /security/acl/rules            - 创建 ACL 规则
- GET  /security/acl/rules/{rule_id}  - 获取单条规则
- PUT  /security/acl/rules/{rule_id}  - 更新规则
- DELETE /security/acl/rules/{rule_id} - 删除规则
- POST /security/injection/check      - 注入检查
- POST /security/injection/clean      - 输入清洗
- POST /security/ssrf/check           - SSRF 检查
- GET  /security/keychain             - 列出密钥名称
- POST /security/keychain             - 存储密钥
- POST /security/keychain/get         - 获取密钥(静态路由在前)
- DELETE /security/keychain/{key}     - 删除密钥
- GET  /security/key-rotation/history - 密钥历史(静态路由在前)
- POST /security/key-rotation         - 密钥轮换
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db.engine import async_session
from ..services.acl_service import acl_service
from ..services.injection_guard import injection_guard
from ..services.ssrf_guard import ssrf_guard
from ..services.keychain import keychain
from ..services.key_rotation import key_rotation_service
from .models import (
    AclCheckRequest,
    AclRuleCreate,
    AclRuleUpdate,
    InjectionCheckRequest,
    KeyRotationRequest,
    KeychainGetRequest,
    KeychainStoreRequest,
    SsrfCheckRequest,
)


class InjectionCleanRequest(BaseModel):
    """输入清洗请求"""

    text: str

router = APIRouter(prefix="/security", tags=["security"])


# ===== 安全模块信息 =====


@router.get("")
async def get_security_info():
    """获取安全模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "security",
            "phase": "8A",
            "features": [
                "acl",
                "injection_guard",
                "ssrf_guard",
                "keychain",
                "key_rotation",
            ],
            "keychain_available": keychain.is_available(),
        },
        "error": None,
    }


# ===== ACL 权限检查(静态路由,必须在 /acl/rules/{rule_id} 之前) =====


@router.post("/acl/check")
async def check_acl_permission(req: AclCheckRequest):
    """权限检查"""
    async with async_session() as session:
        data = await acl_service.check_permission(
            session,
            persona_id=req.persona_id,
            resource=req.resource,
            action=req.action,
        )
    return {"ok": True, "data": data, "error": None}


# ===== ACL 规则管理 =====


@router.get("/acl/rules")
async def list_acl_rules(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
):
    """列出 ACL 规则"""
    async with async_session() as session:
        data = await acl_service.list_rules(session, persona_id=persona_id)
    return {"ok": True, "data": data, "error": None}


@router.post("/acl/rules")
async def create_acl_rule(req: AclRuleCreate):
    """创建 ACL 规则"""
    async with async_session() as session:
        data = await acl_service.create_rule(
            session,
            persona_id=req.persona_id,
            resource=req.resource,
            action=req.action,
            effect=req.effect,
        )
    return {"ok": True, "data": data, "error": None}


@router.get("/acl/rules/{rule_id}")
async def get_acl_rule(rule_id: int):
    """获取单条规则"""
    async with async_session() as session:
        data = await acl_service.get_rule(session, rule_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "ACL rule not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.put("/acl/rules/{rule_id}")
async def update_acl_rule(rule_id: int, req: AclRuleUpdate):
    """更新规则"""
    async with async_session() as session:
        data = await acl_service.update_rule(
            session,
            rule_id,
            **req.model_dump(exclude_unset=True),
        )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "ACL rule not found"},
        )
    return {"ok": True, "data": data, "error": None}


@router.delete("/acl/rules/{rule_id}")
async def delete_acl_rule(rule_id: int):
    """删除规则"""
    async with async_session() as session:
        deleted = await acl_service.delete_rule(session, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": "ACL rule not found"},
        )
    return {"ok": True, "data": {"id": rule_id, "deleted": True}, "error": None}


# ===== 注入防护 =====


@router.post("/injection/check")
async def check_injection(req: InjectionCheckRequest):
    """注入检查"""
    data = injection_guard.check(req.text, context=req.context)
    return {"ok": True, "data": data, "error": None}


@router.post("/injection/clean")
async def clean_injection(req: InjectionCleanRequest):
    """输入清洗

    请求体: {"text": "..."}
    """
    data = {"cleaned_text": injection_guard.clean(req.text)}
    return {"ok": True, "data": data, "error": None}


# ===== SSRF 防护 =====


@router.post("/ssrf/check")
async def check_ssrf(req: SsrfCheckRequest):
    """SSRF 检查"""
    data = ssrf_guard.check(req.url, allow_internal=req.allow_internal)
    return {"ok": True, "data": data, "error": None}


# ===== 密钥管理 =====


@router.get("/keychain")
async def list_keychain_keys():
    """列出所有密钥名称(不返回值)"""
    data = await keychain.list_keys()
    return {"ok": True, "data": data, "error": None}


@router.post("/keychain")
async def store_keychain_key(req: KeychainStoreRequest):
    """存储密钥"""
    if not keychain.is_available():
        return {
            "ok": False,
            "data": None,
            "error": "cryptography 库未安装,密钥管理不可用",
        }
    async with async_session() as session:
        data = await keychain.store(
            session,
            key=req.key,
            value=req.value,
            metadata=req.metadata,
        )
    if "error" in data:
        return {"ok": False, "data": None, "error": data["error"]}
    return {"ok": True, "data": data, "error": None}


@router.post("/keychain/get")
async def get_keychain_key(req: KeychainGetRequest):
    """获取密钥(静态路由,必须在 /keychain/{key} 之前)"""
    if not keychain.is_available():
        return {
            "ok": False,
            "data": None,
            "error": "cryptography 库未安装,密钥管理不可用",
        }
    async with async_session() as session:
        data = await keychain.get(session, req.key)
    if "error" in data:
        return {"ok": False, "data": None, "error": data["error"]}
    return {"ok": True, "data": data, "error": None}


@router.delete("/keychain/{key}")
async def delete_keychain_key(key: str):
    """删除密钥"""
    async with async_session() as session:
        data = await keychain.delete(session, key)
    if not data.get("deleted"):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "data": None, "error": data.get("error", "Key not found")},
        )
    return {"ok": True, "data": data, "error": None}


# ===== 密钥轮换 =====


@router.get("/key-rotation/history")
async def get_key_rotation_history():
    """获取密钥历史(静态路由,必须在 /key-rotation 相关动态路由之前)"""
    async with async_session() as session:
        data = await key_rotation_service.get_key_history(session)
    return {"ok": True, "data": data, "error": None}


@router.post("/key-rotation")
async def rotate_keys(req: KeyRotationRequest):
    """执行密钥轮换"""
    async with async_session() as session:
        data = await key_rotation_service.rotate(session, force=req.force)
    if data.get("error"):
        return {"ok": False, "data": None, "error": data["error"]}
    return {"ok": True, "data": data, "error": None}
