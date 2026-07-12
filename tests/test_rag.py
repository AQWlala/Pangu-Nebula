"""Tests for RAG 索引服务 (T2.8)。

覆盖:
- 索引构建/更新/移除
- 语义检索(返回 top-k 相关条目)
- 检索准确率 ≥ 75%(mock TF-IDF 实现)
- L3 验证(verify endpoint)
- 批量索引所有 WikiPage
"""

import pytest

from server.services.rag_service import RAGService
from server.db.orm import WikiPage


class TestRAGIndexing:
    """T2.8: 索引构建与维护"""

    def test_index_single_document(self):
        """索引单个文档后状态应显示该文档"""
        svc = RAGService()
        doc = svc.index_wiki_page(1, "Python 入门", "Python 是一种解释型编程语言")
        assert doc.doc_id == "wiki:1"
        assert doc.wiki_id == 1
        assert doc.title == "Python 入门"
        status = svc.get_status()
        assert status["doc_count"] == 1
        assert len(status["indexed_docs"]) == 1
        assert status["indexed_docs"][0]["doc_id"] == "wiki:1"

    def test_index_updates_existing_document(self):
        """对同一 wiki_id 重复索引应更新而非追加"""
        svc = RAGService()
        svc.index_wiki_page(1, "旧标题", "旧内容")
        svc.index_wiki_page(1, "新标题", "新内容已更新")
        status = svc.get_status()
        assert status["doc_count"] == 1  # 仍为 1,不重复
        assert status["indexed_docs"][0]["title"] == "新标题"

    def test_remove_document(self):
        """移除文档后索引应不再包含该文档"""
        svc = RAGService()
        svc.index_wiki_page(1, "Test", "content")
        assert svc.get_status()["doc_count"] == 1
        removed = svc.remove_document("wiki:1")
        assert removed is True
        assert svc.get_status()["doc_count"] == 0
        # 再次移除应返回 False
        removed_again = svc.remove_document("wiki:1")
        assert removed_again is False

    def test_clear_index(self):
        """清空索引应移除所有文档"""
        svc = RAGService()
        svc.index_wiki_page(1, "A", "content A")
        svc.index_wiki_page(2, "B", "content B")
        assert svc.get_status()["doc_count"] == 2
        svc.clear()
        status = svc.get_status()
        assert status["doc_count"] == 0
        assert status["vocabulary_size"] == 0


class TestRAGSearch:
    """T2.8: 语义检索"""

    def test_search_empty_index(self):
        """空索引检索应返回空列表"""
        svc = RAGService()
        results = svc.search("任意查询")
        assert results == []

    def test_search_empty_query(self):
        """空查询应返回空列表"""
        svc = RAGService()
        svc.index_wiki_page(1, "Test", "some content")
        results = svc.search("")
        assert results == []
        results = svc.search("   ")
        assert results == []

    def test_search_returns_relevant_results(self):
        """检索应返回最相关的文档排在第一位"""
        svc = RAGService()
        svc.index_wiki_page(1, "Python 入门", "Python 是一种解释型编程语言,支持面向对象")
        svc.index_wiki_page(2, "机器学习", "机器学习是人工智能的一个分支")
        results = svc.search("Python 编程")
        assert len(results) > 0
        assert results[0].wiki_id == 1
        assert results[0].score > 0

    def test_search_accuracy_meets_threshold(self):
        """检索准确率 ≥ 75%: 5 个查询中至少 4 个 top-1 正确"""
        svc = RAGService()
        # 5 篇不同主题的 Wiki
        docs = [
            (1, "Python 编程语言入门", "Python 是一种广泛使用的解释型高级编程语言,由 Guido 创建"),
            (2, "机器学习算法概述", "机器学习是人工智能的核心分支,包括监督学习无监督学习和强化学习"),
            (3, "数据库设计原理", "关系型数据库使用 SQL 语言进行操作,包括 MySQL PostgreSQL 等"),
            (4, "前端开发框架对比", "前端框架包括 React Vue Angular 等,用于构建用户界面"),
            (5, "网络安全最佳实践", "网络安全涉及加密认证授权,保护系统免受攻击"),
        ]
        for wid, title, content in docs:
            svc.index_wiki_page(wid, title, content)

        # 5 个查询,期望的 top-1 wiki_id
        queries = [
            ("Python 是什么", 1),
            ("机器学习", 2),
            ("数据库 SQL", 3),
            ("前端框架", 4),
            ("网络安全", 5),
        ]
        correct = 0
        for query, expected_id in queries:
            results = svc.search(query, top_k=1)
            if results and results[0].wiki_id == expected_id:
                correct += 1
        accuracy = correct / len(queries)
        assert accuracy >= 0.75, f"检索准确率 {accuracy:.0%} 低于 75% 阈值(正确 {correct}/{len(queries)})"

    def test_search_top_k_limit(self):
        """top_k 参数应限制返回结果数量"""
        svc = RAGService()
        for i in range(10):
            svc.index_wiki_page(i, f"Doc {i}", f"文档 {i} 的内容")
        results = svc.search("文档", top_k=3)
        assert len(results) <= 3

    def test_search_results_sorted_by_score(self):
        """检索结果应按相似度降序排列"""
        svc = RAGService()
        svc.index_wiki_page(1, "Python", "Python programming language")
        svc.index_wiki_page(2, "Java", "Java programming language")
        svc.index_wiki_page(3, "Cooking", "recipe for cooking pasta")
        results = svc.search("programming", top_k=3)
        if len(results) >= 2:
            for i in range(1, len(results)):
                assert results[i - 1].score >= results[i].score


class TestRAGVerify:
    """T2.8: L3 语义验证"""

    def test_verify_passes_with_strong_match(self):
        """强匹配应验证通过"""
        svc = RAGService()
        svc.index_wiki_page(1, "Python 入门", "Python 是一种解释型编程语言")
        result = svc.verify("Python 编程语言")
        assert result.verified is True
        assert result.best_score >= svc.VERIFY_THRESHOLD
        assert result.best_match is not None
        assert result.best_match.wiki_id == 1

    def test_verify_fails_with_weak_match(self):
        """弱匹配应验证不通过"""
        svc = RAGService()
        svc.index_wiki_page(1, "Python 入门", "Python 是一种解释型编程语言")
        result = svc.verify("烹饪食谱")
        assert result.verified is False
        assert result.best_score < svc.VERIFY_THRESHOLD or result.best_match is None

    def test_verify_custom_threshold(self):
        """自定义阈值应生效"""
        svc = RAGService()
        svc.index_wiki_page(1, "Python", "Python programming")
        # 用极高阈值 → 不通过
        result_high = svc.verify("Python", threshold=0.99)
        assert result_high.verified is False
        assert result_high.threshold == 0.99
        # 用极低阈值 → 通过
        result_low = svc.verify("Python", threshold=0.0)
        assert result_low.verified is True

    def test_verify_empty_index(self):
        """空索引验证应返回 verified=False"""
        svc = RAGService()
        result = svc.verify("任意查询")
        assert result.verified is False
        assert result.best_score == 0.0
        assert result.best_match is None


class TestRAGBatchIndex:
    """T2.8: 批量索引 WikiPage 表"""

    @pytest.mark.asyncio
    async def test_index_all_wiki_pages(self, db_session):
        """批量索引应处理所有有内容的 WikiPage"""
        # 创建 3 个 WikiPage,其中 1 个内容为空
        db_session.add(WikiPage(title="有内容A", content="Python 编程语言"))
        db_session.add(WikiPage(title="有内容B", content="机器学习算法"))
        db_session.add(WikiPage(title="空内容", content=""))
        await db_session.commit()

        svc = RAGService()
        result = await svc.index_all_wiki_pages(db_session)
        assert result["indexed"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == []
        assert svc.get_status()["doc_count"] == 2

    @pytest.mark.asyncio
    async def test_index_all_uses_plain_text_fallback(self, db_session):
        """批量索引应优先使用 plain_text,回退到 content"""
        db_session.add(
            WikiPage(
                title="测试",
                content="markdown 原文",
                plain_text="纯文本内容 Python",
            )
        )
        await db_session.commit()

        svc = RAGService()
        await svc.index_all_wiki_pages(db_session)
        results = svc.search("Python")
        assert len(results) > 0
        assert results[0].wiki_id is not None
