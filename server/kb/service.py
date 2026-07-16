# server/kb/service.py
"""Shared service helpers for KB API layers.

These helpers are designed to be used as FastAPI ``Depends()`` callables,
centralizing storage/config construction that was previously duplicated
across ``server/api/kb.py`` and ``server/api/graph.py``.

Each store helper reads the singleton from ``app.state`` when available
(populated by lifespan in ``server/main.py``) and falls back to per-request
construction when the lifespan did not run (e.g. in tests that bypass
lifespan).
"""
from __future__ import annotations

from fastapi import Request

from server.config_kb_cu import KBConfig
from server.kb.graph.kuzu_store import KuzuGraphStore
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.repo import DocumentRepo


def get_kb_config() -> KBConfig:
    """Return a KBConfig with directories ensured.

    Usable as a FastAPI ``Depends()`` callable. Creates a fresh instance per
    call (no caching) to remain compatible with tests that monkeypatch
    KBConfig between requests.
    """
    config = KBConfig()
    config.ensure_dirs()
    return config


def get_vector_store(request: Request) -> ChromaVectorStore:
    """Return the singleton ChromaVectorStore from ``app.state`` when available.

    Falls back to per-request construction when the lifespan did not
    initialize a singleton (e.g. in tests that bypass lifespan).
    """
    store = getattr(request.app.state, "vector_store", None)
    if store is not None:
        return store
    config = get_kb_config()
    return ChromaVectorStore(persist_dir=config.chroma_dir)


def get_graph_store(request: Request) -> KuzuGraphStore:
    """Return the singleton KuzuGraphStore from ``app.state`` when available.

    Falls back to per-request construction when the lifespan did not
    initialize a singleton (e.g. in tests that bypass lifespan).

    Note: does NOT call ``ensure_dirs()`` — KuzuGraphStore creates its own
    parent directory, and kuzu 0.11.3 does not allow ``db_dir`` itself to
    pre-exist as a directory.
    """
    store = getattr(request.app.state, "graph_store", None)
    if store is not None:
        return store
    config = KBConfig()
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    return store


def get_document_repo(request: Request) -> DocumentRepo:
    """Return a DocumentRepo constructed from the current KBConfig.

    DocumentRepo is a lightweight file-based store; per-request construction
    is cheap and avoids shared mutable state across requests.
    """
    config = get_kb_config()
    return DocumentRepo(documents_dir=config.documents_dir)


def get_inbox_writer(request: Request) -> InboxWriter:
    """Return an InboxWriter constructed from the current KBConfig.

    InboxWriter is a lightweight file-based store; per-request construction
    is cheap.
    """
    config = get_kb_config()
    return InboxWriter(inbox_dir=config.inbox_dir)
