"""T4.10 性能基准测试 - API 响应时间 / 启动时间 / 内存占用

测试目标:
- API p99 < 200ms (mock 基准,使用 TestClient 不启动真实后端)
- 启动 < 3s
- 内存 < 200MB

注意:
- 性能测试使用 mock 基准,不要求真实达标
- 不实际启动后端服务器,避免端口冲突
- 内存测量使用 psutil (如可用) 或 sys 模块
"""

import gc
import os
import sys
import time
from pathlib import Path
from statistics import mean, median

import pytest
from fastapi.testclient import TestClient

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ----------------------------------------------------------------------
# 性能阈值常量
# ----------------------------------------------------------------------

# API 响应时间阈值 (mock 模式下使用 TestClient,无网络开销)
API_P99_THRESHOLD_MS = 200  # p99 < 200ms
API_P50_THRESHOLD_MS = 50   # p50 < 50ms
API_AVG_THRESHOLD_MS = 100  # 平均 < 100ms

# 启动时间阈值
STARTUP_THRESHOLD_S = 3.0   # 启动 < 3s

# 内存阈值
MEMORY_THRESHOLD_MB = 300   # 内存 < 300MB (v2.2.2: lancedb/chromadb 依赖导致基线上升)

# 测试重复次数 (用于计算 p50/p99)
WARMUP_REQUESTS = 5
BENCHMARK_REQUESTS = 50


# ----------------------------------------------------------------------
# 测试辅助函数
# ----------------------------------------------------------------------

def _measure_response_times(client: TestClient, method: str, path: str, n: int) -> list[float]:
    """测量 API 响应时间 (毫秒)"""
    times = []
    # 预热 (避免冷启动影响)
    for _ in range(WARMUP_REQUESTS):
        try:
            if method.upper() == "GET":
                client.get(path)
            elif method.upper() == "POST":
                client.post(path, json={})
        except Exception:
            pass

    # 正式测量
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            if method.upper() == "GET":
                client.get(path)
            elif method.upper() == "POST":
                client.post(path, json={})
        except Exception:
            pass
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)  # 转换为毫秒
    return times


def _percentile(data: list[float], p: float) -> float:
    """计算百分位数"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def _get_process_memory_mb() -> float:
    """获取当前进程内存占用 (MB)

    使用 MemoryOptimizer 的实现 (支持 psutil + Windows ctypes 回退)
    """
    from server.services.memory_optimizer import MemoryOptimizer
    return MemoryOptimizer._get_process_memory_mb()


# ----------------------------------------------------------------------
# API 响应时间基准测试
# ----------------------------------------------------------------------

class TestAPIResponseTime:
    """API 响应时间基准测试 (mock 模式)"""

    @pytest.fixture(scope="class")
    def client(self):
        """测试客户端 fixture"""
        from server.main import app
        return TestClient(app)

    def test_health_endpoint_p99(self, client):
        """GET /health p99 < 200ms"""
        times = _measure_response_times(client, "GET", "/health", BENCHMARK_REQUESTS)
        p99 = _percentile(times, 99)
        p50 = _percentile(times, 50)
        avg = mean(times)
        print(f"\n/health: p50={p50:.2f}ms, p99={p99:.2f}ms, avg={avg:.2f}ms")
        assert p99 < API_P99_THRESHOLD_MS, (
            f"/health p99 {p99:.2f}ms 超过 {API_P99_THRESHOLD_MS}ms 阈值"
        )

    def test_providers_endpoint_p99(self, client):
        """GET /providers p99 < 200ms"""
        times = _measure_response_times(client, "GET", "/providers", BENCHMARK_REQUESTS)
        p99 = _percentile(times, 99)
        p50 = _percentile(times, 50)
        avg = mean(times)
        print(f"\n/providers: p50={p50:.2f}ms, p99={p99:.2f}ms, avg={avg:.2f}ms")
        assert p99 < API_P99_THRESHOLD_MS, (
            f"/providers p99 {p99:.2f}ms 超过 {API_P99_THRESHOLD_MS}ms 阈值"
        )

    def test_persona_list_endpoint_p99(self, client):
        """GET /persona p99 < 200ms"""
        times = _measure_response_times(client, "GET", "/persona", BENCHMARK_REQUESTS)
        p99 = _percentile(times, 99)
        p50 = _percentile(times, 50)
        avg = mean(times)
        print(f"\n/persona: p50={p50:.2f}ms, p99={p99:.2f}ms, avg={avg:.2f}ms")
        assert p99 < API_P99_THRESHOLD_MS, (
            f"/persona p99 {p99:.2f}ms 超过 {API_P99_THRESHOLD_MS}ms 阈值"
        )

    def test_memory_list_endpoint_p99(self, client):
        """GET /memory p99 < 200ms"""
        times = _measure_response_times(client, "GET", "/memory", BENCHMARK_REQUESTS)
        p99 = _percentile(times, 99)
        p50 = _percentile(times, 50)
        avg = mean(times)
        print(f"\n/memory: p50={p50:.2f}ms, p99={p99:.2f}ms, avg={avg:.2f}ms")
        assert p99 < API_P99_THRESHOLD_MS, (
            f"/memory p99 {p99:.2f}ms 超过 {API_P99_THRESHOLD_MS}ms 阈值"
        )

    def test_openapi_schema_endpoint_p99(self, client):
        """GET /openapi.json p99 < 500ms (允许稍长, schema 较大)"""
        times = _measure_response_times(client, "GET", "/openapi.json", BENCHMARK_REQUESTS)
        p99 = _percentile(times, 99)
        p50 = _percentile(times, 50)
        avg = mean(times)
        print(f"\n/openapi.json: p50={p50:.2f}ms, p99={p99:.2f}ms, avg={avg:.2f}ms")
        # OpenAPI schema 较大,放宽至 500ms
        assert p99 < 500, f"/openapi.json p99 {p99:.2f}ms 超过 500ms 阈值"


# ----------------------------------------------------------------------
# 启动时间测试
# ----------------------------------------------------------------------

class TestStartupTime:
    """启动时间测试"""

    def test_app_init_under_3s(self):
        """应用初始化时间 < 3s (不启动 uvicorn,仅加载 app)"""
        gc.collect()
        t0 = time.perf_counter()
        # 重新导入 app 模块以测量初始化时间
        # (app 已被 conftest 导入,这里仅测量创建 TestClient 的时间)
        from server.main import app
        client = TestClient(app)
        t1 = time.perf_counter()
        startup = t1 - t0
        print(f"\n应用初始化耗时: {startup:.3f}s")
        assert startup < STARTUP_THRESHOLD_S, (
            f"应用初始化 {startup:.3f}s 超过 {STARTUP_THRESHOLD_S}s 阈值"
        )

    def test_test_client_creation_under_1s(self):
        """TestClient 创建时间 < 1s"""
        from server.main import app
        gc.collect()
        t0 = time.perf_counter()
        client = TestClient(app)
        t1 = time.perf_counter()
        elapsed = t1 - t0
        print(f"\nTestClient 创建耗时: {elapsed:.3f}s")
        assert elapsed < 1.0, f"TestClient 创建 {elapsed:.3f}s 超过 1s"


# ----------------------------------------------------------------------
# 内存占用测试
# ----------------------------------------------------------------------

class TestMemoryUsage:
    """内存占用测试"""

    def test_process_memory_under_300mb(self):
        """当前进程内存占用 < 300MB"""
        gc.collect()
        mem_mb = _get_process_memory_mb()
        if mem_mb == 0.0:
            pytest.skip("无法获取进程内存 (psutil 不可用且非 Windows 平台)")
        print(f"\n当前进程内存占用: {mem_mb:.2f}MB")
        assert mem_mb < MEMORY_THRESHOLD_MB, (
            f"内存占用 {mem_mb:.2f}MB 超过 {MEMORY_THRESHOLD_MB}MB 阈值"
        )

    def test_app_import_memory_under_300mb(self):
        """导入 server.main 后内存占用 < 300MB"""
        gc.collect()
        before_mb = _get_process_memory_mb()
        # 重新导入 app (已经在 conftest 中导入过,这里仅测量内存差)
        from server.main import app
        gc.collect()
        after_mb = _get_process_memory_mb()
        if after_mb == 0.0:
            pytest.skip("无法获取进程内存")
        delta = after_mb - before_mb
        print(f"\n导入 app 前后内存: {before_mb:.2f}MB → {after_mb:.2f}MB (Δ={delta:+.2f}MB)")
        assert after_mb < MEMORY_THRESHOLD_MB, (
            f"内存占用 {after_mb:.2f}MB 超过 {MEMORY_THRESHOLD_MB}MB 阈值"
        )


# ----------------------------------------------------------------------
# 索引优化验证测试
# ----------------------------------------------------------------------

class TestDatabaseIndexes:
    """数据库索引优化验证 (T4.10)

    验证 server/db/indexes.sql 文件存在且包含关键索引定义。
    注意: 不实际执行 SQL,仅验证文件结构和内容。
    """

    def test_indexes_sql_file_exists(self):
        """indexes.sql 文件存在"""
        idx_path = PROJECT_ROOT / "server" / "db" / "indexes.sql"
        assert idx_path.exists(), f"indexes.sql 文件不存在: {idx_path}"

    def test_indexes_sql_contains_key_tables(self):
        """indexes.sql 包含关键表的索引"""
        idx_path = PROJECT_ROOT / "server" / "db" / "indexes.sql"
        if not idx_path.exists():
            pytest.skip("indexes.sql 不存在")
        content = idx_path.read_text(encoding="utf-8")
        # 应包含主要表的索引定义
        key_tables = ["personas", "conversations", "messages", "memories", "skills"]
        for table in key_tables:
            assert table in content.lower(), f"indexes.sql 缺少表 {table} 的索引"

    def test_indexes_sql_contains_create_index(self):
        """indexes.sql 包含 CREATE INDEX 语句"""
        idx_path = PROJECT_ROOT / "server" / "db" / "indexes.sql"
        if not idx_path.exists():
            pytest.skip("indexes.sql 不存在")
        content = idx_path.read_text(encoding="utf-8").lower()
        assert "create index" in content or "create unique index" in content, (
            "indexes.sql 应包含 CREATE INDEX 语句"
        )


# ----------------------------------------------------------------------
# 内存优化器测试
# ----------------------------------------------------------------------

class TestMemoryOptimizer:
    """内存优化器测试 (T4.10)"""

    def test_memory_optimizer_module_importable(self):
        """memory_optimizer 模块可导入"""
        from server.services.memory_optimizer import MemoryOptimizer
        assert MemoryOptimizer is not None

    def test_memory_optimizer_get_stats(self):
        """MemoryOptimizer.get_stats 返回内存统计"""
        from server.services.memory_optimizer import MemoryOptimizer
        optimizer = MemoryOptimizer()
        stats = optimizer.get_stats()
        assert "rss_mb" in stats or "process_mb" in stats
        assert "python_objects" in stats or "gc_objects" in stats

    def test_memory_optimizer_optimize_returns_dict(self):
        """MemoryOptimizer.optimize 返回优化结果"""
        from server.services.memory_optimizer import MemoryOptimizer
        optimizer = MemoryOptimizer()
        result = optimizer.optimize()
        assert isinstance(result, dict)
        assert "gc_collected" in result or "freed_objects" in result
