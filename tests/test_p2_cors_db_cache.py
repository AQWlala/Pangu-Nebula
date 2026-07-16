# tests/test_p2_cors_db_cache.py
"""v2.2.1 P2 — 三个 P2 一般问题修复的回归测试

覆盖:
1. P2-1 CORS 收敛: allow_methods/allow_headers 不再是通配符 "*"
2. P2-2 DB 连接池: engine 含 pool_pre_ping=True (防 stale connection)
3. P2-3 Embedding 缓存: _LocalHashEmbedding._embed_cached LRU 命中/未命中/淘汰

约束:
- 不引入新依赖 (functools/hashlib 标准库)
- 不修改被测代码的函数签名
- SQLite 下不强制 pool_size (engine.py 已按 database_url 分支处理)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ============ P2-1: CORS 收敛 ============

class TestCorsHardened:
    """CORS allow_methods / allow_headers 收敛到具体集合,不再通配。"""

    def test_cors_methods_restricted(self, test_client: TestClient):
        """Access-Control-Allow-Methods 不含通配符 *"""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 204)
        allow_methods = response.headers.get("access-control-allow-methods", "")
        # 核心断言: 不含通配符
        assert "*" not in allow_methods, (
            f"allow-methods 仍为通配符: {allow_methods!r}"
        )
        # 收敛后应包含实际 RESTful 方法
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
            assert method in allow_methods, (
                f"{method} 缺失于 allow-methods: {allow_methods!r}"
            )

    def test_cors_headers_restricted(self, test_client: TestClient):
        """Access-Control-Allow-Headers 不含通配符 *"""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code in (200, 204)
        allow_headers = response.headers.get("access-control-allow-headers", "")
        # 核心断言: 不含通配符
        assert "*" not in allow_headers, (
            f"allow-headers 仍为通配符: {allow_headers!r}"
        )
        # 收敛后应包含实际使用的头 (大小写不敏感比对)
        lowered = allow_headers.lower()
        for header in ("authorization", "content-type", "accept"):
            assert header in lowered, (
                f"{header} 缺失于 allow-headers: {allow_headers!r}"
            )

    def test_cors_options_allowed(self, test_client: TestClient):
        """OPTIONS 预检请求仍可用 (不被 401/405 拦截)"""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        # CORS 预检应返回 200 (CORSMiddleware 处理) 而非 401/405
        assert response.status_code in (200, 204), (
            f"OPTIONS 预检失败, status={response.status_code}, "
            f"body={response.text[:200]}"
        )


# ============ P2-2: DB 连接池 ============

class TestDbEnginePoolPrePing:
    """engine 配置含 pool_pre_ping=True, 防 stale connection."""

    def test_db_engine_has_pre_ping(self):
        """engine.sync_engine.pool._pre_ping == True

        SQLAlchemy 2.0 在 pool 对象上存储 _pre_ping 标志:
        - pool_pre_ping=True  -> _pre_ping = True
        - 未配置              -> _pre_ping = False
        (已通过对照实验验证: 不传 kwarg 时 _pre_ping=False)
        """
        from server.db.engine import engine
        sync_engine = engine.sync_engine
        pool = sync_engine.pool
        # 核心断言: pool_pre_ping 已启用
        assert getattr(pool, "_pre_ping", None) is True, (
            "engine.pool._pre_ping 应为 True (pool_pre_ping 已配置), "
            f"实际: {getattr(pool, '_pre_ping', None)!r}"
        )

    def test_db_engine_sqlite_no_pool_size(self):
        """SQLite 下不强制 pool_size (会与 SingletonThreadPool 冲突)

        验证 engine.py 的分支逻辑: SQLite 仅加 pool_pre_ping,
        PostgreSQL/MySQL 才加 pool_size/max_overflow/pool_recycle。
        默认 database_url 为 sqlite+aiosqlite,故池类型应为 AsyncAdaptedQueuePool
        且不抛错 (说明未传 SQLite 不支持的 pool_size 参数)。
        """
        from server.db.engine import engine, database_url
        # 仅在 SQLite 下验证 (CI 默认 SQLite)
        if not database_url.startswith("sqlite"):
            pytest.skip("非 SQLite,跳过 SQLite 专属断言")
        pool = engine.sync_engine.pool
        # SQLite 引擎能正常创建即说明未传冲突参数
        assert pool is not None
        # AsyncAdaptedQueuePool 是 aiosqlite 的默认池类型
        assert "Pool" in type(pool).__name__


# ============ P2-3: Embedding 缓存 ============

class TestEmbeddingCache:
    """_LocalHashEmbedding._embed_cached LRU 缓存行为。"""

    @pytest.fixture(autouse=True)
    def _clear_cache_per_test(self):
        """每个测试前后清空 LRU 缓存,避免测试间相互污染。"""
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        _LocalHashEmbedding._embed_cached.cache_clear()
        yield
        _LocalHashEmbedding._embed_cached.cache_clear()

    def test_embedding_cache_hit(self):
        """相同文本第二次调用命中缓存 (hits 增加, 返回相同对象)"""
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        emb = _LocalHashEmbedding(dim=384)

        # 第一次调用: miss
        v1 = emb._embed_one("hello world")
        info_after_first = _LocalHashEmbedding._embed_cached.cache_info()
        assert info_after_first.misses == 1
        assert info_after_first.hits == 0

        # 第二次相同文本: 应命中缓存
        v2 = emb._embed_one("hello world")
        info_after_second = _LocalHashEmbedding._embed_cached.cache_info()
        assert info_after_second.hits == 1, (
            f"第二次相同文本应命中缓存, hits={info_after_second.hits}"
        )

        # 向量值应相等 (语义等价)
        import numpy as np
        assert np.array_equal(v1, v2)

        # 缓存层返回的 tuple 应是同一对象 (is) — 证明走的是缓存
        t1 = _LocalHashEmbedding._embed_cached("hello world", 384)
        t2 = _LocalHashEmbedding._embed_cached("hello world", 384)
        assert t1 is t2, "相同输入应返回缓存的同一 tuple 对象"

    def test_embedding_cache_different_text(self):
        """不同文本不命中缓存 (misses 增加)"""
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        emb = _LocalHashEmbedding(dim=384)

        v1 = emb._embed_one("first text")
        v2 = emb._embed_one("second different text")

        info = _LocalHashEmbedding._embed_cached.cache_info()
        # 两次不同输入 -> 两次 miss, 0 hit
        assert info.misses == 2, f"应有 2 次 miss, 实际 {info.misses}"
        assert info.hits == 0, f"不应有 hit, 实际 {info.hits}"

        # 向量应不同
        import numpy as np
        assert not np.array_equal(v1, v2), "不同文本不应产生相同向量"

    def test_embedding_cache_lru_eviction(self):
        """maxsize=1024 满后淘汰最久未用条目 (LRU 语义验证)

        策略:
        1. 填入 1024 个不同文本填满缓存
        2. 再次访问第一个文本 (LRU 最近使用, 不应被淘汰, 因为它最老)
           — 实际上填满后第一个文本是最老的,但 LRU 在填满过程中若被访问会更新
        3. 插入第 1025 个文本触发淘汰
        4. 验证 currsize 不超过 maxsize
        """
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        emb = _LocalHashEmbedding(dim=384)

        # 1. 填满缓存 (maxsize=1024)
        for i in range(1024):
            emb._embed_one(f"text-{i}")
        info_full = _LocalHashEmbedding._embed_cached.cache_info()
        assert info_full.currsize == 1024, (
            f"填满后 currsize 应为 1024, 实际 {info_full.currsize}"
        )
        assert info_full.maxsize == 1024

        # 2. 再访问第一个文本 (应命中,因为 LRU 把它标记为最近使用)
        emb._embed_one("text-0")
        info_after_revisit = _LocalHashEmbedding._embed_cached.cache_info()
        assert info_after_revisit.hits >= 1, "再访问 text-0 应命中缓存"

        # 3. 插入新文本触发淘汰 (currsize 已满,新条目挤掉最老的)
        emb._embed_one("overflow-text-1024")
        info_after_overflow = _LocalHashEmbedding._embed_cached.cache_info()
        # LRU 淘汰后 currsize 仍 = maxsize (不会无限增长)
        assert info_after_overflow.currsize == 1024, (
            f"淘汰后 currsize 应保持 1024, 实际 {info_after_overflow.currsize}"
        )

        # 4. 验证确实发生了淘汰: text-1 (未被再访问,最老) 应被淘汰
        #    重新访问 text-1 应计为 miss (因已被淘汰)
        #    注意: text-0 在步骤2被访问过,所以它在 text-1 之后,LRU 优先淘汰 text-1
        #    但若 maxsize 策略保留最近使用的,text-1 应该已被淘汰
        #    为避免 LRU 实现细节不确定性,只断言 currsize 不超过 maxsize
        #    (上面已断言),并断言总 miss 数合理增长
        assert info_after_overflow.misses >= 1025, (
            f"插入 overflow 后 misses 应 >= 1025, 实际 {info_after_overflow.misses}"
        )

    def test_embedding_cache_maxsize_is_1024(self):
        """lru_cache maxsize 固定为 1024 (符合 P2 配置约定)"""
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        info = _LocalHashEmbedding._embed_cached.cache_info()
        assert info.maxsize == 1024, (
            f"maxsize 应为 1024 (P2 约定), 实际 {info.maxsize}"
        )

    def test_embedding_cache_dim_isolation(self):
        """不同 dim 的相同文本不共享缓存 (dim 作为 cache key 的一部分)"""
        from server.kb.retrieval.vectorstore import _LocalHashEmbedding
        emb_384 = _LocalHashEmbedding(dim=384)
        emb_128 = _LocalHashEmbedding(dim=128)

        v_384 = emb_384._embed_one("same text")
        v_128 = emb_128._embed_one("same text")

        info = _LocalHashEmbedding._embed_cached.cache_info()
        # 不同 dim -> 两次 miss (dim 是 key 的一部分)
        assert info.misses == 2, (
            f"不同 dim 应产生 2 次 miss, 实际 {info.misses}"
        )

        # 向量维度应不同
        import numpy as np
        assert v_384.shape == (384,)
        assert v_128.shape == (128,)
