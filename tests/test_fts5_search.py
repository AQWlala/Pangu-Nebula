# tests/test_fts5_search.py
"""FTS5 关键词搜索测试（Task P3）"""
import sqlite3
from unittest.mock import MagicMock


def _setup_kb(tmp_path):
    """创建临时 KB，返回 (config, repo, vector_store_mock)。"""
    from server.config_kb_cu import KBConfig
    config = KBConfig(kb_root=tmp_path / "kb")
    config.ensure_dirs()
    from server.kb.storage.repo import DocumentRepo
    repo = DocumentRepo(documents_dir=config.documents_dir)
    # keyword-only 测试不需要真实向量存储，用 mock 即可
    vector_store = MagicMock()
    return config, repo, vector_store


def _make_fm(doc_id, title, scope="private"):
    from server.kb.storage.frontmatter import FrontMatter
    return FrontMatter(
        id=doc_id, title=title, type="note", scope=scope,
        source_type="manual", confidence=0.95,
        checksum=f"sha256:{doc_id}",
    )


def _sync_fts(config, doc_id, title, content, scope):
    """模拟 approve_document 端点的 FTS5 同步逻辑。"""
    from server.kb.retrieval.hybrid import ensure_fts_table
    db_path = config.meta_db
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        ensure_fts_table(conn)
        conn.execute("DELETE FROM kb_documents_fts WHERE doc_id = ?", (doc_id,))
        conn.execute(
            "INSERT INTO kb_documents_fts (doc_id, title, content, scope) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, title, content, scope),
        )
        conn.commit()


def test_fts5_returns_relevant_documents(tmp_path):
    """Test 1: FTS5 搜索返回相关文档。"""
    config, repo, store = _setup_kb(tmp_path)
    docs = [
        ("kb-fts-001", "Python Guide",
         "Python is a popular programming language.", "private"),
        ("kb-fts-002", "Java Guide",
         "Java is another programming language.", "private"),
        ("kb-fts-003", "Cooking Recipes",
         "How to cook pasta with tomato sauce.", "private"),
    ]
    for doc_id, title, content, scope in docs:
        repo.save(_make_fm(doc_id, title, scope), content)
        _sync_fts(config, doc_id, title, content, scope)

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher._keyword_search("Python", "private", top_k=10)

    doc_ids = [r.doc_id for r in results]
    # 包含 Python 的文档应被检索到
    assert "kb-fts-001" in doc_ids
    # 不含 Python 的文档不应出现
    assert "kb-fts-003" not in doc_ids
    # Java 文档不含 "python" token，不应匹配单 term 查询
    assert "kb-fts-002" not in doc_ids
    # 所有结果标记为 keyword 来源
    assert all(r.source_method == "keyword" for r in results)


def test_fts5_ranks_better_matches_higher(tmp_path):
    """Test 2: FTS5 搜索将更好匹配的文档排在前面。"""
    config, repo, store = _setup_kb(tmp_path)
    # Doc A：Python 出现多次，短文档 → BM25 得分更高
    repo.save(_make_fm("kb-rank-a", "Python"),
              "Python " * 10)
    _sync_fts(config, "kb-rank-a", "Python", "Python " * 10, "private")
    # Doc B：Python 仅出现一次，长文档 → BM25 得分更低
    long_content = ("A brief introduction to Python for beginners "
                    "covering many different topics and subjects "
                    "in software engineering and computer science.")
    repo.save(_make_fm("kb-rank-b", "Intro"), long_content)
    _sync_fts(config, "kb-rank-b", "Intro", long_content, "private")

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher._keyword_search("Python", "private", top_k=10)

    assert len(results) >= 2
    # 出现频次更高、文档更短的 Doc A 应排在前面
    assert results[0].doc_id == "kb-rank-a"
    assert results[1].doc_id == "kb-rank-b"
    # score 也应更高
    assert results[0].score >= results[1].score


def test_fts5_scope_filter(tmp_path):
    """Test 3: FTS5 搜索的 scope 过滤只返回匹配作用域的文档。"""
    config, repo, store = _setup_kb(tmp_path)
    # 两个文档内容相同但 scope 不同
    repo.save(_make_fm("kb-scope-priv", "Python Private", scope="private"),
              "Python tutorial content")
    _sync_fts(config, "kb-scope-priv", "Python Private",
              "Python tutorial content", "private")

    repo.save(_make_fm("kb-scope-pub", "Python Public", scope="public"),
              "Python tutorial content")
    _sync_fts(config, "kb-scope-pub", "Python Public",
              "Python tutorial content", "public")

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)

    # 搜索 private scope → 只返回 private 文档
    priv_results = searcher._keyword_search("Python", "private", top_k=10)
    priv_ids = [r.doc_id for r in priv_results]
    assert "kb-scope-priv" in priv_ids
    assert "kb-scope-pub" not in priv_ids
    assert all(r.scope == "private" for r in priv_results)

    # 搜索 public scope → 只返回 public 文档
    pub_results = searcher._keyword_search("Python", "public", top_k=10)
    pub_ids = [r.doc_id for r in pub_results]
    assert "kb-scope-pub" in pub_ids
    assert "kb-scope-priv" not in pub_ids
    assert all(r.scope == "public" for r in pub_results)


def test_fts5_empty_query_returns_empty(tmp_path):
    """Test 4: 空查询返回空列表。"""
    config, repo, store = _setup_kb(tmp_path)
    repo.save(_make_fm("kb-empty-001", "Some Doc"), "Some content here.")
    _sync_fts(config, "kb-empty-001", "Some Doc", "Some content here.", "private")

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)

    assert searcher._keyword_search("", "private", top_k=10) == []
    assert searcher._keyword_search("   ", "private", top_k=10) == []


def test_fts5_fallback_when_db_missing(tmp_path):
    """Test 5: meta.db 不存在时降级到暴力扫描。"""
    config, repo, store = _setup_kb(tmp_path)
    # 只保存到 repo，不写入 FTS5（meta.db 不存在）
    repo.save(_make_fm("kb-fb-001", "Python Fallback"),
              "Python fallback brute force search test.")
    repo.save(_make_fm("kb-fb-002", "Other Doc"),
              "Completely unrelated content about cooking.")

    # 确认 meta.db 不存在
    assert not config.meta_db.exists()

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    # search() 集成测试：methods=["keyword"] 走关键词路径
    results = searcher.search(
        query="Python", scope="private", top_k=10, methods=["keyword"]
    )

    # 暴力扫描应能找到包含 Python 的文档
    doc_ids = [r.doc_id for r in results]
    assert "kb-fb-001" in doc_ids
    assert "kb-fb-002" not in doc_ids
    assert all(r.source_method == "keyword" for r in results)


def test_fts5_fallback_when_table_empty(tmp_path):
    """Test 5b: FTS5 表存在但为空时降级到暴力扫描。"""
    config, repo, store = _setup_kb(tmp_path)
    repo.save(_make_fm("kb-fb-empty-001", "Python Doc"),
              "Python content for empty fts table test.")

    # 创建 meta.db 和 FTS5 表，但不插入任何数据
    from server.kb.retrieval.hybrid import ensure_fts_table
    config.meta_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(config.meta_db)) as conn:
        ensure_fts_table(conn)  # 建表但不插入

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher._keyword_search("Python", "private", top_k=10)

    # 表为空 → 降级到暴力扫描 → 应找到文档
    doc_ids = [r.doc_id for r in results]
    assert "kb-fb-empty-001" in doc_ids


def test_fts5_chinese_content(tmp_path):
    """附加：FTS5 支持 CJK 中文内容检索。"""
    config, repo, store = _setup_kb(tmp_path)
    repo.save(_make_fm("kb-cn-001", "Python 编程指南"),
              "这是一篇关于 Python 编程的入门指南。")
    _sync_fts(config, "kb-cn-001", "Python 编程指南",
              "这是一篇关于 Python 编程的入门指南。", "private")

    repo.save(_make_fm("kb-cn-002", "烹饪手册"),
              "今天教大家做红烧肉和番茄炒蛋。")
    _sync_fts(config, "kb-cn-002", "烹饪手册",
              "今天教大家做红烧肉和番茄炒蛋。", "private")

    from server.kb.retrieval.hybrid import HybridSearcher
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher._keyword_search("Python", "private", top_k=10)

    doc_ids = [r.doc_id for r in results]
    assert "kb-cn-001" in doc_ids
    assert "kb-cn-002" not in doc_ids
