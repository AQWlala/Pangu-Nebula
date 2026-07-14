"""T0.4 Provider 协议抽象层测试

覆盖:
1. 协议基类 ProtocolBase - 多模态检测/图片剥离/统一流式接口
2. OpenAI 协议 - SSE 解析 / mock 响应 / payload 构建
3. Anthropic 协议 - system 分离 / SSE 解析
4. Gemini 协议 - 角色映射 / contents 构建 / SSE 解析
5. Custom 协议 - 抽象行为
6. 8 个 provider 的 protocol 字段正确性
7. 新增 provider 只需 1 个类 (验证代码量缩减)
8. 多模态 fallback 自动剥离图片
9. 统一 StreamChunk 流式接口
"""

import json

import pytest

from server.providers import (
    AnthropicProvider,
    AnthropicProtocol,
    BaseProvider,
    CustomProtocol,
    DeepSeekProvider,
    GeminiProvider,
    GeminiProtocol,
    KimiProvider,
    Message,
    OpenAIProvider,
    OpenAIProtocol,
    OpenRouterProvider,
    ProtocolBase,
    ProviderCapability,
    QwenProvider,
    StreamChunk,
    ZhipuProvider,
    list_providers,
    register_provider,
)


# ===== 1. ProtocolBase 多模态工具方法 =====


def test_protocol_base_detects_image_content():
    """ProtocolBase._has_image_content 正确检测 OpenAI 多模态格式"""
    # 纯文本 - 无图片
    assert ProtocolBase._has_image_content("hello") is False
    assert ProtocolBase._has_image_content(["text"]) is False

    # 含图片的多模态 content
    multimodal = [
        {"type": "text", "text": "What is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
    ]
    assert ProtocolBase._has_image_content(multimodal) is True

    # 仅图片
    image_only = [{"type": "image_url", "image_url": {"url": "..."}}]
    assert ProtocolBase._has_image_content(image_only) is True


def test_protocol_base_messages_have_images():
    """ProtocolBase._messages_have_images 检测消息列表中的图片"""
    text_msgs = [
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi"),
    ]
    assert ProtocolBase._messages_have_images(text_msgs) is False

    multimodal_msgs = [
        Message(role="user", content="look at this"),
        Message(
            role="user",
            content=[
                {"type": "text", "text": "describe"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        ),
    ]
    assert ProtocolBase._messages_have_images(multimodal_msgs) is True


def test_protocol_base_strip_images_returns_text_only():
    """ProtocolBase._strip_images 剥离图片,保留文本"""
    msgs = [
        Message(role="system", content="you are helpful"),
        Message(
            role="user",
            content=[
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        ),
    ]
    stripped = ProtocolBase._strip_images(msgs)

    assert len(stripped) == 2
    assert stripped[0].role == "system"
    assert stripped[0].content == "you are helpful"
    assert stripped[1].role == "user"
    # 文本 part 被保留并拼接为字符串
    assert isinstance(stripped[1].content, str)
    assert "What is in this image?" in stripped[1].content
    # 图片已剥离
    assert "image_url" not in str(stripped[1].content)
    assert "data:image" not in stripped[1].content


def test_protocol_base_strip_images_preserves_str_content():
    """_strip_images 对纯字符串 content 原样保留"""
    msgs = [Message(role="user", content="pure text")]
    stripped = ProtocolBase._strip_images(msgs)
    assert stripped[0].content == "pure text"


# ===== 2. 多模态 fallback 应用 =====


def test_apply_multimodal_fallback_strips_when_no_vision():
    """_apply_multimodal_fallback 在 capabilities.vision=False 时剥离图片"""

    class NoVisionProvider(OpenAIProtocol):
        name = "test-novision"
        capabilities = ProviderCapability(text=True, vision=False)
        env_key = "TEST_NOVISION_KEY"

    provider = NoVisionProvider()
    msgs = [
        Message(
            role="user",
            content=[
                {"type": "text", "text": "describe"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        )
    ]
    effective, stripped = provider._apply_multimodal_fallback(msgs)
    assert stripped is True
    assert not provider._messages_have_images(effective)


def test_apply_multimodal_fallback_keeps_when_vision_supported():
    """_apply_multimodal_fallback 在 capabilities.vision=True 时保留图片"""

    class VisionProvider(OpenAIProtocol):
        name = "test-vision"
        capabilities = ProviderCapability(text=True, vision=True)
        env_key = "TEST_VISION_KEY"

    provider = VisionProvider()
    msgs = [
        Message(
            role="user",
            content=[
                {"type": "text", "text": "describe"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        )
    ]
    effective, stripped = provider._apply_multimodal_fallback(msgs)
    assert stripped is False
    assert provider._messages_have_images(effective)


# ===== 3. OpenAI 协议 =====


def test_openai_protocol_sse_line_parsing():
    """OpenAIProtocol._parse_sse_line 正确解析 OpenAI 流式响应"""
    # 正常 content delta
    line = 'data: {"choices":[{"delta":{"content":"hello"}}]}'
    assert OpenAIProtocol._parse_sse_line(line) == "hello"

    # [DONE] 标记
    assert OpenAIProtocol._parse_sse_line("data: [DONE]") == ""

    # 空/非 data 行
    assert OpenAIProtocol._parse_sse_line("") == ""
    assert OpenAIProtocol._parse_sse_line(": comment") == ""

    # 无 choices
    assert OpenAIProtocol._parse_sse_line('data: {"id":"x"}') == ""

    # 无效 JSON
    assert OpenAIProtocol._parse_sse_line("data: {invalid") == ""


def test_openai_protocol_parse_sse_chunk_returns_streamchunk():
    """OpenAIProtocol._parse_sse_chunk 返回带 finish_reason 的 StreamChunk"""
    line = 'data: {"choices":[{"delta":{"content":"world"},"finish_reason":null}]}'
    chunk = OpenAIProtocol._parse_sse_chunk(line)
    assert chunk is not None
    assert isinstance(chunk, StreamChunk)
    assert chunk.text == "world"

    # stop 信号
    stop_line = 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
    stop_chunk = OpenAIProtocol._parse_sse_chunk(stop_line)
    assert stop_chunk is not None
    assert stop_chunk.finish_reason == "stop"

    # [DONE]
    done_chunk = OpenAIProtocol._parse_sse_chunk("data: [DONE]")
    assert done_chunk is not None
    assert done_chunk.finish_reason == "stop"


def test_openai_protocol_build_payload_format():
    """OpenAIProtocol._build_payload 生成正确的 OpenAI 格式"""

    class TestOpenAI(OpenAIProtocol):
        name = "test-openai"
        env_key = "TEST_OPENAI_KEY"
        default_chat_model = "gpt-4o-mini"

    provider = TestOpenAI()
    msgs = [
        Message(role="system", content="be helpful"),
        Message(role="user", content="hi"),
    ]
    payload = provider._build_payload(msgs, "gpt-4o", {"temperature": 0.5})

    assert payload["model"] == "gpt-4o"
    assert payload["stream"] is True
    assert payload["temperature"] == 0.5
    assert len(payload["messages"]) == 2
    assert payload["messages"][0] == {"role": "system", "content": "be helpful"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}


def test_openai_protocol_mock_generate_without_key(monkeypatch):
    """OpenAIProtocol.generate 无 API key 时返回 mock"""
    monkeypatch.delenv("TEST_OPENAI_MOCK_KEY", raising=False)

    class TestOpenAI(OpenAIProtocol):
        name = "test-openai-mock"
        env_key = "TEST_OPENAI_MOCK_KEY"
        default_chat_model = "gpt-4o-mini"
        supported_models = ["gpt-4o-mini"]

    provider = TestOpenAI()
    assert provider.api_key == ""

    msgs = [Message(role="user", content="Hello, world! This is a test.")]
    chunks = []
    import asyncio

    async def _collect():
        async for c in provider.generate(msgs, "gpt-4o-mini"):
            chunks.append(c)

    asyncio.run(_collect())
    assert len(chunks) == 1
    assert chunks[0].startswith("[mock] ")
    assert "test-openai-mock" in chunks[0]
    assert "Hello, world!" in chunks[0]


# ===== 4. Anthropic 协议 =====


def test_anthropic_protocol_split_system():
    """AnthropicProtocol._split_system 正确分离 system 消息"""
    msgs = [
        Message(role="system", content="you are claude"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi"),
    ]
    system, api_msgs = AnthropicProtocol._split_system(msgs)
    assert system == "you are claude"
    assert len(api_msgs) == 2
    assert api_msgs[0] == {"role": "user", "content": "hello"}
    assert api_msgs[1] == {"role": "assistant", "content": "hi"}


def test_anthropic_protocol_sse_line_parsing():
    """AnthropicProtocol._parse_sse_line 解析 content_block_delta"""
    # text_delta
    line = 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}'
    assert AnthropicProtocol._parse_sse_line(line) == "hi"

    # 非 content_block_delta 事件 (如 message_start)
    line = 'data: {"type":"message_start","message":{}}'
    assert AnthropicProtocol._parse_sse_line(line) == ""

    # 非 text_delta
    line = 'data: {"type":"content_block_delta","delta":{"type":"input_json_delta"}}'
    assert AnthropicProtocol._parse_sse_line(line) == ""


def test_anthropic_protocol_build_payload_includes_system():
    """AnthropicProtocol._build_payload 包含 system 字段和 max_tokens"""

    class TestAnthropic(AnthropicProtocol):
        name = "test-anthropic"
        env_key = "TEST_ANTHROPIC_KEY"
        default_chat_model = "claude-3-5-sonnet-latest"

    provider = TestAnthropic()
    msgs = [
        Message(role="system", content="be safe"),
        Message(role="user", content="hello"),
    ]
    payload = provider._build_payload(msgs, "claude-3-opus", {"max_tokens": 512})

    assert payload["model"] == "claude-3-opus"
    assert payload["system"] == "be safe"
    assert payload["max_tokens"] == 512
    assert payload["stream"] is True
    assert len(payload["messages"]) == 1


# ===== 5. Gemini 协议 =====


def test_gemini_protocol_role_mapping():
    """GeminiProtocol._to_gemini_role 正确映射角色"""
    assert GeminiProtocol._to_gemini_role("user") == "user"
    assert GeminiProtocol._to_gemini_role("assistant") == "model"
    assert GeminiProtocol._to_gemini_role("tool") == "user"
    assert GeminiProtocol._to_gemini_role("system") == "system"


def test_gemini_protocol_build_contents():
    """GeminiProtocol._build_contents 正确构建 contents + systemInstruction"""

    class TestGemini(GeminiProtocol):
        name = "test-gemini"
        env_key = "TEST_GEMINI_KEY"
        default_chat_model = "gemini-2.0-flash"

    provider = TestGemini()
    msgs = [
        Message(role="system", content="be concise"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi there"),
    ]
    sys_inst, contents = provider._build_contents(msgs)

    assert sys_inst == {"parts": [{"text": "be concise"}]}
    assert len(contents) == 2
    assert contents[0] == {"role": "user", "parts": [{"text": "hello"}]}
    # assistant -> model
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"] == [{"text": "hi there"}]


def test_gemini_protocol_sse_line_parsing():
    """GeminiProtocol._parse_sse_line 解析 candidates.parts.text"""
    line = 'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}'
    assert GeminiProtocol._parse_sse_line(line) == "hello"

    # 无 candidates
    line = 'data: {"promptFeedback":{}}'
    assert GeminiProtocol._parse_sse_line(line) == ""

    # 多个 parts,返回第一个非空 text
    line = 'data: {"candidates":[{"content":{"parts":[{"text":"world"}]}}]}'
    assert GeminiProtocol._parse_sse_line(line) == "world"


# ===== 6. Custom 协议 =====


def test_custom_protocol_is_abstract_for_generate():
    """CustomProtocol.generate 必须由子类实现"""

    class TestCustom(CustomProtocol):
        name = "test-custom"
        env_key = "TEST_CUSTOM_KEY"

    provider = TestCustom()
    import asyncio

    async def _run():
        async for _ in provider.generate([], "model"):
            pass

    with pytest.raises(NotImplementedError):
        asyncio.run(_run())


def test_custom_protocol_embed_raises():
    """CustomProtocol.embed 默认抛出 NotImplementedError"""
    provider = CustomProtocol.__new__(CustomProtocol)
    provider.name = "x"
    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(provider.embed("text", "model"))


# ===== 7. 8 个 provider 的 protocol 字段 =====


PROVIDER_PROTOCOL_MAP = [
    (OpenAIProvider, "openai"),
    (DeepSeekProvider, "openai"),
    (OpenRouterProvider, "openai"),
    (QwenProvider, "openai"),
    (KimiProvider, "openai"),
    (ZhipuProvider, "openai"),
    (AnthropicProvider, "anthropic"),
    (GeminiProvider, "gemini"),
]


@pytest.mark.parametrize("cls,expected_protocol", PROVIDER_PROTOCOL_MAP)
def test_provider_has_correct_protocol_field(cls, expected_protocol):
    """每个 provider 都有正确的 protocol 字段"""
    instance = cls()
    assert instance.protocol == expected_protocol


@pytest.mark.parametrize("cls,expected_protocol", PROVIDER_PROTOCOL_MAP)
def test_provider_info_includes_protocol(cls, expected_protocol):
    """info() 包含 protocol 字段"""
    info = cls().info()
    assert "protocol" in info
    assert info["protocol"] == expected_protocol


@pytest.mark.parametrize("cls,expected_base", [
    (OpenAIProvider, OpenAIProtocol),
    (DeepSeekProvider, OpenAIProtocol),
    (OpenRouterProvider, OpenAIProtocol),
    (QwenProvider, OpenAIProtocol),
    (KimiProvider, OpenAIProtocol),
    (ZhipuProvider, OpenAIProtocol),
    (AnthropicProvider, AnthropicProtocol),
    (GeminiProvider, GeminiProtocol),
])
def test_provider_inherits_correct_protocol_base(cls, expected_base):
    """每个 provider 继承自正确的协议基类"""
    assert issubclass(cls, expected_base)


# ===== 8. 新增 provider 只需 1 个类 =====


def test_new_provider_only_needs_one_class(monkeypatch):
    """验证新增 OpenAI 兼容 provider 只需声明类属性,无需实现任何方法"""

    class FakeProvider(OpenAIProtocol):
        name = "fake-test-provider"
        capabilities = ProviderCapability(text=True, vision=False)
        supported_models = ["fake-1", "fake-2"]
        default_chat_model = "fake-1"
        default_embed_model = "fake-embed"
        env_key = "FAKE_TEST_PROVIDER_KEY"
        env_base_url = "FAKE_TEST_PROVIDER_BASE_URL"
        default_base_url = "https://fake.example.com/v1"

    monkeypatch.delenv("FAKE_TEST_PROVIDER_KEY", raising=False)

    provider = FakeProvider()
    # 自动获得所有能力
    assert provider.api_key == ""
    assert provider.base_url == "https://fake.example.com/v1"
    assert provider.protocol == "openai"

    # info 自动包含 available + protocol
    info = provider.info()
    assert info["name"] == "fake-test-provider"
    assert info["available"] is False
    assert info["protocol"] == "openai"
    assert info["supported_models"] == ["fake-1", "fake-2"]

    # generate 自动返回 mock
    import asyncio

    async def _gen():
        chunks = []
        async for c in provider.generate([Message(role="user", content="hi")], "fake-1"):
            chunks.append(c)
        return chunks

    chunks = asyncio.run(_gen())
    assert len(chunks) == 1
    assert "[mock]" in chunks[0]

    # embed 自动返回 mock 向量
    async def _emb():
        return await provider.embed("text", "fake-embed")

    vec = asyncio.run(_emb())
    assert isinstance(vec, list)
    assert len(vec) == 1536

    # test_connection 自动返回 False
    async def _tc():
        return await provider.test_connection()

    assert asyncio.run(_tc()) is False


# ===== 9. 统一 StreamChunk 流式接口 =====


async def test_unified_stream_interface_yields_streamchunks():
    """stream() 统一接口产出 StreamChunk 对象"""
    provider = DeepSeekProvider()  # 无 API key
    msgs = [Message(role="user", content="hello stream")]
    chunks = []
    async for chunk in provider.stream(msgs, "deepseek-chat"):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert isinstance(chunks[0], StreamChunk)
    assert isinstance(chunks[0].text, str)
    assert "[mock]" in chunks[0].text


async def test_stream_chunk_model_fields():
    """StreamChunk 模型字段正确"""
    chunk = StreamChunk(text="hello", finish_reason="stop")
    assert chunk.text == "hello"
    assert chunk.finish_reason == "stop"
    assert chunk.raw is None

    chunk2 = StreamChunk(text="world", raw={"id": "x"})
    assert chunk2.text == "world"
    assert chunk2.raw == {"id": "x"}


# ===== 10. list_providers 包含 protocol 字段 =====


def test_list_providers_includes_protocol_field():
    """list_providers() 返回的 info 包含 protocol 字段"""
    providers = list_providers()
    assert len(providers) >= 8
    for p in providers:
        assert "protocol" in p, f"Provider {p.get('name')} missing protocol field"
        assert p["protocol"] in ("openai", "anthropic", "gemini", "custom")


# ===== 11. 协议基类不能直接实例化(抽象方法) =====


def test_protocol_base_cannot_instantiate():
    """ProtocolBase 是抽象类,不能直接实例化"""
    with pytest.raises(TypeError):
        ProtocolBase()


def test_base_provider_has_protocol_field():
    """BaseProvider 添加了 protocol 字段,默认 'custom'"""
    assert hasattr(BaseProvider, "protocol")
    assert BaseProvider.protocol == "custom"


# ===== 12. 多模态 fallback 在 generate 中生效 =====


async def test_deepseek_generate_strips_images_automatically(monkeypatch):
    """DeepSeek (vision=False) 的 generate 自动剥离图片,返回 mock"""
    monkeypatch.delenv("NEBULA_DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekProvider()
    assert provider.capabilities.vision is False

    multimodal_msgs = [
        Message(
            role="user",
            content=[
                {"type": "text", "text": "describe this image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
            ],
        )
    ]
    chunks = []
    async for c in provider.generate(multimodal_msgs, "deepseek-chat"):
        chunks.append(c)

    # 应返回 mock (因为无 API key),且图片被剥离
    assert len(chunks) == 1
    assert "[mock]" in chunks[0]
    # mock 响应中包含文本预览
    assert "describe this image" in chunks[0]


async def test_openai_generate_with_multimodal_content_no_key(monkeypatch):
    """OpenAI (vision=True) 在无 key 时仍能处理多模态消息返回 mock"""
    monkeypatch.delenv("NEBULA_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("server.providers.config_store.get_provider_config", lambda name: {})
    provider = OpenAIProvider()
    assert provider.capabilities.vision is True

    multimodal_msgs = [
        Message(
            role="user",
            content=[
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )
    ]
    chunks = []
    async for c in provider.generate(multimodal_msgs, "gpt-4o"):
        chunks.append(c)

    assert len(chunks) == 1
    assert "[mock]" in chunks[0]
    assert "what is this?" in chunks[0]


# ===== 13. Anthropic / Gemini 也支持 mock =====


async def test_anthropic_generate_returns_mock_without_key(monkeypatch):
    """Anthropic provider 无 key 时返回 mock"""
    monkeypatch.delenv("NEBULA_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("server.providers.config_store.get_provider_config", lambda name: {})
    provider = AnthropicProvider()
    msgs = [Message(role="user", content="Hello Claude")]
    chunks = []
    async for c in provider.generate(msgs, "claude-3-5-sonnet-latest"):
        chunks.append(c)
    assert len(chunks) == 1
    assert "[mock]" in chunks[0]
    assert "anthropic" in chunks[0]


async def test_gemini_generate_returns_mock_without_key(monkeypatch):
    """Gemini provider 无 key 时返回 mock"""
    monkeypatch.delenv("NEBULA_GEMINI_API_KEY", raising=False)
    provider = GeminiProvider()
    msgs = [Message(role="user", content="Hello Gemini")]
    chunks = []
    async for c in provider.generate(msgs, "gemini-2.0-flash"):
        chunks.append(c)
    assert len(chunks) == 1
    assert "[mock]" in chunks[0]
    assert "gemini" in chunks[0]


async def test_anthropic_embed_raises_not_implemented():
    """Anthropic provider embed 抛出 NotImplementedError"""
    provider = AnthropicProvider()
    with pytest.raises(NotImplementedError):
        await provider.embed("text", "model")


async def test_gemini_embed_raises_not_implemented():
    """Gemini provider embed 抛出 NotImplementedError"""
    provider = GeminiProvider()
    with pytest.raises(NotImplementedError):
        await provider.embed("text", "model")
