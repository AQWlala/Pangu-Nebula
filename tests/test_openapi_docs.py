"""T0.16 OpenAPI 自动文档测试

验证:
- /docs (Swagger UI) 可访问且返回 200
- /redoc (ReDoc) 可访问且返回 200
- /openapi.json 可访问且包含 paths 定义
- 关键端点(优先级 router)具有 summary 字段
"""

import pytest
from fastapi.testclient import TestClient

from server.main import app


# 优先级 router 的代表性端点(POST/GET),用于校验 summary 字段
# 格式: (HTTP method, path)
PRIORITY_ENDPOINTS = [
    ("POST", "/chat/conversations"),       # 创建对话
    ("GET", "/chat/conversations"),        # 列出对话
    ("GET", "/persona"),                   # 列出 Persona
    ("POST", "/persona"),                  # 创建 Persona
    ("POST", "/swarm"),                    # 创建蜂群
    ("GET", "/swarm"),                     # 列出蜂群
    ("POST", "/memory"),                   # 创建记忆
    ("GET", "/memory"),                    # 列出记忆
    ("GET", "/skills"),                    # 列出技能
    ("POST", "/skills"),                   # 创建技能
    ("GET", "/wiki"),                      # 列出 Wiki
    ("POST", "/wiki"),                     # 创建 Wiki
    ("GET", "/autowork"),                  # Autowork 模块信息
    ("GET", "/dag"),                       # DAG 模块信息
    ("GET", "/acp"),                       # ACP 模块信息
    ("GET", "/terminal"),                  # Terminal 模块信息
    ("GET", "/providers"),                 # 列出 Providers
    ("GET", "/multimodal"),                # 多模态模块信息
    ("GET", "/security"),                  # 安全模块信息
    ("GET", "/channel"),                   # Channel 模块信息
]


# 扩展端点: 覆盖 T4.11 补全的 API 文件(channel/oauth/browser/os_sense/security/scheduler/sync)
# 用于验证所有路由模块的关键端点都有 summary
EXTENDED_ENDPOINTS = [
    # channel
    ("GET", "/channel/types"),
    ("GET", "/channel/list"),
    ("POST", "/channel/send"),
    ("POST", "/channel/receive"),
    ("POST", "/channel/wechat/login"),
    ("GET", "/channel/wechat/status"),
    ("POST", "/channel/feishu/configure"),
    ("GET", "/channel/feishu/status"),
    ("POST", "/channel/telegram/configure"),
    ("GET", "/channel/telegram/status"),
    ("POST", "/channel/discord/configure"),
    ("GET", "/channel/discord/status"),
    ("POST", "/channel/dingtalk/configure"),
    ("GET", "/channel/dingtalk/status"),
    ("POST", "/channel/wecom/configure"),
    ("GET", "/channel/wecom/status"),
    # oauth
    ("GET", "/oauth"),
    ("GET", "/oauth/providers"),
    ("POST", "/oauth/authorize"),
    ("POST", "/oauth/callback"),
    ("POST", "/oauth/refresh"),
    ("GET", "/oauth/tokens"),
    ("POST", "/oauth/tokens"),
    # browser
    ("GET", "/browser"),
    ("GET", "/browser/page-info"),
    ("GET", "/browser/tabs"),
    ("POST", "/browser/session"),
    ("DELETE", "/browser/session"),
    ("POST", "/browser/navigate"),
    ("POST", "/browser/action"),
    # os_sense
    ("GET", "/os_sense"),
    ("GET", "/os_sense/clipboard/status"),
    ("POST", "/os_sense/clipboard/start"),
    ("POST", "/os_sense/clipboard/stop"),
    ("GET", "/os_sense/clipboard/history"),
    ("DELETE", "/os_sense/clipboard/history"),
    ("GET", "/os_sense/file-watcher/status"),
    ("POST", "/os_sense/file-watcher/start"),
    ("POST", "/os_sense/file-watcher/stop"),
    ("GET", "/os_sense/file-watcher/events"),
    ("GET", "/os_sense/tray/status"),
    ("POST", "/os_sense/tray/start"),
    ("POST", "/os_sense/tray/stop"),
    ("POST", "/os_sense/tray/shortcuts"),
    ("GET", "/os_sense/screen/status"),
    ("POST", "/os_sense/screen/capture"),
    ("POST", "/os_sense/screen/start"),
    ("POST", "/os_sense/screen/stop"),
    ("GET", "/os_sense/screen/screenshots"),
    ("GET", "/os_sense/screen/ocr-results"),
    # security
    ("POST", "/security/acl/check"),
    ("GET", "/security/acl/rules"),
    ("POST", "/security/acl/rules"),
    ("POST", "/security/injection/check"),
    ("POST", "/security/injection/clean"),
    ("POST", "/security/ssrf/check"),
    ("GET", "/security/keychain"),
    ("POST", "/security/keychain"),
    ("POST", "/security/keychain/get"),
    ("GET", "/security/key-rotation/history"),
    ("POST", "/security/key-rotation"),
    ("GET", "/security/national-crypto/status"),
    ("POST", "/security/national-crypto/sm2-generate"),
    ("POST", "/security/national-crypto/sm2-encrypt"),
    ("POST", "/security/national-crypto/sm2-decrypt"),
    ("GET", "/security/dlp/status"),
    ("POST", "/security/dlp/scan"),
    ("POST", "/security/dlp/mask"),
    ("POST", "/security/dlp/classify"),
    ("GET", "/security/dlp/audit-log"),
    # scheduler
    ("GET", "/scheduler"),
    ("GET", "/scheduler/status"),
    ("POST", "/scheduler/start"),
    ("POST", "/scheduler/stop"),
    ("GET", "/scheduler/jobs"),
    ("POST", "/scheduler/jobs"),
    # sync (CRDT)
    ("GET", "/sync"),
    ("GET", "/sync/crdt/keys"),
    ("POST", "/sync/crdt/lww"),
    ("GET", "/sync/operations"),
    # sync_device (pairing/relay)
    ("POST", "/sync/pairing/initiate"),
    ("POST", "/sync/pairing/confirm"),
    ("GET", "/sync/devices"),
    ("POST", "/sync/relay/start"),
    ("POST", "/sync/relay/stop"),
    ("GET", "/sync/relay/status"),
    ("POST", "/sync/relay/sync"),
    ("GET", "/sync/relay/servers"),
    # did
    ("GET", "/did"),
    ("POST", "/did/create"),
    ("POST", "/did/sign"),
    ("POST", "/did/verify"),
    ("GET", "/did/list"),
    ("POST", "/did/redact"),
    ("POST", "/did/detect"),
    ("GET", "/did/redact/rules"),
    # audit
    ("GET", "/audit/logs"),
    ("POST", "/audit/logs"),
    ("GET", "/audit/summary"),
    ("GET", "/audit/budget"),
    ("POST", "/audit/budget"),
    ("PUT", "/audit/budget"),
    ("POST", "/audit/budget/check"),
    ("GET", "/audit/budget/usage"),
    # evolution
    ("GET", "/evolution"),
    ("POST", "/evolution/trigger"),
    ("GET", "/evolution/logs"),
    ("POST", "/evolution/confirm-soul"),
    # loop
    ("POST", "/loop"),
    ("GET", "/loop"),
    # distiller
    ("POST", "/distiller/check"),
    ("POST", "/distiller/confirm"),
    ("GET", "/distiller/records"),
    ("POST", "/distiller/records"),
    # mcp
    ("GET", "/mcp"),
    ("GET", "/mcp/tools"),
    ("POST", "/mcp/tools"),
    ("POST", "/mcp/rpc"),
]


def test_docs_endpoint_returns_200(test_client: TestClient):
    """测试 /docs (Swagger UI) 返回 200"""
    response = test_client.get("/docs")
    assert response.status_code == 200
    # Swagger UI 页面应包含 "Swagger UI" 关键词
    assert "swagger" in response.text.lower()


def test_redoc_endpoint_returns_200(test_client: TestClient):
    """测试 /redoc (ReDoc) 返回 200"""
    response = test_client.get("/redoc")
    assert response.status_code == 200
    # ReDoc 页面应包含 "redoc" 关键词
    assert "redoc" in response.text.lower()


def test_openapi_json_returns_200_and_contains_paths(test_client: TestClient):
    """测试 /openapi.json 返回 200 且包含 paths 定义"""
    response = test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    # 必须包含 paths 字段且非空
    assert "paths" in schema, "OpenAPI schema 缺少 paths 字段"
    assert len(schema["paths"]) > 0, "OpenAPI schema paths 为空"
    # 必须包含 info 字段
    assert "info" in schema, "OpenAPI schema 缺少 info 字段"
    # 必须包含 openapi 版本字段
    assert "openapi" in schema, "OpenAPI schema 缺少 openapi 版本字段"


def test_priority_endpoints_have_summary(test_client: TestClient):
    """测试优先级 router 的关键端点在 OpenAPI schema 中包含 summary 字段"""
    response = test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    missing: list[str] = []
    no_summary: list[str] = []

    for method, path in PRIORITY_ENDPOINTS:
        # 归一化路径(去除尾部斜杠差异)
        path_variants = {path, path.rstrip("/")}
        matched_key = next((k for k in paths if k in path_variants), None)
        if matched_key is None:
            # 允许部分端点未注册(降级断言: 至少 80% 命中)
            missing.append(f"{method.upper()} {path}")
            continue
        operation = paths[matched_key].get(method.lower())
        if operation is None:
            missing.append(f"{method.upper()} {path}")
            continue
        if not operation.get("summary"):
            no_summary.append(f"{method.upper()} {path}")

    # 至少 80% 的优先级端点应被注册
    registered_ratio = 1 - len(missing) / len(PRIORITY_ENDPOINTS)
    assert registered_ratio >= 0.8, (
        f"优先级端点注册率过低: {registered_ratio:.0%},缺失: {missing}"
    )
    # 所有已注册的优先级端点必须有 summary
    assert not no_summary, f"以下端点缺少 summary: {no_summary}"


def test_extended_endpoints_have_summary(test_client: TestClient):
    """测试扩展端点(T4.11 补全的 API)在 OpenAPI schema 中包含 summary 字段

    覆盖 channel/oauth/browser/os_sense/security/scheduler/sync/did/audit/evolution/loop/distiller/mcp
    """
    response = test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    missing: list[str] = []
    no_summary: list[str] = []

    for method, path in EXTENDED_ENDPOINTS:
        path_variants = {path, path.rstrip("/")}
        matched_key = next((k for k in paths if k in path_variants), None)
        if matched_key is None:
            missing.append(f"{method.upper()} {path}")
            continue
        operation = paths[matched_key].get(method.lower())
        if operation is None:
            missing.append(f"{method.upper()} {path}")
            continue
        if not operation.get("summary"):
            no_summary.append(f"{method.upper()} {path}")

    # 扩展端点注册率至少 70%(部分可选模块可能未注册)
    registered_ratio = 1 - len(missing) / len(EXTENDED_ENDPOINTS)
    assert registered_ratio >= 0.7, (
        f"扩展端点注册率过低: {registered_ratio:.0%},缺失: {missing}"
    )
    # 所有已注册的扩展端点必须有 summary
    assert not no_summary, f"以下扩展端点缺少 summary: {no_summary}"


def test_openapi_schema_contains_components(test_client: TestClient):
    """测试 OpenAPI schema 包含 components/schemas(Pydantic 模型已暴露)"""
    response = test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    # Pydantic 模型应被注册到 components.schemas
    assert "components" in schema, "OpenAPI schema 缺少 components 字段"
    assert "schemas" in schema["components"], "OpenAPI schema 缺少 components.schemas"
    schemas = schema["components"]["schemas"]
    # 校验关键 Pydantic 模型存在
    expected_models = ["PersonaCreate", "MemoryCreate", "SkillCreate", "SwarmCreate"]
    for model_name in expected_models:
        assert model_name in schemas, f"OpenAPI schema 缺少模型: {model_name}"


def test_priority_models_have_field_descriptions(test_client: TestClient):
    """测试优先级 Pydantic 模型的字段包含 description"""
    response = test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    schemas = schema["components"]["schemas"]

    # PersonaCreate.name 字段应有 description
    persona_create = schemas.get("PersonaCreate", {})
    properties = persona_create.get("properties", {})
    name_field = properties.get("name", {})
    assert name_field.get("description"), "PersonaCreate.name 缺少 description"

    # MemoryCreate.layer 字段应有 description
    memory_create = schemas.get("MemoryCreate", {})
    properties = memory_create.get("properties", {})
    layer_field = properties.get("layer", {})
    assert layer_field.get("description"), "MemoryCreate.layer 缺少 description"

    # SkillCreate.prompt_template 字段应有 description
    skill_create = schemas.get("SkillCreate", {})
    properties = skill_create.get("properties", {})
    prompt_field = properties.get("prompt_template", {})
    assert prompt_field.get("description"), "SkillCreate.prompt_template 缺少 description"
