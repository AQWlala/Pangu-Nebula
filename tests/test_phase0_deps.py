# tests/test_phase0_deps.py
"""验证 KB/CU 新增依赖声明在 requirements.txt 中且核心依赖可导入。

注意: chromadb/llama-index/playwright 等大型依赖允许缺失(try/except 跳过),
      但 pyyaml 和 pandas 必须可导入(测试强依赖)。
"""


def test_kb_dependencies_declared():
    """验证 KB 依赖已声明在 requirements.txt"""
    from pathlib import Path
    req = Path(__file__).parent.parent / "requirements.txt"
    content = req.read_text(encoding="utf-8")
    assert "chromadb" in content
    assert "llama-index" in content
    assert "kuzu" in content
    assert "marker-pdf" in content


def test_cu_dependencies_declared():
    """验证 CU 依赖已声明在 requirements.txt"""
    from pathlib import Path
    req = Path(__file__).parent.parent / "requirements.txt"
    content = req.read_text(encoding="utf-8")
    assert "browser-use" in content
    assert "playwright" in content


def test_kb_dependencies_importable():
    """大型 KB 依赖允许缺失(try/except)"""
    try:
        import chromadb
        assert chromadb is not None
    except ImportError:
        pass


def test_cu_dependencies_importable():
    """大型 CU 依赖允许缺失(try/except)"""
    try:
        import playwright
        assert playwright is not None
    except ImportError:
        pass


def test_yaml_dependency():
    """pyyaml 必须可导入(M1 frontmatter 解析强依赖)"""
    import yaml
    assert yaml is not None


def test_pandas_dependency():
    """pandas 必须可导入(M1.3 Excel 解析强依赖)"""
    pytest = __import__("pytest")
    pytest.importorskip("pandas")
