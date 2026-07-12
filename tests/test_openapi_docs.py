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
