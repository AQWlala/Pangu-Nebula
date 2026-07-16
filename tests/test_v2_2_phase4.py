# tests/test_v2_2_phase4.py
"""v2.2.0 Phase 4 — LanceDB 知识库 + RAG 接入对话 测试

测试覆盖:
1. _chunk_text 文本切片
2. format_rag_context RAG 上下文格式化
3. KnowledgeService (自动降级 LanceDB → ChromaVectorStore)
4. LanceVectorStore (importorskip lancedb,本地无 lancedb 时跳过)
5. stream_reply RAG 接入 (mock knowledge_service)
6. /api/kb/status 端点
"""
import pytest
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

# 项目内导入
from server.services.knowledge_service import (
    KnowledgeService,
    _chunk_text,
    format_rag_context,
    knowledge_service,
)
from server.config_kb_cu import KBConfig


# ============================================================
# 1. _chunk_text 文本切片
# ============================================================

class TestChunkText:
    def test_empty_text(self):
        assert _chunk_text("") == []
        assert _chunk_text(None) == []  # type: ignore

    def test_short_text_no_split(self):
        text = "hello world"
        result = _chunk_text(text, chunk_size=100, overlap=10)
        assert result == ["hello world"]

    def test_long_text_splits(self):
        text = "a" * 150
        result = _chunk_text(text, chunk_size=50, overlap=10)
        assert len(result) >= 3
        # 每个切片不超过 chunk_size
        for chunk in result:
            assert len(chunk) <= 50

    def test_overlap(self):
        text = "abcdefghij" * 10  # 100 字符
        result = _chunk_text(text, chunk_size=20, overlap=5)
        # 第二个切片应与第一个有 5 字符重叠
        if len(result) >= 2:
            # 第一个切片结束的 5 字符应出现在第二个切片开头
            assert result[0][-5:] == result[1][:5]


# ============================================================
# 2. format_rag_context RAG 上下文格式化
# ============================================================

class TestFormatRagContext:
    def test_empty_results(self):
        assert format_rag_context([]) == ""

    def test_single_result(self):
        results = [{"doc_id": "doc1", "score": 0.85, "text": "这是参考内容"}]
        ctx = format_rag_context(results)
        assert "知识库参考:" in ctx
        assert "doc_id:doc1" in ctx
        assert "score:0.850" in ctx
        assert "这是参考内容" in ctx

    def test_multiple_results(self):
        results = [
            {"doc_id": "doc1", "score": 0.9, "text": "内容1"},
            {"doc_id": "doc2", "score": 0.7, "text": "内容2"},
        ]
        ctx = format_rag_context(results)
        assert "[1]" in ctx
        assert "[2]" in ctx
        assert "内容1" in ctx
        assert "内容2" in ctx

    def test_long_text_truncated(self):
        long_text = "x" * 1000
        results = [{"doc_id": "doc1", "score": 0.85, "text": long_text}]
        ctx = format_rag_context(results)
        assert "..." in ctx
        # 截断后不超过 800 + 3 (省略号)
        assert len(ctx.split("doc_id:doc1")[1]) < 900

    def test_empty_text_skipped(self):
        results = [
            {"doc_id": "doc1", "score": 0.85, "text": ""},
            {"doc_id": "doc2", "score": 0.7, "text": "有效内容"},
        ]
        ctx = format_rag_context(results)
        assert "有效内容" in ctx
        assert "doc1" not in ctx


# ============================================================
# 3. KnowledgeService (自动降级)
# ============================================================

class TestKnowledgeService:
    def test_init_with_temp_config(self):
        """KnowledgeService 初始化,使用临时目录。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)
            # 不触发 _get_store() (因为本地可能无 chromadb/lancedb)
            assert svc._config is not None
            svc.close()

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        """空查询返回空结果,不触发 store。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)
            result = await svc.search("", top_k=5)
            assert result == []
            svc.close()

    @pytest.mark.asyncio
    async def test_ingest_and_search_with_mock_store(self):
        """摄入文档后能检索到 (使用 mock store,不依赖真实 chromadb/lancedb)。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)

            # mock store
            mock_store = MagicMock()
            mock_store.upsert = MagicMock()
            mock_store.query = MagicMock(return_value=[
                {"id": "c0", "doc_id": "test-doc-1", "text": "Python 异步编程",
                 "scope": "private", "tags": [], "score": 0.9}
            ])
            mock_store.count = MagicMock(return_value=1)
            svc._store = mock_store
            svc._store_type = "mock"

            # 摄入文档
            ingest_result = await svc.ingest(
                doc_id="test-doc-1",
                content="Python 异步编程是现代开发的重要技能",
                scope="private",
                tags=["python", "async"],
            )
            assert ingest_result["doc_id"] == "test-doc-1"
            assert ingest_result["chunks"] >= 1
            mock_store.upsert.assert_called_once()

            # 检索
            results = await svc.search("Python 异步", top_k=5, scope="private")
            assert len(results) >= 1
            assert results[0]["doc_id"] == "test-doc-1"
            mock_store.query.assert_called_once()
            svc.close()

    @pytest.mark.asyncio
    async def test_ingest_empty_content(self):
        """空内容摄入返回 0 chunks。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)
            result = await svc.ingest("doc1", "", scope="private")
            assert result["chunks"] == 0
            svc.close()

    @pytest.mark.asyncio
    async def test_delete_doc_with_mock_store(self):
        """删除文档 (使用 mock store)。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)

            mock_store = MagicMock()
            mock_store.delete_by_doc_id = MagicMock()
            svc._store = mock_store
            svc._store_type = "mock"

            ok = await svc.delete_doc("del-doc")
            assert ok is True
            mock_store.delete_by_doc_id.assert_called_once_with("del-doc")
            svc.close()

    @pytest.mark.asyncio
    async def test_delete_doc_failure(self):
        """删除失败返回 False。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)

            mock_store = MagicMock()
            mock_store.delete_by_doc_id = MagicMock(side_effect=Exception("fail"))
            svc._store = mock_store
            svc._store_type = "mock"

            ok = await svc.delete_doc("del-doc")
            assert ok is False
            svc.close()

    def test_get_status_with_mock_store(self):
        """get_status 返回正确结构 (使用 mock store)。"""
        with TemporaryDirectory() as tmp:
            config = KBConfig(kb_root=Path(tmp))
            config.ensure_dirs()
            svc = KnowledgeService(config=config)

            mock_store = MagicMock()
            mock_store.count = MagicMock(return_value=42)
            svc._store = mock_store
            svc._store_type = "mock"

            status = svc.get_status()
            assert "store_type" in status
            assert "chunk_count" in status
            assert "persist_dir" in status
            assert status["store_type"] == "mock"
            assert status["chunk_count"] == 42
            svc.close()


# ============================================================
# 4. LanceVectorStore (importorskip lancedb)
# ============================================================

# 注意: importorskip 必须放在类内部,否则会跳过整个模块
# 无 lancedb 时,以下测试类会被跳过


class TestLanceVectorStore:
    """LanceDB 适配器测试 — 仅在 lancedb 可用时运行。"""

    def test_init(self):
        pytest.importorskip("lancedb")
        from server.kb.retrieval.lance_store import LanceVectorStore
        with TemporaryDirectory() as tmp:
            store = LanceVectorStore(persist_dir=Path(tmp))
            assert store._db is None  # 惰性初始化
            store.close()

    @pytest.mark.asyncio
    async def test_upsert_and_query(self):
        pytest.importorskip("lancedb")
        from server.kb.retrieval.lance_store import LanceVectorStore
        with TemporaryDirectory() as tmp:
            store = LanceVectorStore(persist_dir=Path(tmp))
            chunks = [{
                "id": "chunk1",
                "doc_id": "doc1",
                "text": "Python 异步编程",
                "scope": "private",
                "tags": ["python"],
                "chunk_idx": 0,
                "section": "",
            }]
            store.upsert(chunks)
            results = store.query("Python 异步", scope="private", top_k=5)
            assert len(results) >= 1
            assert results[0]["doc_id"] == "doc1"
            store.close()

    def test_delete_by_doc_id(self):
        pytest.importorskip("lancedb")
        from server.kb.retrieval.lance_store import LanceVectorStore
        with TemporaryDirectory() as tmp:
            store = LanceVectorStore(persist_dir=Path(tmp))
            store.upsert([{
                "id": "c1", "doc_id": "d1", "text": "内容",
                "scope": "private", "tags": [], "chunk_idx": 0, "section": "",
            }])
            store.delete_by_doc_id("d1")
            assert store.count() == 0
            store.close()


# ============================================================
# 5. stream_reply RAG 接入
# ============================================================

class TestStreamReplyRAG:
    """测试 stream_reply 中的 RAG 检索接入。"""

    @pytest.mark.asyncio
    async def test_rag_disabled_no_search(self):
        """rag_enabled=False 时不执行 RAG 检索。"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation, Message

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=[])

            svc = ChatService()
            # mock stream_reply 内部所需
            with patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):
                with patch("server.services.chat_service.async_session") as mock_session_factory:
                    # 构造 mock session 返回 persona + history
                    mock_session = AsyncMock()
                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

                    persona = Persona(
                        id=1, name="test", system_prompt="你是助手",
                        model_provider=None,  # 触发 "No provider" 分支
                        rag_enabled=False,
                        tools_enabled=False,
                    )
                    conv = Conversation(id=1, persona_id=1)
                    mock_session.execute = AsyncMock(side_effect=[
                        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
                        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
                        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                    ])
                    mock_session.add = MagicMock()
                    mock_session.commit = AsyncMock()

                    chunks = []
                    async for chunk in svc.stream_reply(1, "hello"):
                        chunks.append(chunk)

                    # rag_enabled=False,不应调用 search
                    mock_svc.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_rag_enabled_triggers_search(self):
        """rag_enabled=True 时执行 RAG 检索并 yield rag_context 事件。"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation

        rag_results = [
            {"doc_id": "doc1", "score": 0.9, "text": "RAG 参考内容"},
        ]

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=rag_results)

            svc = ChatService()
            with patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):
                with patch("server.services.chat_service.async_session") as mock_session_factory:
                    mock_session = AsyncMock()
                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

                    persona = Persona(
                        id=1, name="test", system_prompt="你是助手",
                        model_provider=None,  # 触发 "No provider" 分支
                        rag_enabled=True,
                        tools_enabled=False,
                    )
                    conv = Conversation(id=1, persona_id=1)
                    mock_session.execute = AsyncMock(side_effect=[
                        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
                        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
                        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                    ])
                    mock_session.add = MagicMock()
                    mock_session.commit = AsyncMock()

                    chunks = []
                    async for chunk in svc.stream_reply(1, "hello"):
                        chunks.append(chunk)

                    # 应调用 search
                    mock_svc.search.assert_called_once()
                    # 应 yield rag_context 事件
                    rag_events = [c for c in chunks if c.get("type") == "rag_context"]
                    assert len(rag_events) == 1
                    assert rag_events[0]["sources"][0]["doc_id"] == "doc1"

    @pytest.mark.asyncio
    async def test_rag_search_failure_does_not_block(self):
        """RAG 检索失败不阻断对话。"""
        from server.services.chat_service import ChatService
        from server.db.orm import Persona, Conversation

        with patch("server.services.chat_service.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(side_effect=Exception("DB error"))

            svc = ChatService()
            with patch.object(svc, "_persist_assistant", AsyncMock(return_value=1)):
                with patch("server.services.chat_service.async_session") as mock_session_factory:
                    mock_session = AsyncMock()
                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

                    persona = Persona(
                        id=1, name="test", system_prompt="你是助手",
                        model_provider=None,
                        rag_enabled=True,
                        tools_enabled=False,
                    )
                    conv = Conversation(id=1, persona_id=1)
                    mock_session.execute = AsyncMock(side_effect=[
                        MagicMock(scalar_one_or_none=MagicMock(return_value=conv)),
                        MagicMock(scalar_one_or_none=MagicMock(return_value=persona)),
                        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                    ])
                    mock_session.add = MagicMock()
                    mock_session.commit = AsyncMock()

                    chunks = []
                    async for chunk in svc.stream_reply(1, "hello"):
                        chunks.append(chunk)

                    # 不应崩溃,应有 error 事件(No provider)
                    assert any(c.get("type") == "error" for c in chunks)
                    # 不应有 rag_context 事件
                    assert not any(c.get("type") == "rag_context" for c in chunks)


# ============================================================
# 6. /api/kb/status 端点
# ============================================================

class TestKBStatusEndpoint:
    """测试 /api/kb/status 端点。"""

    def test_status_endpoint(self):
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("server.services.knowledge_service.knowledge_service") as mock_svc:
            mock_svc.get_status = MagicMock(return_value={
                "store_type": "chroma",
                "chunk_count": 42,
                "persist_dir": "/tmp/kb",
            })
            client = TestClient(app)
            resp = client.get("/api/kb/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["store_type"] == "chroma"
            assert data["data"]["chunk_count"] == 42

    def test_status_endpoint_error(self):
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("server.services.knowledge_service.knowledge_service") as mock_svc:
            mock_svc.get_status = MagicMock(side_effect=Exception("init failed"))
            client = TestClient(app)
            resp = client.get("/api/kb/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is False
            assert data["data"]["store_type"] == "unknown"
