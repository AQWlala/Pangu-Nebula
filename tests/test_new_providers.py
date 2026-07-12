"""Tests for the 5 new LLM providers: deepseek, openrouter, qwen, kimi, zhipu.

Each provider should:
- Be instantiable without an API key
- Return mock responses when no API key is set
- Register itself in the provider registry
"""

import pytest

from server.providers import (
    DeepSeekProvider,
    KimiProvider,
    OpenRouterProvider,
    QwenProvider,
    ZhipuProvider,
    list_providers,
)
from server.providers.base import Message

# Map of provider name -> (class, supported_models, env_var)
NEW_PROVIDERS = {
    "deepseek": (
        DeepSeekProvider,
        ["deepseek-chat", "deepseek-reasoner"],
        "NEBULA_DEEPSEEK_API_KEY",
    ),
    "openrouter": (
        OpenRouterProvider,
        [
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash",
            "deepseek/deepseek-chat",
        ],
        "NEBULA_OPENROUTER_API_KEY",
    ),
    "qwen": (
        QwenProvider,
        ["qwen-max", "qwen-plus", "qwen-turbo"],
        "NEBULA_QWEN_API_KEY",
    ),
    "kimi": (
        KimiProvider,
        ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "NEBULA_KIMI_API_KEY",
    ),
    "zhipu": (
        ZhipuProvider,
        ["glm-4", "glm-4-flash", "glm-4v"],
        "NEBULA_ZHIPU_API_KEY",
    ),
}


# Build parametrize argument list: each entry is (name, cls, models, env_var)
_PARAM_LIST = [(name, *vals) for name, vals in NEW_PROVIDERS.items()]


@pytest.fixture(autouse=True)
def _clear_api_keys(monkeypatch):
    """Ensure no API key is set in the environment for any new provider."""
    for _, _, _, env_var in _PARAM_LIST:
        monkeypatch.delenv(env_var, raising=False)


@pytest.mark.parametrize("name,cls,models,env_var", _PARAM_LIST)
def test_provider_instantiable(name, cls, models, env_var):
    """Test 1: each provider can be instantiated without error."""
    instance = cls()
    assert instance is not None
    assert instance.api_key == ""
    assert instance.name == name


@pytest.mark.parametrize("name,cls,models,env_var", _PARAM_LIST)
def test_provider_info_returns_correct_fields(name, cls, models, env_var):
    """Test 2: info() returns correct fields including 'available'."""
    instance = cls()
    info = instance.info()
    assert info["name"] == name
    assert info["supported_models"] == models
    assert "capabilities" in info
    assert isinstance(info["capabilities"], dict)
    assert "available" in info
    assert info["available"] is False  # no API key set


@pytest.mark.parametrize("name,cls,models,env_var", _PARAM_LIST)
async def test_provider_generate_returns_mock(name, cls, models, env_var):
    """Test 3: generate() yields mock response without API key."""
    instance = cls()
    messages = [Message(role="user", content="Hello, world! This is a test.")]
    chunks = []
    async for chunk in instance.generate(messages, models[0]):
        chunks.append(chunk)
    assert len(chunks) == 1
    assert chunks[0].startswith("[mock] ")
    assert name in chunks[0]
    # mock response contains truncated user content
    assert "Hello, world!" in chunks[0]


@pytest.mark.parametrize("name,cls,models,env_var", _PARAM_LIST)
async def test_provider_embed_returns_mock_vector(name, cls, models, env_var):
    """Test 4: embed() returns a 1536-dim mock vector without API key."""
    instance = cls()
    vector = await instance.embed("some text", "any-model")
    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert all(v == 0.0 for v in vector)


@pytest.mark.parametrize("name,cls,models,env_var", _PARAM_LIST)
async def test_provider_test_connection_false_without_key(name, cls, models, env_var):
    """Test 5: test_connection() returns False without API key."""
    instance = cls()
    result = await instance.test_connection()
    assert result is False


def test_list_providers_includes_all_new_providers():
    """Test 6: list_providers() contains all 5 new providers."""
    providers = list_providers()
    names = [p["name"] for p in providers]
    for name in NEW_PROVIDERS:
        assert name in names, f"Provider '{name}' not found in registry"

    # Verify each new provider's info is correctly returned
    providers_by_name = {p["name"]: p for p in providers}
    for name, cls, models, _ in _PARAM_LIST:
        info = providers_by_name[name]
        assert info["supported_models"] == models
        assert info["available"] is False
