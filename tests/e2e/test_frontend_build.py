# -*- coding: utf-8 -*-
"""前端构建产物测试 - Pangu Nebula (Phase 11D)

验证前端构建产物存在且结构正确:
- frontend/dist/index.html 存在
- frontend/dist/assets/ 目录存在
- index.html 包含 '<div id="app">'

如果 dist/ 不存在,标记为 skip(需要先构建前端)。
"""

import os

import pytest

# 项目根目录(tests/e2e/ 往上两级)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
INDEX_HTML = os.path.join(FRONTEND_DIST, "index.html")
ASSETS_DIR = os.path.join(FRONTEND_DIST, "assets")


@pytest.fixture(scope="module")
def dist_available():
    """检查 frontend/dist/ 是否存在,不存在则跳过整个模块。"""
    if not os.path.isdir(FRONTEND_DIST):
        pytest.skip(f"前端构建产物不存在: {FRONTEND_DIST}(请先运行 npm run build)")
    return FRONTEND_DIST


def test_index_html_exists(dist_available):
    """测试 frontend/dist/index.html 存在。"""
    assert os.path.isfile(INDEX_HTML), f"index.html 不存在: {INDEX_HTML}"
    print(f"[OK] index.html 存在: {INDEX_HTML}")


def test_assets_dir_exists(dist_available):
    """测试 frontend/dist/assets/ 目录存在。"""
    assert os.path.isdir(ASSETS_DIR), f"assets 目录不存在: {ASSETS_DIR}"
    files = os.listdir(ASSETS_DIR)
    assert len(files) > 0, f"assets 目录为空: {ASSETS_DIR}"
    print(f"[OK] assets 目录存在,包含 {len(files)} 个文件: {files}")


def test_index_html_has_app_div(dist_available):
    """测试 index.html 包含 '<div id="app">'。"""
    if not os.path.isfile(INDEX_HTML):
        pytest.skip("index.html 不存在")
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    assert '<div id="app">' in content, (
        f"index.html 未包含 '<div id=\"app\">': {INDEX_HTML}"
    )
    print(f"[OK] index.html 包含应用挂载点 '<div id=\"app\">'")
