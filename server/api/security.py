"""安全防护 API (Phase 8A) + 安全合规扩展 (国密/DLP)

端点总览:
- GET  /security                                 - 安全模块信息
- POST /security/acl/check                        - 权限检查(静态路由在前)
- GET  /security/acl/rules                        - 列出 ACL 规则
- POST /security/acl/rules                        - 创建 ACL 规则
- GET  /security/acl/rules/{rule_id}              - 获取单条规则
- PUT  /security/acl/rules/{rule_id}              - 更新规则
- DELETE /security/acl/rules/{rule_id}            - 删除规则
- POST /security/injection/check                  - 注入检查
- POST /security/injection/clean                  - 输入清洗
- POST /security/ssrf/check                       - SSRF 检查
- GET  /security/keychain                         - 列出密钥名称
- POST /security/keychain                         - 存储密钥
- POST /security/keychain/get                     - 获取密钥(静态路由在前)
- DELETE /security/keychain/{key}                 - 删除密钥
- GET  /security/key-rotation/history             - 密钥历史(静态路由在前)
- POST /security/key-rotation                     - 密钥轮换
- GET  /security/national-crypto/status           - 国密支持状态
- POST /security/national-crypto/sm2-generate     - SM2 生成密钥对
- POST /security/national-crypto/sm2-encrypt      - SM2 加密
- POST /security/national-crypto/sm2-decrypt      - SM2 解密
- GET  /security/dlp/status                       - DLP 引擎状态
- POST /security/dlp/scan                         - 扫描敏感数据
- POST /security/dlp/mask                         - 脱敏处理
- POST /security/dlp/classify                     - 分类文档
- GET  /security/dlp/audit-log                    - DLP 审计日志
"""

import base64

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db.engine import async_session
from ..services.acl_service import acl_service
from ..services.injection_guard import injection_guard
from ..services.ssrf_guard import ssrf_guard
from ..services.keychain import keychain
from ..services.key_rotation import key_rotation_service
from ..services.national_crypto import national_crypto
from ..services.dlp_engine import dlp_engine
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


# ===== 国密算法请求模型 =====


class SM2EncryptRequest(BaseModel):
    """SM2 加密请求"""

    public_key: str
    data: str  # 明文(UTF-8),后端编码为 bytes 后加密


class SM2DecryptRequest(BaseModel):
    """SM2 解密请求"""

    private_key: str
    data: str  # base64 编码的密文


class SM4EncryptRequest(BaseModel):
    """SM4 加密请求"""

    key: str  # base64 编码的密钥
    data: str  # 明文(UTF-8)


class SM4DecryptRequest(BaseModel):
    """SM4 解密请求"""

    key: str  # base64 编码的密钥
    data: str  # base64 编码的密文


# ===== DLP 请求模型 =====


class DLPScanRequest(BaseModel):
    """DLP 扫描请求"""

    text: str


class DLPMaskRequest(BaseModel):
    """DLP 脱敏请求"""

    text: str

router = APIRouter(prefix="/security", tags=["security"])


# ===== 安全模块信息 =====


@router.get("", summary="安全模块信息", description="获取安全模块信息,包括 ACL、注入防护、SSRF、密钥管理、国密、DLP 等功能状态")
async def get_security_info():
    """获取安全模块信息"""
    return {
        "ok": True,
        "data": {
            "module": "security",
            "phase": "8A+compliance",
            "features": [
                "acl",
                "injection_guard",
                "ssrf_guard",
                "keychain",
                "key_rotation",
                "national_crypto",
                "dlp_engine",
            ],
            "keychain_available": keychain.is_available(),
            "national_crypto": national_crypto.get_status(),
            "dlp": dlp_engine.get_status(),
        },
        "error": None,
    }


# ===== ACL 权限检查(静态路由,必须在 /acl/rules/{rule_id} 之前) =====


@router.post("/acl/check", summary="ACL 权限检查", description="检查指定 Persona 对资源的操作权限")
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


@router.get("/acl/rules", summary="列出 ACL 规则", description="列出 ACL 规则,可按 Persona 过滤")
async def list_acl_rules(
    persona_id: int | None = Query(None, description="按 Persona 过滤"),
):
    """列出 ACL 规则"""
    async with async_session() as session:
        data = await acl_service.list_rules(session, persona_id=persona_id)
    return {"ok": True, "data": data, "error": None}


@router.post("/acl/rules", summary="创建 ACL 规则", description="创建新的 ACL 规则,指定 Persona、资源、动作和效果(allow/deny)")
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


@router.post("/injection/check", summary="注入检查", description="检查文本是否包含 Prompt 注入、代码注入、URL 注入等攻击")
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


@router.post("/ssrf/check", summary="SSRF 检查", description="检查 URL 是否存在 SSRF 风险(内网 IP、敏感协议等)")
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


# ===== 国密算法 (SM2/SM4) =====


@router.get("/national-crypto/status")
async def get_national_crypto_status():
    """获取国密算法支持状态"""
    return {"ok": True, "data": national_crypto.get_status(), "error": None}


@router.post("/national-crypto/sm2-generate")
async def sm2_generate_keypair():
    """SM2 生成密钥对"""
    private_key, public_key = national_crypto.sm2_generate_keypair()
    return {
        "ok": True,
        "data": {
            "private_key": private_key,
            "public_key": public_key,
            "mode": national_crypto.get_status()["mode"],
        },
        "error": None,
    }


@router.post("/national-crypto/sm2-encrypt")
async def sm2_encrypt(req: SM2EncryptRequest):
    """SM2 加密

    请求: {"public_key": "...", "data": "plaintext"}
    返回: {"ciphertext": "base64..."}
    """
    try:
        encrypted_bytes = national_crypto.sm2_encrypt(
            req.public_key, req.data.encode("utf-8")
        )
        ciphertext = base64.b64encode(encrypted_bytes).decode("ascii")
    except Exception as e:
        return {"ok": False, "data": None, "error": f"SM2 encrypt failed: {e}"}
    return {
        "ok": True,
        "data": {
            "ciphertext": ciphertext,
            "mode": national_crypto.get_status()["mode"],
        },
        "error": None,
    }


@router.post("/national-crypto/sm2-decrypt")
async def sm2_decrypt(req: SM2DecryptRequest):
    """SM2 解密

    请求: {"private_key": "...", "data": "base64..."}
    返回: {"plaintext": "..."}
    """
    try:
        encrypted_bytes = base64.b64decode(req.data)
        decrypted_bytes = national_crypto.sm2_decrypt(req.private_key, encrypted_bytes)
        plaintext = decrypted_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "data": None, "error": f"SM2 decrypt failed: {e}"}
    return {
        "ok": True,
        "data": {
            "plaintext": plaintext,
            "mode": national_crypto.get_status()["mode"],
        },
        "error": None,
    }


@router.post("/national-crypto/sm4-encrypt")
async def sm4_encrypt(req: SM4EncryptRequest):
    """SM4 对称加密

    请求: {"key": "base64...", "data": "plaintext"}
    返回: {"ciphertext": "base64..."}
    """
    try:
        key_bytes = base64.b64decode(req.key)
        encrypted_bytes = national_crypto.sm4_encrypt(
            key_bytes, req.data.encode("utf-8")
        )
        ciphertext = base64.b64encode(encrypted_bytes).decode("ascii")
    except Exception as e:
        return {"ok": False, "data": None, "error": f"SM4 encrypt failed: {e}"}
    return {
        "ok": True,
        "data": {
            "ciphertext": ciphertext,
            "mode": national_crypto.get_status()["mode"],
        },
        "error": None,
    }


@router.post("/national-crypto/sm4-decrypt")
async def sm4_decrypt(req: SM4DecryptRequest):
    """SM4 对称解密

    请求: {"key": "base64...", "data": "base64..."}
    返回: {"plaintext": "..."}
    """
    try:
        key_bytes = base64.b64decode(req.key)
        encrypted_bytes = base64.b64decode(req.data)
        decrypted_bytes = national_crypto.sm4_decrypt(key_bytes, encrypted_bytes)
        plaintext = decrypted_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "data": None, "error": f"SM4 decrypt failed: {e}"}
    return {
        "ok": True,
        "data": {
            "plaintext": plaintext,
            "mode": national_crypto.get_status()["mode"],
        },
        "error": None,
    }


# ===== DLP 数据防泄漏引擎 =====


@router.get("/dlp/status")
async def get_dlp_status():
    """获取 DLP 引擎状态"""
    return {"ok": True, "data": dlp_engine.get_status(), "error": None}


@router.post("/dlp/scan")
async def dlp_scan(req: DLPScanRequest):
    """扫描文本中的敏感数据

    返回 findings: [{type, match, position, classification}]
    """
    findings = dlp_engine.scan(req.text)
    return {
        "ok": True,
        "data": {
            "findings": findings,
            "total": len(findings),
            "input_length": len(req.text),
        },
        "error": None,
    }


@router.post("/dlp/mask")
async def dlp_mask(req: DLPMaskRequest):
    """脱敏处理

    根据 DLP 规则的 mask_strategy 自动选择策略:
    - partial: 保留前几位
    - full: 全部 *
    - hash: SHA256 前 16 位
    """
    masked_text = dlp_engine.mask(req.text)
    return {
        "ok": True,
        "data": {
            "masked_text": masked_text,
            "input_length": len(req.text),
            "output_length": len(masked_text),
        },
        "error": None,
    }


@router.post("/dlp/classify")
async def dlp_classify(req: DLPScanRequest):
    """分类文档(返回最高敏感级别)"""
    classification = dlp_engine.classify(req.text)
    findings = dlp_engine.scan(req.text)
    # 统计每个分级命中数
    summary: dict[str, int] = {}
    for f in findings:
        summary[f["classification"]] = summary.get(f["classification"], 0) + 1
    return {
        "ok": True,
        "data": {
            "classification": classification.value,
            "findings_count": len(findings),
            "classification_summary": summary,
        },
        "error": None,
    }


@router.get("/dlp/audit-log")
async def get_dlp_audit_log(limit: int = Query(100, ge=1, le=1000)):
    """获取 DLP 脱敏审计日志"""
    log = dlp_engine.get_audit_log(limit=limit)
    return {
        "ok": True,
        "data": {"entries": log, "count": len(log)},
        "error": None,
    }
