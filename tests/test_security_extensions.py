"""Tests for security compliance extensions — 国密算法 + DLP 引擎。"""

import base64

from fastapi.testclient import TestClient

from server.main import app
from server.services.national_crypto import NationalCrypto
from server.services.dlp_engine import (
    DataClassification,
    DLPEngine,
    DLPRule,
    SensitiveType,
)


# =====================================================================
# 1. NationalCrypto 可实例化
# =====================================================================


def test_national_crypto_instantiable():
    """NationalCrypto 可实例化,且 get_status 返回结构正确"""
    crypto = NationalCrypto()
    status = crypto.get_status()
    assert "available" in status
    assert "algorithms" in status
    assert "mode" in status
    assert status["mode"] in ("real", "mock")
    # 即使不可用,也不应抛异常
    assert isinstance(status["available"], bool)


# =====================================================================
# 2. SM2 生成密钥对 (mock)
# =====================================================================


def test_sm2_generate_keypair():
    """SM2 生成密钥对返回 (private, public)"""
    crypto = NationalCrypto()
    private_key, public_key = crypto.sm2_generate_keypair()
    assert isinstance(private_key, str)
    assert isinstance(public_key, str)
    assert len(private_key) > 0
    assert len(public_key) > 0
    # mock 模式下应返回固定占位值
    if crypto.get_status()["mode"] == "mock":
        assert private_key == "mock_sm2_private_key"
        assert public_key == "mock_sm2_public_key"


# =====================================================================
# 3. SM4 加密/解密 (mock)
# =====================================================================


def test_sm4_encrypt_decrypt_mock():
    """SM4 加密/解密在 mock 模式下返回占位数据"""
    crypto = NationalCrypto()
    key = b"0123456789abcdef"  # 16 字节 SM4 密钥
    data = b"hello world"
    encrypted = crypto.sm4_encrypt(key, data)
    assert isinstance(encrypted, bytes)
    assert len(encrypted) > 0

    decrypted = crypto.sm4_decrypt(key, encrypted)
    assert isinstance(decrypted, bytes)
    assert len(decrypted) > 0

    # mock 模式下的固定格式
    if crypto.get_status()["mode"] == "mock":
        assert encrypted == b"mock_sm4_encrypted:" + data[:10]
        assert decrypted == b"mock_sm4_decrypted_data"


# =====================================================================
# 3b. SM2 加密/解密 (mock) — 额外覆盖
# =====================================================================


def test_sm2_encrypt_decrypt_mock():
    """SM2 加密/解密在 mock 模式下返回占位数据"""
    crypto = NationalCrypto()
    public_key = "mock_sm2_public_key"
    private_key = "mock_sm2_private_key"
    data = b"sensitive payload"
    encrypted = crypto.sm2_encrypt(public_key, data)
    assert isinstance(encrypted, bytes)
    assert encrypted  # 非空

    decrypted = crypto.sm2_decrypt(private_key, encrypted)
    assert isinstance(decrypted, bytes)
    assert decrypted  # 非空

    if crypto.get_status()["mode"] == "mock":
        assert encrypted == b"mock_sm2_encrypted:" + data[:10]
        assert decrypted == b"mock_sm2_decrypted_data"


# =====================================================================
# 4. DLP 扫描身份证号
# =====================================================================


def test_dlp_scan_id_card():
    """DLP 扫描身份证号"""
    engine = DLPEngine()
    text = "我的身份证号是 11010119900307783X 请妥善保管"
    findings = engine.scan(text)
    id_card_findings = [f for f in findings if f["type"] == "id_card"]
    assert len(id_card_findings) == 1
    finding = id_card_findings[0]
    assert finding["match"] == "11010119900307783X"
    assert finding["position"][0] >= 0
    assert finding["classification"] == DataClassification.CONFIDENTIAL.value


# =====================================================================
# 5. DLP 扫描手机号
# =====================================================================


def test_dlp_scan_phone():
    """DLP 扫描手机号"""
    engine = DLPEngine()
    text = "联系我: 13812345678, 或者 19987654321"
    findings = engine.scan(text)
    phone_findings = [f for f in findings if f["type"] == "phone"]
    assert len(phone_findings) == 2
    matches = {f["match"] for f in phone_findings}
    assert "13812345678" in matches
    assert "19987654321" in matches
    for f in phone_findings:
        assert f["classification"] == DataClassification.INTERNAL.value


# =====================================================================
# 6. DLP 脱敏处理 (partial 策略)
# =====================================================================


def test_dlp_mask_partial_strategy():
    """DLP 脱敏处理 - partial 策略保留前几位"""
    # 仅用一条规则避免与 BANK_CARD 的 16-19 位数字规则冲突
    engine = DLPEngine(
        rules=[
            DLPRule(
                SensitiveType.PHONE,
                r"1[3-9]\d{9}",
                "partial",
                DataClassification.INTERNAL,
            )
        ]
    )
    text = "联系我: 13812345678"
    masked = engine.mask(text)
    # partial: 保留前 3 位,后面用 * 替换
    assert "138" in masked
    assert "*" in masked
    assert "12345678" not in masked  # 后 8 位不应可见
    assert len(masked) == len(text)  # 长度保持


# =====================================================================
# 6b. DLP 脱敏 full / hash 策略
# =====================================================================


def test_dlp_mask_full_and_hash_strategy():
    """DLP full 与 hash 脱敏策略"""
    full_engine = DLPEngine(
        rules=[
            DLPRule(
                SensitiveType.PHONE,
                r"1[3-9]\d{9}",
                "full",
                DataClassification.INTERNAL,
            )
        ]
    )
    text = "电话 13812345678"
    masked_full = full_engine.mask(text)
    assert "13812345678" not in masked_full
    assert "*" in masked_full

    hash_engine = DLPEngine(
        rules=[
            DLPRule(
                SensitiveType.PHONE,
                r"1[3-9]\d{9}",
                "hash",
                DataClassification.INTERNAL,
            )
        ]
    )
    masked_hash = hash_engine.mask(text)
    assert "13812345678" not in masked_hash
    # hash 策略下,被替换为 16 位 hex
    assert any(c in "0123456789abcdef" for c in masked_hash)


# =====================================================================
# 7. DLP 分类文档
# =====================================================================


def test_dlp_classify():
    """DLP 文档分类 - 含敏感信息时返回非 public 级别"""
    engine = DLPEngine()

    # 公开文本
    public_text = "今天的天气真好,适合户外活动。"
    assert engine.classify(public_text) == DataClassification.PUBLIC

    # 含手机号 -> INTERNAL
    internal_text = "联系我: 13812345678"
    assert engine.classify(internal_text) == DataClassification.INTERNAL

    # 含密码 -> TOP_SECRET (最高级)
    secret_text = "password=s3cret_password_value_here"
    classification = engine.classify(secret_text)
    assert classification == DataClassification.TOP_SECRET


# =====================================================================
# 8. DLP 审计日志记录
# =====================================================================


def test_dlp_audit_log():
    """DLP 脱敏操作会写入审计日志"""
    engine = DLPEngine(
        rules=[
            DLPRule(
                SensitiveType.PHONE,
                r"1[3-9]\d{9}",
                "partial",
                DataClassification.INTERNAL,
            )
        ]
    )
    # 初始为空
    assert engine.get_audit_log() == []

    # 触发一次脱敏
    engine.mask("电话 13812345678")
    log = engine.get_audit_log()
    assert len(log) == 1
    entry = log[0]
    assert entry["action"] == "mask"
    assert entry["total_redactions"] == 1
    assert "phone" in entry["affected_types"]
    assert "timestamp" in entry

    # 再触发一次
    engine.mask("另一个 13912345678")
    log = engine.get_audit_log()
    assert len(log) == 2

    # limit 参数生效
    limited = engine.get_audit_log(limit=1)
    assert len(limited) == 1


# =====================================================================
# 9. DLP add_rule 添加自定义规则
# =====================================================================


def test_dlp_add_custom_rule():
    """DLP 可添加自定义规则并立即生效"""
    engine = DLPEngine()
    initial_count = len(engine.get_status()["rule_types"])
    engine.add_rule(
        DLPRule(
            SensitiveType.API_KEY,
            r"custom_token_[a-z0-9]{20}",
            "full",
            DataClassification.TOP_SECRET,
        )
    )
    assert engine.get_status()["rules_count"] == initial_count + 1
    text = "我的 token 是 custom_token_abcdef1234567890abcd"
    findings = engine.scan(text)
    api_key_findings = [f for f in findings if f["type"] == "api_key"]
    assert any("custom_token_" in f["match"] for f in api_key_findings)


# =====================================================================
# 10. API 端点: 国密 status
# =====================================================================


def test_api_national_crypto_status(test_client: TestClient):
    """GET /security/national-crypto/status 返回结构正确"""
    response = test_client.get("/security/national-crypto/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert "available" in body["data"]
    assert "mode" in body["data"]


# =====================================================================
# 11. API 端点: SM2 generate
# =====================================================================


def test_api_sm2_generate(test_client: TestClient):
    """POST /security/national-crypto/sm2-generate 返回密钥对"""
    response = test_client.post("/security/national-crypto/sm2-generate")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert "private_key" in data
    assert "public_key" in data
    assert data["private_key"]
    assert data["public_key"]


# =====================================================================
# 12. API 端点: SM4 encrypt/decrypt
# =====================================================================


def test_api_sm4_encrypt_decrypt(test_client: TestClient):
    """POST SM4 加密/解密端点能完成往返(mock 模式下解密返回占位数据)"""
    key_b64 = base64.b64encode(b"0123456789abcdef").decode("ascii")
    plaintext = "hello world"

    # 加密
    enc_response = test_client.post(
        "/security/national-crypto/sm4-encrypt",
        json={"key": key_b64, "data": plaintext},
    )
    assert enc_response.status_code == 200
    enc_body = enc_response.json()
    assert enc_body["ok"] is True
    ciphertext = enc_body["data"]["ciphertext"]
    assert ciphertext

    # 解密
    dec_response = test_client.post(
        "/security/national-crypto/sm4-decrypt",
        json={"key": key_b64, "data": ciphertext},
    )
    assert dec_response.status_code == 200
    dec_body = dec_response.json()
    assert dec_body["ok"] is True
    assert "plaintext" in dec_body["data"]


# =====================================================================
# 13. API 端点: DLP scan
# =====================================================================


def test_api_dlp_scan(test_client: TestClient):
    """POST /security/dlp/scan 能识别手机号"""
    response = test_client.post(
        "/security/dlp/scan",
        json={"text": "电话 13812345678"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    findings = body["data"]["findings"]
    phone_findings = [f for f in findings if f["type"] == "phone"]
    assert len(phone_findings) == 1
    assert phone_findings[0]["match"] == "13812345678"


# =====================================================================
# 14. API 端点: DLP status
# =====================================================================


def test_api_dlp_status(test_client: TestClient):
    """GET /security/dlp/status 返回引擎状态"""
    response = test_client.get("/security/dlp/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "rules_count" in body["data"]
    assert "rule_types" in body["data"]


# =====================================================================
# 15. API 端点: DLP audit-log
# =====================================================================


def test_api_dlp_audit_log(test_client: TestClient):
    """GET /security/dlp/audit-log 返回审计日志列表"""
    # 先触发一次脱敏 (通过 mask 端点) 确保日志非空
    test_client.post("/security/dlp/mask", json={"text": "电话 13812345678"})

    response = test_client.get("/security/dlp/audit-log")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "entries" in body["data"]
    assert "count" in body["data"]
    assert body["data"]["count"] >= 1
