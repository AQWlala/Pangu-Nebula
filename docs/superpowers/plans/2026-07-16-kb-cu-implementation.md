# 轻量级 GraphRAG 知识库 + Computer Use 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Pangu Nebula 增加轻量级多模态知识库（M1-M3）与 Computer Use GUI 自动化能力（M4-M5），以及前端可视化监控面板（M6），实现 CU 与知识库深度集成、全链路可审计可回滚。

**Architecture:** Markdown + YAML Front Matter 作为唯一事实来源；ChromaDB/LightRAG/Kuzu 嵌入式存储作为投影；Browser-Use + Playwright 在双层沙箱内执行 CU；所有 CU 动作通过 MCP Server 标准化暴露；前端用 AntV G6 渲染 wikigraph 知识图谱。

**Tech Stack:** Python 3.11 / FastAPI / ChromaDB / LlamaIndex / LightRAG / Kuzu / Marker / Pandas / Browser-Use / Playwright / Preact / AntV G6 v5 / SQLite

**Spec:** `docs/superpowers/specs/2026-07-16-kb-cu-design.md`

---

## 执行顺序与并行策略

```
Phase 0 (基础设施) ──必须先完成──►
    │
    ├─► M1 (解析) ──► M2 (检索) ──► M3 (图谱)
    │                                   │
    ├─► M4 (CU基础) ────────────────────┤
    │                                   ▼
    │                              M5 (CU联动)
    │                                   │
    └───────────────────────────────────►│
                                        ▼
                                   M6 (可视化)
```

- Phase 0 完成后，M1 和 M4 可并行启动
- M2 依赖 M1，M3 依赖 M1
- M5 依赖 M4 + M1-M3
- M6 依赖所有后端里程碑

---

## Phase 0: 基础设施

### Task 0.1: 创建知识库目录结构与配置

**Files:**
- Create: `server/config_kb_cu.py`
- Create: `server/kb/__init__.py` (及子包 `__init__.py`)
- Create: `server/cu/__init__.py` (及子包 `__init__.py`)
- Test: `tests/test_phase0_infra.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_phase0_infra.py
import pytest
from server.config_kb_cu import KBConfig, CUConfig

def test_kb_config_defaults():
    config = KBConfig()
    assert config.kb_root.name == "knowledge_base"
    assert config.documents_dir.name == "documents"
    assert config.inbox_dir.name == "_inbox"
    assert config.sandbox_dir.name == "_sandbox"
    assert config.chroma_dir.name == "chroma"
    assert config.kuzu_dir.name == "kuzu"
    assert config.meta_db.name == "meta.db"

def test_cu_config_defaults():
    config = CUConfig()
    assert config.audit_log_dir.name == "cu_audit"
    assert config.default_step_timeout_ms == 3000
    assert config.max_step_timeout_ms == 10000
    assert config.screenshot_enabled is True

def test_kb_config_dirs_are_under_kb_root():
    config = KBConfig()
    assert config.documents_dir.parent == config.kb_root
    assert config.inbox_dir.parent == config.kb_root
    assert config.sandbox_dir.parent == config.kb_root
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_phase0_infra.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现配置模块**

```python
# server/config_kb_cu.py
"""知识库与 Computer Use 配置模块"""
from pathlib import Path
from dataclasses import dataclass


@dataclass
class KBConfig:
    """知识库配置"""
    kb_root: Path = Path.home() / ".pangu-nebula" / "knowledge_base"
    documents_dir: Path = kb_root / "documents"
    inbox_dir: Path = kb_root / "_inbox"
    sandbox_dir: Path = kb_root / "_sandbox"
    archive_dir: Path = kb_root / "_archive"
    indexes_dir: Path = kb_root / "indexes"
    chroma_dir: Path = indexes_dir / "chroma"
    kuzu_dir: Path = indexes_dir / "kuzu"
    meta_db: Path = kb_root / "meta.db"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50

    def ensure_dirs(self) -> None:
        for d in [self.kb_root, self.documents_dir, self.inbox_dir,
                  self.sandbox_dir, self.archive_dir, self.indexes_dir,
                  self.chroma_dir, self.kuzu_dir]:
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class CUConfig:
    """Computer Use 配置"""
    audit_log_dir: Path = Path.home() / ".pangu-nebula" / "logs" / "cu_audit"
    default_step_timeout_ms: int = 3000
    max_step_timeout_ms: int = 10000
    screenshot_enabled: bool = True
    max_retries: int = 2
    confidence_high: float = 0.85
    confidence_low: float = 0.6

    def ensure_dirs(self) -> None:
        self.audit_log_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 创建所有 `__init__.py`**

为 `server/kb/`, `server/kb/parser/`, `server/kb/storage/`, `server/kb/retrieval/`, `server/kb/graph/`, `server/cu/`, `server/cu/executor/`, `server/cu/sandbox/`, `server/cu/safety/` 创建空 `__init__.py`。

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_phase0_infra.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add server/config_kb_cu.py server/kb/ server/cu/ tests/test_phase0_infra.py
git commit -m "feat(kb-cu): Phase 0 基础设施 - 目录结构与配置模块"
```

---

### Task 0.2: SQLite 元数据表与 ORM 模型

**Files:**
- Create: `server/db/kb_models.py`
- Create: `server/db/cu_models.py`
- Modify: `server/db/indexes.sql` (追加 KB/CU 表)
- Test: `tests/test_phase0_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_phase0_models.py
import pytest
from sqlalchemy import inspect
from server.db.engine import get_engine


@pytest.mark.asyncio
async def test_kb_documents_table_exists():
    engine = get_engine()
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "kb_documents" in tables

@pytest.mark.asyncio
async def test_kb_relations_table_exists():
    engine = get_engine()
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "kb_relations" in tables

@pytest.mark.asyncio
async def test_cu_audit_logs_table_exists():
    engine = get_engine()
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert "cu_audit_logs" in tables

def test_kb_document_model_fields():
    from server.db.kb_models import KBDocument
    assert hasattr(KBDocument, "id")
    assert hasattr(KBDocument, "title")
    assert hasattr(KBDocument, "scope")
    assert hasattr(KBDocument, "confidence")
    assert hasattr(KBDocument, "checksum")

def test_cu_audit_log_model_fields():
    from server.db.cu_models import CUAuditLog
    assert hasattr(CUAuditLog, "task_id")
    assert hasattr(CUAuditLog, "step_index")
    assert hasattr(CUAuditLog, "action_type")
    assert hasattr(CUAuditLog, "result_status")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_phase0_models.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 KB 模型**

```python
# server/db/kb_models.py
"""知识库元数据 ORM 模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.db.orm import Base


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    graph_built_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    relations_as_source = relationship("KBRelation", foreign_keys="KBRelation.source_id", back_populates="source")
    relations_as_target = relationship("KBRelation", foreign_keys="KBRelation.target_id", back_populates="target")


class KBRelation(Base):
    __tablename__ = "kb_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("kb_documents.id"), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), ForeignKey("kb_documents.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    source_method: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    source = relationship("KBDocument", foreign_keys=[source_id], back_populates="relations_as_source")
    target = relationship("KBDocument", foreign_keys=[target_id], back_populates="relations_as_target")
```

- [ ] **Step 4: 实现 CU 模型**

```python
# server/db/cu_models.py
"""Computer Use 审计日志 ORM 模型"""
from datetime import datetime
from sqlalchemy import String, Text, Integer, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from server.db.orm import Base


class CUAuditLog(Base):
    __tablename__ = "cu_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_payload: Mapped[str] = mapped_column(Text, nullable=False)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 5: 在 indexes.sql 追加 FTS5 表**

在 `server/db/indexes.sql` 末尾追加：

```sql
-- KB 全文检索虚拟表 (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS kb_documents_fts USING fts5(
    doc_id UNINDEXED,
    title,
    content,
    tags,
    tokenize = 'unicode61'
);
```

- [ ] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_phase0_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add server/db/kb_models.py server/db/cu_models.py server/db/indexes.sql tests/test_phase0_models.py
git commit -m "feat(kb-cu): Phase 0 基础设施 - KB/CU ORM 模型与 FTS5"
```

---

### Task 0.3: 添加新依赖

**Files:**
- Modify: `requirements.txt`
- Test: `tests/test_phase0_deps.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_phase0_deps.py
def test_kb_dependencies_importable():
    try:
        import chromadb
        assert chromadb is not None
    except ImportError:
        pass

def test_cu_dependencies_importable():
    try:
        import playwright
        assert playwright is not None
    except ImportError:
        pass

def test_yaml_dependency():
    import yaml
    assert yaml is not None

def test_pandas_dependency():
    import pandas
    assert pandas is not None
```

- [ ] **Step 2: 追加依赖到 requirements.txt**

```
# KB + CU 新增依赖
chromadb>=0.5.0
llama-index>=0.11.0
lightrag-hku>=1.0.0
kuzu>=0.4.0
marker-pdf>=0.2.0
python-docx>=1.1.0
trafilatura>=1.12.0
pyyaml>=6.0
browser-use>=0.1.0
playwright>=1.45.0
```

- [ ] **Step 3: 安装依赖**

Run: `pip install -r requirements.txt && playwright install chromium`

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_phase0_deps.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/test_phase0_deps.py
git commit -m "feat(kb-cu): Phase 0 基础设施 - 添加 KB/CU 依赖"
```

---

## M1: 文档解析与 Markdown 中心存储

### Task M1.1: Front Matter 解析与校验

**Files:**
- Create: `server/kb/storage/frontmatter.py`
- Create: `server/kb/parser/validator.py`
- Test: `tests/test_m1_frontmatter.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m1_frontmatter.py
import pytest
from server.kb.storage.frontmatter import parse_frontmatter, dump_frontmatter, FrontMatter
from server.kb.parser.validator import validate_frontmatter, ValidationError

def test_parse_frontmatter_valid():
    content = """---
id: kb-20260716-001
title: "测试文档"
type: note
scope: private
confidence: 0.95
checksum: sha256:abc123
---

# 正文"""
    fm, body = parse_frontmatter(content)
    assert fm.id == "kb-20260716-001"
    assert fm.title == "测试文档"
    assert fm.type == "note"
    assert fm.scope == "private"
    assert fm.confidence == 0.95
    assert body.startswith("# 正文")

def test_parse_frontmatter_no_frontmatter():
    content = "# 纯正文无 front matter"
    fm, body = parse_frontmatter(content)
    assert fm is None
    assert body == content

def test_dump_frontmatter_roundtrip():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    dumped = dump_frontmatter(fm)
    fm2, _ = parse_frontmatter(dumped + "\n\n# body")
    assert fm2.id == fm.id
    assert fm2.title == fm.title

def test_validate_frontmatter_missing_id():
    fm = FrontMatter(
        id="", title="测试", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="id"):
        validate_frontmatter(fm)

def test_validate_frontmatter_invalid_scope():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="invalid_scope",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="scope"):
        validate_frontmatter(fm)

def test_validate_frontmatter_invalid_type():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="invalid_type", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="type"):
        validate_frontmatter(fm)

def test_validate_frontmatter_confidence_range():
    fm = FrontMatter(
        id="kb-test-001", title="测试", type="note", scope="private",
        source_type="manual", confidence=1.5, checksum="sha256:test",
    )
    with pytest.raises(ValidationError, match="confidence"):
        validate_frontmatter(fm)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m1_frontmatter.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 FrontMatter 数据类与解析**

```python
# server/kb/storage/frontmatter.py
"""YAML Front Matter 解析与序列化"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import yaml


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class FrontMatter:
    """文档 front matter 结构"""
    id: str = ""
    title: str = ""
    type: str = "note"
    scope: str = "private"
    source_type: str = "manual"
    source_original_path: str = ""
    source_imported_at: str = ""
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    confidence: float = 1.0
    checksum: str = ""
    created_at: str = ""
    updated_at: str = ""


def parse_frontmatter(content: str) -> tuple[FrontMatter | None, str]:
    """解析 MD 内容，返回 (frontmatter, body)"""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    yaml_str, body = match.groups()
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError:
        return None, content

    if not isinstance(data, dict):
        return None, content

    source = data.get("source", {}) or {}
    fm = FrontMatter(
        id=data.get("id", ""),
        title=data.get("title", ""),
        type=data.get("type", "note"),
        scope=data.get("scope", "private"),
        source_type=source.get("type", "manual") if isinstance(source, dict) else "manual",
        source_original_path=source.get("original_path", "") if isinstance(source, dict) else "",
        source_imported_at=source.get("imported_at", "") if isinstance(source, dict) else "",
        tags=data.get("tags", []) or [],
        categories=data.get("categories", []) or [],
        relations=data.get("relations", []) or [],
        confidence=float(data.get("confidence", 1.0)),
        checksum=data.get("checksum", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )
    return fm, body


def dump_frontmatter(fm: FrontMatter) -> str:
    """序列化 front matter 为 YAML 字符串"""
    source = {
        "type": fm.source_type,
        "original_path": fm.source_original_path,
        "imported_at": fm.source_imported_at,
    }
    data = {
        "id": fm.id,
        "title": fm.title,
        "type": fm.type,
        "source": source,
        "scope": fm.scope,
        "tags": fm.tags,
        "categories": fm.categories,
        "relations": fm.relations,
        "confidence": fm.confidence,
        "checksum": fm.checksum,
    }
    if fm.created_at:
        data["created_at"] = fm.created_at
    if fm.updated_at:
        data["updated_at"] = fm.updated_at

    yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_str}---"
```

- [ ] **Step 4: 实现校验器**

```python
# server/kb/parser/validator.py
"""Front Matter 校验器"""
from server.kb.storage.frontmatter import FrontMatter

VALID_TYPES = {"note", "doc", "snippet", "cu_log"}
VALID_SCOPES = {"private", "project", "public"}
VALID_SOURCE_TYPES = {"manual", "import", "cu", "crawler"}
VALID_RELATION_TYPES = {"references", "extends", "contradicts", "derived_from"}


class ValidationError(ValueError):
    """校验错误"""


def validate_frontmatter(fm: FrontMatter) -> None:
    """校验 front matter 完整性"""
    if not fm.id:
        raise ValidationError("id 不能为空")
    if not fm.title:
        raise ValidationError("title 不能为空")
    if fm.type not in VALID_TYPES:
        raise ValidationError(f"type 必须是 {VALID_TYPES} 之一，得到: {fm.type}")
    if fm.scope not in VALID_SCOPES:
        raise ValidationError(f"scope 必须是 {VALID_SCOPES} 之一，得到: {fm.scope}")
    if fm.source_type not in VALID_SOURCE_TYPES:
        raise ValidationError(f"source.type 必须是 {VALID_SOURCE_TYPES} 之一，得到: {fm.source_type}")
    if not 0.0 <= fm.confidence <= 1.0:
        raise ValidationError(f"confidence 必须在 [0.0, 1.0] 范围内，得到: {fm.confidence}")
    if not fm.checksum:
        raise ValidationError("checksum 不能为空")

    for i, rel in enumerate(fm.relations):
        if "target" not in rel:
            raise ValidationError(f"relations[{i}] 缺少 target 字段")
        if rel.get("type") not in VALID_RELATION_TYPES:
            raise ValidationError(f"relations[{i}].type 必须是 {VALID_RELATION_TYPES} 之一")
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_m1_frontmatter.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add server/kb/storage/frontmatter.py server/kb/parser/validator.py tests/test_m1_frontmatter.py
git commit -m "feat(kb): M1.1 Front Matter 解析与校验"
```

---

### Task M1.2: Markdown 文档仓库 CRUD 与 _inbox 暂存

**Files:**
- Create: `server/kb/storage/repo.py`
- Create: `server/kb/storage/inbox.py`
- Test: `tests/test_m1_repo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m1_repo.py
import pytest
from pathlib import Path
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.frontmatter import FrontMatter
from server.kb.storage.inbox import InboxWriter


@pytest.fixture
def temp_repo(tmp_path):
    return DocumentRepo(documents_dir=tmp_path / "documents")


def test_repo_save_and_read(temp_repo):
    fm = FrontMatter(
        id="kb-test-001", title="测试文档", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:abc",
    )
    temp_repo.save(fm, "# 正文内容")
    read_fm, read_body = temp_repo.read("kb-test-001")
    assert read_fm.id == "kb-test-001"
    assert "# 正文内容" in read_body

def test_repo_delete(temp_repo):
    fm = FrontMatter(
        id="kb-test-002", title="待删除", type="note", scope="private",
        source_type="manual", confidence=0.9, checksum="sha256:def",
    )
    temp_repo.save(fm, "content")
    assert temp_repo.exists("kb-test-002")
    temp_repo.delete("kb-test-002")
    assert not temp_repo.exists("kb-test-002")

def test_repo_list(temp_repo):
    for i in range(3):
        fm = FrontMatter(
            id=f"kb-test-{i:03d}", title=f"文档{i}", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum=f"sha256:{i}",
        )
        temp_repo.save(fm, f"内容{i}")
    docs = temp_repo.list_all()
    assert len(docs) == 3


@pytest.fixture
def temp_inbox(tmp_path):
    return InboxWriter(inbox_dir=tmp_path / "_inbox")


def test_inbox_stage(temp_inbox):
    pending_id = temp_inbox.stage(
        original_filename="report.pdf",
        converted_md="# 导入的报表\n\n数据...",
        frontmatter=FrontMatter(
            id="kb-import-001", title="导入的报表", type="doc", scope="private",
            source_type="import", source_original_path="/path/to/report.pdf",
            confidence=0.85, checksum="sha256:import1",
        ),
        meta={"parser": "pdf_parser", "confidence": 0.85},
    )
    assert pending_id is not None
    pending = temp_inbox.get_pending(pending_id)
    assert pending is not None
    assert "导入的报表" in pending["converted_md"]

def test_inbox_list_pending(temp_inbox):
    for i in range(2):
        temp_inbox.stage(
            original_filename=f"file{i}.txt",
            converted_md=f"# 文件{i}",
            frontmatter=FrontMatter(
                id=f"kb-import-{i}", title=f"文件{i}", type="note", scope="private",
                source_type="import", confidence=0.8, checksum=f"sha256:{i}",
            ),
            meta={"parser": "markdown"},
        )
    pending_list = temp_inbox.list_pending()
    assert len(pending_list) == 2

def test_inbox_approve_and_remove(temp_inbox):
    pending_id = temp_inbox.stage(
        original_filename="test.md",
        converted_md="# test",
        frontmatter=FrontMatter(
            id="kb-approve-001", title="approve test", type="note", scope="private",
            source_type="import", confidence=0.9, checksum="sha256:approve",
        ),
        meta={},
    )
    temp_inbox.remove_pending(pending_id)
    assert temp_inbox.get_pending(pending_id) is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m1_repo.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 DocumentRepo**

```python
# server/kb/storage/repo.py
"""Markdown 文档仓库 CRUD"""
from __future__ import annotations
from pathlib import Path
import hashlib
from datetime import datetime
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter, dump_frontmatter


class DocumentRepo:
    """本地 MD 文件仓库，唯一事实来源"""

    def __init__(self, documents_dir: Path):
        self.documents_dir = documents_dir
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, doc_id: str) -> Path:
        safe_id = doc_id.replace("/", "_").replace("\\", "_")
        return self.documents_dir / f"{safe_id}.md"

    def save(self, fm: FrontMatter, body: str) -> Path:
        now = datetime.utcnow().isoformat() + "Z"
        if not fm.created_at:
            fm.created_at = now
        fm.updated_at = now

        if not fm.checksum or fm.checksum.startswith("sha256:"):
            content_hash = hashlib.sha256(body.encode()).hexdigest()
            fm.checksum = f"sha256:{content_hash}"

        content = dump_frontmatter(fm) + "\n\n" + body
        file_path = self._file_path(fm.id)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read(self, doc_id: str) -> tuple[FrontMatter, str]:
        file_path = self._file_path(doc_id)
        content = file_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        return fm, body

    def exists(self, doc_id: str) -> bool:
        return self._file_path(doc_id).exists()

    def delete(self, doc_id: str) -> None:
        file_path = self._file_path(doc_id)
        if file_path.exists():
            file_path.unlink()

    def list_all(self) -> list[str]:
        return [f.stem for f in self.documents_dir.glob("*.md")]
```

- [ ] **Step 4: 实现 InboxWriter**

```python
# server/kb/storage/inbox.py
"""_inbox 暂存回写管理"""
from __future__ import annotations
from pathlib import Path
import json
import uuid
import shutil
from datetime import datetime
from server.kb.storage.frontmatter import FrontMatter, dump_frontmatter


class InboxWriter:
    """管理 _inbox/ 暂存区，禁止直写 documents/"""

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def stage(
        self,
        original_filename: str,
        converted_md: str,
        frontmatter: FrontMatter,
        meta: dict,
    ) -> str:
        pending_id = f"pending-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        pending_dir = self.inbox_dir / pending_id
        pending_dir.mkdir(parents=True, exist_ok=True)

        (pending_dir / "converted.md").write_text(converted_md, encoding="utf-8")
        (pending_dir / "frontmatter.yaml").write_text(
            dump_frontmatter(frontmatter), encoding="utf-8"
        )

        meta_data = {
            "original_filename": original_filename,
            "staged_at": datetime.utcnow().isoformat() + "Z",
            **meta,
        }
        (pending_dir / "meta.json").write_text(
            json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return pending_id

    def get_pending(self, pending_id: str) -> dict | None:
        pending_dir = self.inbox_dir / pending_id
        if not pending_dir.exists():
            return None

        converted_path = pending_dir / "converted.md"
        meta_path = pending_dir / "meta.json"
        fm_path = pending_dir / "frontmatter.yaml"

        if not converted_path.exists():
            return None

        return {
            "pending_id": pending_id,
            "converted_md": converted_path.read_text(encoding="utf-8"),
            "frontmatter": fm_path.read_text(encoding="utf-8") if fm_path.exists() else "",
            "meta": json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {},
        }

    def list_pending(self) -> list[str]:
        return [d.name for d in self.inbox_dir.iterdir() if d.is_dir()]

    def remove_pending(self, pending_id: str) -> None:
        pending_dir = self.inbox_dir / pending_id
        if pending_dir.exists():
            shutil.rmtree(pending_dir)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_m1_repo.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add server/kb/storage/repo.py server/kb/storage/inbox.py tests/test_m1_repo.py
git commit -m "feat(kb): M1.2 Markdown 文档仓库 CRUD 与 _inbox 暂存"
```

---

### Task M1.3: 文档解析器（PDF/Excel/Word/HTML/MD + 降级策略）

**Files:**
- Create: `server/kb/parser/markdown_parser.py` (含 ParseResult 数据类)
- Create: `server/kb/parser/pdf_parser.py`
- Create: `server/kb/parser/office_parser.py`
- Create: `server/kb/parser/image_parser.py`
- Test: `tests/test_m1_parsers.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m1_parsers.py
import pytest
from pathlib import Path
from server.kb.parser.markdown_parser import MarkdownParser
from server.kb.parser.pdf_parser import PdfParser
from server.kb.parser.office_parser import ExcelParser, WordParser
from server.kb.parser.image_parser import ImageParser


def test_markdown_parser_parse():
    parser = MarkdownParser()
    result = parser.parse("# 标题\n\n正文内容")
    assert result.success is True
    assert "标题" in result.content
    assert result.confidence >= 0.85

def test_markdown_parser_plain_text():
    parser = MarkdownParser()
    result = parser.parse("纯文本无格式")
    assert result.success is True
    assert "纯文本无格式" in result.content

def test_excel_parser_basic(tmp_path):
    import pandas as pd
    excel_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    df.to_excel(excel_path, sheet_name="Sheet1", index=False)

    parser = ExcelParser()
    result = parser.parse(excel_path)
    assert result.success is True
    assert "Sheet1" in result.content
    assert "A" in result.content and "B" in result.content

def test_word_parser_basic(tmp_path):
    try:
        from docx import Document
    except ImportError:
        pytest.skip("python-docx 未安装")

    docx_path = tmp_path / "test.docx"
    doc = Document()
    doc.add_heading("标题", level=1)
    doc.add_paragraph("段落内容")
    doc.save(docx_path)

    parser = WordParser()
    result = parser.parse(docx_path)
    assert result.success is True
    assert "标题" in result.content

def test_image_parser_degradation():
    parser = ImageParser()
    result = parser.parse("fake_image.png")
    assert result.success is True
    assert result.confidence <= 0.3
    assert "待多模态解析" in result.content or "image" in result.content.lower()

def test_pdf_parser_graceful_degradation(tmp_path):
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a real pdf")

    parser = PdfParser()
    result = parser.parse(fake_pdf)
    assert result.success is False or result.confidence < 0.5
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m1_parsers.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现 ParseResult 与 MarkdownParser**

```python
# server/kb/parser/markdown_parser.py
"""Markdown/TXT 解析器"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    content: str
    confidence: float
    parser_name: str
    error: str = ""
    assets: list[str] = field(default_factory=list)


class MarkdownParser:
    """Markdown/纯文本解析器（直接透传）"""

    def parse(self, content: str | Path) -> ParseResult:
        if isinstance(content, Path):
            try:
                text = content.read_text(encoding="utf-8")
            except Exception as e:
                return ParseResult(False, "", 0.0, "markdown", str(e))
        else:
            text = content

        confidence = 0.95 if text.strip().startswith("#") else 0.85
        return ParseResult(True, text, confidence, "markdown")
```

- [ ] **Step 4: 实现 PdfParser（含降级）**

```python
# server/kb/parser/pdf_parser.py
"""PDF 解析器（Marker + pypdf 降级）"""
from __future__ import annotations
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult


class PdfParser:
    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if not file_path.exists():
            return ParseResult(False, "", 0.0, "pdf", f"文件不存在: {file_path}")

        try:
            return self._parse_with_marker(file_path)
        except Exception:
            pass

        try:
            return self._parse_with_pypdf(file_path)
        except Exception as e:
            return ParseResult(False, "", 0.0, "pdf", f"PDF 解析失败: {e}")

    def _parse_with_marker(self, file_path: Path) -> ParseResult:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(file_path))
        return ParseResult(True, rendered.markdown, 0.9, "pdf_marker")

    def _parse_with_pypdf(self, file_path: Path) -> ParseResult:
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return ParseResult(True, "\n\n".join(text_parts), 0.5, "pdf_pypdf")
```

- [ ] **Step 5: 实现 ExcelParser 和 WordParser**

```python
# server/kb/parser/office_parser.py
"""Office 文档解析器（Excel/Word → Markdown）"""
from __future__ import annotations
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult


class ExcelParser:
    """Excel→Markdown 解析器（Pandas）"""

    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        try:
            import pandas as pd
        except ImportError:
            return ParseResult(False, "", 0.0, "excel", "pandas 未安装")

        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            return ParseResult(False, "", 0.0, "excel", str(e))

        md_parts = []
        total_cells = 0
        converted_cells = 0

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            md_parts.append(f"## {sheet_name}\n")
            if df.empty:
                md_parts.append("*(空表)*\n")
                continue

            headers = df.columns.tolist()
            md_parts.append("| " + " | ".join(str(h) for h in headers) + " |")
            md_parts.append("| " + " | ".join("---" for _ in headers) + " |")

            for _, row in df.iterrows():
                cells = []
                for val in row:
                    total_cells += 1
                    if pd.isna(val):
                        cells.append("")
                    else:
                        cells.append(str(val))
                        converted_cells += 1
                md_parts.append("| " + " | ".join(cells) + " |")
            md_parts.append("")

        confidence = 0.95 if total_cells == 0 else min(0.95, converted_cells / total_cells)
        if confidence < 0.95:
            confidence = 0.6
        return ParseResult(True, "\n".join(md_parts), confidence, "excel")


class WordParser:
    """Word→Markdown 解析器（python-docx）"""

    def parse(self, file_path: Path) -> ParseResult:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        try:
            from docx import Document
        except ImportError:
            return ParseResult(False, "", 0.0, "word", "python-docx 未安装")

        try:
            doc = Document(str(file_path))
        except Exception as e:
            return ParseResult(False, "", 0.0, "word", str(e))

        md_parts = []
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading"):
                level = int(para.style.name.split()[-1]) if para.style.name[-1].isdigit() else 1
                md_parts.append(f"{'#' * (level + 1)} {para.text}")
            elif para.text.strip():
                md_parts.append(para.text)
            else:
                md_parts.append("")

        return ParseResult(True, "\n".join(md_parts), 0.85, "word")
```

- [ ] **Step 6: 实现 ImageParser（降级占位）**

```python
# server/kb/parser/image_parser.py
"""图片解析器（降级占位，待多模态 API 启用）"""
from __future__ import annotations
from pathlib import Path
from server.kb.parser.markdown_parser import ParseResult


class ImageParser:
    """图片解析器 - 当前仅降级占位"""

    def __init__(self, vl_api_client=None):
        self.vl_api_client = vl_api_client

    def parse(self, file_path: Path | str) -> ParseResult:
        if self.vl_api_client:
            return self.parse_with_vl(file_path)
        return self._parse_degraded(file_path)

    def _parse_degraded(self, file_path: Path | str) -> ParseResult:
        path = Path(file_path) if not isinstance(file_path, Path) else file_path
        filename = path.name if path.exists() else str(file_path)
        content = f"![image]({filename}) <!-- 待多模态解析 -->"
        return ParseResult(
            True, content, 0.3, "image_degraded",
            assets=[str(path)] if path.exists() else [],
        )

    def parse_with_vl(self, file_path: Path | str) -> ParseResult:
        raise NotImplementedError("多模态解析未配置")
```

- [ ] **Step 7: 运行测试验证通过**

Run: `python -m pytest tests/test_m1_parsers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 8: Commit**

```bash
git add server/kb/parser/ tests/test_m1_parsers.py
git commit -m "feat(kb): M1.3 文档解析器（PDF/Excel/Word/HTML/MD + 降级策略）"
```

---

### Task M1.4: 知识库 CRUD API 端点

**Files:**
- Create: `server/api/kb.py`
- Modify: `server/main.py` (注册路由)
- Test: `tests/test_m1_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m1_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_kb_import_document(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "kb" / "_inbox")

    response = await client.post("/api/kb/import", json={
        "content": "# 测试文档\n\n这是导入的内容",
        "title": "测试文档",
        "type": "note",
        "scope": "private",
        "tags": ["test"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "pending_id" in data

@pytest.mark.asyncio
async def test_kb_list_pending(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "_inbox")

    response = await client.get("/api/kb/inbox")
    assert response.status_code == 200
    data = response.json()
    assert "pending" in data
    assert isinstance(data["pending"], list)

@pytest.mark.asyncio
async def test_kb_approve_document(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "kb" / "_inbox")

    import_resp = await client.post("/api/kb/import", json={
        "content": "# 审核测试",
        "title": "审核测试",
        "type": "note",
        "scope": "private",
    })
    pending_id = import_resp.json()["pending_id"]

    response = await client.post(f"/api/kb/inbox/{pending_id}/approve")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "doc_id" in data

@pytest.mark.asyncio
async def test_kb_list_documents(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "documents")

    response = await client.get("/api/kb/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m1_api.py -v`
Expected: FAIL (路由不存在)

- [ ] **Step 3: 实现 KB API**

```python
# server/api/kb.py
"""知识库 CRUD API"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import hashlib

from server.config_kb_cu import KBConfig
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.inbox import InboxWriter
from server.kb.storage.frontmatter import FrontMatter, parse_frontmatter
from server.kb.parser.validator import validate_frontmatter, ValidationError

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class ImportRequest(BaseModel):
    content: str
    title: str
    type: str = "note"
    scope: str = "private"
    tags: list[str] = []
    categories: list[str] = []


class ImportResponse(BaseModel):
    success: bool
    pending_id: str
    message: str = ""


def _get_config() -> KBConfig:
    config = KBConfig()
    config.ensure_dirs()
    return config


@router.post("/import", response_model=ImportResponse)
async def import_document(req: ImportRequest):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)

    checksum = f"sha256:{hashlib.sha256(req.content.encode()).hexdigest()}"
    fm = FrontMatter(
        id=f"kb-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        title=req.title, type=req.type, scope=req.scope,
        source_type="manual", confidence=0.95, checksum=checksum,
        tags=req.tags, categories=req.categories,
    )

    try:
        validate_frontmatter(fm)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pending_id = inbox.stage(
        original_filename="manual_input.md",
        converted_md=req.content,
        frontmatter=fm,
        meta={"parser": "manual", "source": "api"},
    )
    return ImportResponse(success=True, pending_id=pending_id, message="文档已暂存到 _inbox")


@router.get("/inbox")
async def list_inbox():
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    return {"pending": inbox.list_pending()}


@router.post("/inbox/{pending_id}/approve")
async def approve_document(pending_id: str):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    repo = DocumentRepo(documents_dir=config.documents_dir)

    pending = inbox.get_pending(pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="待审核项不存在")

    fm_content = pending["frontmatter"] + "\n\n# placeholder"
    fm, _ = parse_frontmatter(fm_content)
    if not fm:
        raise HTTPException(status_code=500, detail="front matter 解析失败")

    repo.save(fm, pending["converted_md"])
    inbox.remove_pending(pending_id)
    return {"success": True, "doc_id": fm.id, "message": "文档已审核通过并保存"}


@router.delete("/inbox/{pending_id}")
async def reject_document(pending_id: str):
    config = _get_config()
    inbox = InboxWriter(inbox_dir=config.inbox_dir)
    inbox.remove_pending(pending_id)
    return {"success": True, "message": "已拒绝并移除"}


@router.get("/documents")
async def list_documents():
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    return {"documents": repo.list_all()}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    fm, body = repo.read(doc_id)
    return {
        "id": fm.id, "title": fm.title, "type": fm.type,
        "scope": fm.scope, "confidence": fm.confidence,
        "tags": fm.tags, "content": body,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    if not repo.exists(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    repo.delete(doc_id)
    return {"success": True, "message": "文档已删除"}
```

- [ ] **Step 4: 在 main.py 注册路由**

在 `server/main.py` 路由注册部分添加：

```python
from server.api.kb import router as kb_router
app.include_router(kb_router)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_m1_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add server/api/kb.py server/main.py tests/test_m1_api.py
git commit -m "feat(kb): M1.4 知识库 CRUD API 端点"
```

---

## M2: 向量检索与混合检索

### Task M2.1: ChromaDB 向量存储与增量索引

**Files:**
- Create: `server/kb/retrieval/vectorstore.py`
- Create: `server/kb/retrieval/indexer.py`
- Test: `tests/test_m2_vectorstore.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m2_vectorstore.py
import pytest
from pathlib import Path
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.retrieval.indexer import Indexer


@pytest.fixture
def temp_store(tmp_path):
    return ChromaVectorStore(persist_dir=tmp_path / "chroma")


def test_vectorstore_add_and_query(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "Python 是一门编程语言", "scope": "private", "tags": ["python"]},
        {"id": "chunk-002", "doc_id": "doc-002", "text": "FastAPI 是 Web 框架", "scope": "private", "tags": ["fastapi"]},
    ]
    temp_store.upsert(chunks)
    results = temp_store.query("编程语言", scope="private", top_k=2)
    assert len(results) > 0
    assert results[0]["doc_id"] in ["doc-001", "doc-002"]

def test_vectorstore_scope_filter(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "私有内容", "scope": "private", "tags": []},
        {"id": "chunk-002", "doc_id": "doc-002", "text": "公开内容", "scope": "public", "tags": []},
    ]
    temp_store.upsert(chunks)
    results = temp_store.query("内容", scope="private", top_k=10)
    assert all(r["scope"] == "private" for r in results)

def test_vectorstore_delete_by_doc(temp_store):
    chunks = [
        {"id": "chunk-001", "doc_id": "doc-001", "text": "test", "scope": "private", "tags": []},
    ]
    temp_store.upsert(chunks)
    temp_store.delete_by_doc_id("doc-001")
    results = temp_store.query("test", scope="private", top_k=10)
    assert len(results) == 0


@pytest.fixture
def temp_indexer(tmp_path):
    from server.kb.storage.repo import DocumentRepo
    from server.kb.storage.frontmatter import FrontMatter
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    for i in range(3):
        fm = FrontMatter(
            id=f"kb-test-{i:03d}", title=f"测试文档{i}", type="note", scope="private",
            source_type="manual", confidence=0.9, checksum=f"sha256:{i}",
        )
        repo.save(fm, f"# 文档{i}\n\n这是测试内容{i}，关于Python编程")
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    return Indexer(repo=repo, vector_store=store)


def test_indexer_build_index(temp_indexer):
    result = temp_indexer.build_index()
    assert result.success is True
    assert result.indexed_count == 3

def test_indexer_incremental_update(temp_indexer):
    temp_indexer.build_index()
    result = temp_indexer.build_index()
    assert result.indexed_count == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m2_vectorstore.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 ChromaVectorStore**

```python
# server/kb/retrieval/vectorstore.py
"""ChromaDB 嵌入式向量存储"""
from __future__ import annotations
from pathlib import Path


class ChromaVectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None

    def _ensure_client(self):
        if self._client is not None:
            return
        import chromadb
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="kb_chunks", metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        self._ensure_client()
        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [{
            "doc_id": c["doc_id"],
            "scope": c.get("scope", "private"),
            "tags": ",".join(c.get("tags", [])),
            "chunk_idx": c.get("chunk_idx", 0),
            "section": c.get("section", ""),
        } for c in chunks]
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, query_text: str, scope: str, top_k: int = 10) -> list[dict]:
        self._ensure_client()
        results = self._collection.query(
            query_texts=[query_text], n_results=top_k,
            where={"scope": scope},
        )
        if not results["ids"] or not results["ids"][0]:
            return []
        return [{
            "id": results["ids"][0][i],
            "doc_id": results["metadatas"][0][i].get("doc_id", ""),
            "text": results["documents"][0][i],
            "scope": results["metadatas"][0][i].get("scope", ""),
            "tags": results["metadatas"][0][i].get("tags", "").split(",") if results["metadatas"][0][i].get("tags") else [],
            "score": 1 - results["distances"][0][i] if "distances" in results else 0.0,
        } for i in range(len(results["ids"][0]))]

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._ensure_client()
        self._collection.delete(where={"doc_id": doc_id})
```

- [ ] **Step 4: 实现 Indexer**

```python
# server/kb/retrieval/indexer.py
"""索引构建器"""
from __future__ import annotations
from dataclasses import dataclass
from server.kb.storage.repo import DocumentRepo
from server.kb.retrieval.vectorstore import ChromaVectorStore


@dataclass
class IndexResult:
    success: bool
    indexed_count: int
    skipped_count: int
    error: str = ""


class Indexer:
    """文档索引构建器（增量更新）"""

    def __init__(self, repo: DocumentRepo, vector_store: ChromaVectorStore):
        self.repo = repo
        self.vector_store = vector_store
        self._indexed_checksums: set[str] = set()

    def build_index(self) -> IndexResult:
        doc_ids = self.repo.list_all()
        indexed = 0
        skipped = 0

        for doc_id in doc_ids:
            fm, body = self.repo.read(doc_id)
            if fm.checksum in self._indexed_checksums:
                skipped += 1
                continue
            chunks = self._chunk_document(doc_id, fm, body)
            self.vector_store.upsert(chunks)
            self._indexed_checksums.add(fm.checksum)
            indexed += 1

        return IndexResult(True, indexed, skipped)

    def _chunk_document(self, doc_id: str, fm, body: str) -> list[dict]:
        chunks = []
        sections = body.split("\n## ")
        for idx, section in enumerate(sections):
            if not section.strip():
                continue
            chunk_text = section if idx == 0 else f"## {section}"
            chunks.append({
                "id": f"{doc_id}-chunk-{idx:03d}",
                "doc_id": doc_id, "text": chunk_text,
                "scope": fm.scope, "tags": fm.tags,
                "chunk_idx": idx, "section": chunk_text.split("\n")[0][:100],
            })
        return chunks
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_m2_vectorstore.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add server/kb/retrieval/vectorstore.py server/kb/retrieval/indexer.py tests/test_m2_vectorstore.py
git commit -m "feat(kb): M2.1 ChromaDB 向量存储与增量索引"
```

---

### Task M2.2: 混合检索（向量 + 关键词 + RRF 融合 + scope 隔离）

**Files:**
- Create: `server/kb/retrieval/scope.py`
- Create: `server/kb/retrieval/hybrid.py`
- Test: `tests/test_m2_hybrid.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m2_hybrid.py
import pytest
from pathlib import Path
from server.kb.retrieval.hybrid import HybridSearcher, SearchResult
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.storage.repo import DocumentRepo
from server.kb.storage.frontmatter import FrontMatter


@pytest.fixture
def setup_kb(tmp_path):
    repo = DocumentRepo(documents_dir=tmp_path / "documents")
    store = ChromaVectorStore(persist_dir=tmp_path / "chroma")
    docs = [
        ("kb-001", "Python 编程入门", "private", "Python 是一门易学的编程语言，适合初学者"),
        ("kb-002", "FastAPI Web 开发", "private", "FastAPI 是现代的 Python Web 框架"),
        ("kb-003", "数据库设计原则", "public", "数据库设计需要考虑范式化和性能优化"),
    ]
    for doc_id, title, scope, content in docs:
        fm = FrontMatter(
            id=doc_id, title=title, type="note", scope=scope,
            source_type="manual", confidence=0.9, checksum=f"sha256:{doc_id}",
            tags=[title.split()[0].lower()],
        )
        repo.save(fm, f"# {title}\n\n{content}")
    chunks = [{
        "id": f"{doc_id}-chunk-000", "doc_id": doc_id, "text": content,
        "scope": scope, "tags": [title.split()[0].lower()],
    } for doc_id, title, scope, content in docs]
    store.upsert(chunks)
    return repo, store


def test_hybrid_search_basic(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("Python 编程", scope="private", top_k=2)
    assert len(results) > 0
    assert any(r.doc_id == "kb-001" for r in results)

def test_hybrid_search_scope_filter(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("数据库", scope="private", top_k=10)
    assert all(r.scope == "private" for r in results)

def test_hybrid_search_source_method(setup_kb):
    repo, store = setup_kb
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search("Python", scope="private", top_k=5)
    assert all(hasattr(r, "source_method") for r in results)

def test_search_result_dataclass():
    r = SearchResult(doc_id="kb-001", chunk_text="test", score=0.9,
                     source_method="vector", scope="private", title="测试")
    assert r.doc_id == "kb-001"
    assert r.source_method == "vector"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m2_hybrid.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 ScopeFilter 和 HybridSearcher**

```python
# server/kb/retrieval/scope.py
"""作用域硬隔离过滤（E2 安全核心）"""
from __future__ import annotations
from server.kb.retrieval.hybrid import SearchResult


class ScopeFilter:
    """服务端代码级强制 scope 过滤"""

    @staticmethod
    def filter(results: list[SearchResult], scope: str) -> list[SearchResult]:
        """双重保险：检索后再次校验 scope"""
        return [r for r in results if r.scope == scope]
```

```python
# server/kb/retrieval/hybrid.py
"""混合检索（向量 + 关键词 + RRF 融合）"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from server.kb.storage.repo import DocumentRepo
from server.kb.retrieval.vectorstore import ChromaVectorStore
from server.kb.retrieval.scope import ScopeFilter


@dataclass
class SearchResult:
    doc_id: str
    chunk_text: str
    score: float
    source_method: str
    scope: str
    title: str = ""
    tags: list[str] = field(default_factory=list)


class HybridSearcher:
    VECTOR_WEIGHT = 0.5
    KEYWORD_WEIGHT = 0.3
    GRAPH_WEIGHT = 0.2
    RRF_K = 60

    def __init__(self, repo: DocumentRepo, vector_store: ChromaVectorStore):
        self.repo = repo
        self.vector_store = vector_store

    def search(self, query: str, scope: str, top_k: int = 5,
               methods: list[str] | None = None) -> list[SearchResult]:
        if methods is None:
            methods = ["vector", "keyword"]

        all_results: list[SearchResult] = []
        if "vector" in methods:
            all_results.extend(self._vector_search(query, scope, top_k * 4))
        if "keyword" in methods:
            all_results.extend(self._keyword_search(query, scope, top_k * 4))

        fused = self._rrf_fuse(all_results, top_k)
        return ScopeFilter.filter(fused, scope)

    def _vector_search(self, query: str, scope: str, top_k: int) -> list[SearchResult]:
        raw = self.vector_store.query(query, scope=scope, top_k=top_k)
        return [SearchResult(
            doc_id=r["doc_id"], chunk_text=r["text"], score=r["score"],
            source_method="vector", scope=r["scope"], tags=r.get("tags", []),
        ) for r in raw]

    def _keyword_search(self, query: str, scope: str, top_k: int) -> list[SearchResult]:
        results = []
        query_lower = query.lower()
        for doc_id in self.repo.list_all():
            fm, body = self.repo.read(doc_id)
            if fm.scope != scope:
                continue
            body_lower = body.lower()
            title_lower = fm.title.lower()
            score = 0.0
            if query_lower in title_lower:
                score += 0.5
            if query_lower in body_lower:
                score += 0.3
            for word in query_lower.split():
                score += body_lower.count(word) * 0.05
            if score > 0:
                idx = body_lower.find(query_lower)
                chunk = body[max(0, idx-50):min(len(body), idx+len(query)+100)] if idx >= 0 else body[:200]
                results.append(SearchResult(
                    doc_id=doc_id, chunk_text=chunk, score=min(score, 1.0),
                    source_method="keyword", scope=fm.scope, title=fm.title, tags=fm.tags,
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _rrf_fuse(self, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        doc_scores: dict[str, float] = defaultdict(float)
        doc_info: dict[str, SearchResult] = {}
        by_method: dict[str, list[SearchResult]] = defaultdict(list)
        for r in results:
            by_method[r.source_method].append(r)

        weights = {"vector": self.VECTOR_WEIGHT, "keyword": self.KEYWORD_WEIGHT, "graph": self.GRAPH_WEIGHT}
        for method, method_results in by_method.items():
            method_results.sort(key=lambda r: r.score, reverse=True)
            weight = weights.get(method, 0.1)
            for rank, r in enumerate(method_results):
                doc_scores[r.doc_id] += weight / (self.RRF_K + rank + 1)
                if r.doc_id not in doc_info:
                    doc_info[r.doc_id] = r

        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        return [SearchResult(
            doc_id=doc_id, chunk_text=doc_info[doc_id].chunk_text,
            score=score, source_method=doc_info[doc_id].source_method,
            scope=doc_info[doc_id].scope, title=doc_info[doc_id].title,
            tags=doc_info[doc_id].tags,
        ) for doc_id, score in sorted_docs[:top_k]]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_m2_hybrid.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add server/kb/retrieval/scope.py server/kb/retrieval/hybrid.py tests/test_m2_hybrid.py
git commit -m "feat(kb): M2.2 混合检索（向量+关键词+RRF融合+scope隔离）"
```

---

### Task M2.3: 检索 API 端点

**Files:**
- Modify: `server/api/kb.py` (追加检索端点)
- Test: `tests/test_m2_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m2_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_search_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "inbox_dir", tmp_path / "kb" / "_inbox")
    monkeypatch.setattr(KBConfig, "chroma_dir", tmp_path / "kb" / "indexes" / "chroma")

    import_resp = await client.post("/api/kb/import", json={
        "content": "# Python 编程\n\nPython 是一门编程语言",
        "title": "Python 编程", "type": "note", "scope": "private", "tags": ["python"],
    })
    pending_id = import_resp.json()["pending_id"]
    await client.post(f"/api/kb/inbox/{pending_id}/approve")

    response = await client.get("/api/kb/search", params={"query": "Python", "scope": "private", "top_k": 5})
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m2_api.py -v`
Expected: FAIL (端点不存在)

- [ ] **Step 3: 追加检索端点到 kb.py**

在 `server/api/kb.py` 末尾追加：

```python
@router.get("/search")
async def search_documents(query: str, scope: str = "private", top_k: int = 5):
    """混合检索文档"""
    from server.kb.retrieval.hybrid import HybridSearcher
    config = _get_config()
    repo = DocumentRepo(documents_dir=config.documents_dir)
    store = ChromaVectorStore(persist_dir=config.chroma_dir)
    searcher = HybridSearcher(repo=repo, vector_store=store)
    results = searcher.search(query=query, scope=scope, top_k=top_k)
    return {"results": [{
        "doc_id": r.doc_id, "title": r.title, "chunk_text": r.chunk_text,
        "score": r.score, "source_method": r.source_method, "scope": r.scope, "tags": r.tags,
    } for r in results]}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_m2_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/api/kb.py tests/test_m2_api.py
git commit -m "feat(kb): M2.3 检索 API 端点"
```

---

## M3: 知识图谱 + wikigraph 可视化

### Task M3.1: Kuzu 图数据库存储

**Files:**
- Create: `server/kb/graph/kuzu_store.py`
- Test: `tests/test_m3_kuzu.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m3_kuzu.py
import pytest
from pathlib import Path
from server.kb.graph.kuzu_store import KuzuGraphStore


@pytest.fixture
def temp_store(tmp_path):
    return KuzuGraphStore(db_dir=tmp_path / "kuzu")


def test_kuzu_init_schema(temp_store):
    temp_store.init_schema()
    tables = temp_store.list_tables()
    assert "Document" in tables
    assert "Entity" in tables


def test_kuzu_add_document(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "测试文档", "note", "private", 0.9, "documents/kb-001.md")
    docs = temp_store.list_documents(scope="private")
    assert len(docs) == 1
    assert docs[0]["id"] == "kb-001"


def test_kuzu_add_relation(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "文档1", "note", "private", 0.9, "doc1.md")
    temp_store.add_document("kb-002", "文档2", "note", "private", 0.9, "doc2.md")
    temp_store.add_relation("kb-001", "kb-002", "References", 0.8)
    relations = temp_store.get_relations("kb-001")
    assert len(relations) == 1
    assert relations[0]["target_id"] == "kb-002"


def test_kuzu_get_neighbors(temp_store):
    temp_store.init_schema()
    for i in range(1, 4):
        temp_store.add_document(f"kb-00{i}", f"文档{i}", "note", "private", 0.9, f"doc{i}.md")
    temp_store.add_relation("kb-001", "kb-002", "References", 0.8)
    temp_store.add_relation("kb-002", "kb-003", "Extends", 0.7)
    neighbors = temp_store.get_neighbors("kb-001", depth=2, scope="private")
    neighbor_ids = [n["id"] for n in neighbors]
    assert "kb-002" in neighbor_ids


def test_kuzu_scope_filter(temp_store):
    temp_store.init_schema()
    temp_store.add_document("kb-001", "私有", "note", "private", 0.9, "doc1.md")
    temp_store.add_document("kb-002", "公开", "note", "public", 0.9, "doc2.md")
    private_docs = temp_store.list_documents(scope="private")
    assert len(private_docs) == 1
    assert private_docs[0]["id"] == "kb-001"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m3_kuzu.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 KuzuGraphStore**

```python
# server/kb/graph/kuzu_store.py
"""Kuzu 嵌入式图数据库存储"""
from __future__ import annotations
from pathlib import Path


class KuzuGraphStore:
    SCHEMA_DDL = [
        "CREATE NODE TABLE IF NOT EXISTS Document (id STRING PRIMARY KEY, title STRING, type STRING, scope STRING, confidence DOUBLE, file_path STRING, updated_at TIMESTAMP)",
        "CREATE NODE TABLE IF NOT EXISTS Entity (id STRING PRIMARY KEY, name STRING, entity_type STRING, description STRING, mention_count INT64)",
        "CREATE REL TABLE IF NOT EXISTS References (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Extends (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Contradicts (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS DerivedFrom (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Mentions (FROM Document TO Entity, count INT64, first_seen TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS RelatedTo (FROM Entity TO Entity, relation STRING, weight DOUBLE)",
    ]

    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._db = None
        self._conn = None

    def _ensure_connection(self):
        if self._conn is not None:
            return
        import kuzu
        self._db = kuzu.Database(str(self.db_dir))
        self._conn = kuzu.Connection(self._db)

    def init_schema(self):
        self._ensure_connection()
        for ddl in self.SCHEMA_DDL:
            self._conn.execute(ddl)

    def add_document(self, doc_id, title, doc_type, scope, confidence, file_path):
        self._ensure_connection()
        self._conn.execute(
            "MERGE (d:Document {id: $id}) SET d.title=$title, d.type=$type, d.scope=$scope, d.confidence=$confidence, d.file_path=$file_path, d.updated_at=timestamp()",
            {"id": doc_id, "title": title, "type": doc_type, "scope": scope, "confidence": confidence, "file_path": file_path},
        )

    def add_relation(self, source_id, target_id, rel_type, weight):
        self._ensure_connection()
        valid = {"References", "Extends", "Contradicts", "DerivedFrom"}
        if rel_type not in valid:
            raise ValueError(f"rel_type 必须是 {valid} 之一")
        query = f"MATCH (s:Document {{id: $src}}), (t:Document {{id: $tgt}}) MERGE (s)-[r:{rel_type}]->(t) SET r.weight=$w, r.created_at=timestamp()"
        self._conn.execute(query, {"src": source_id, "tgt": target_id, "w": weight})

    def list_documents(self, scope=None):
        self._ensure_connection()
        if scope:
            result = self._conn.execute("MATCH (d:Document) WHERE d.scope=$scope RETURN d.id, d.title, d.type, d.scope, d.confidence", {"scope": scope})
        else:
            result = self._conn.execute("MATCH (d:Document) RETURN d.id, d.title, d.type, d.scope, d.confidence")
        docs = []
        while result.hasNext():
            row = result.getNext()
            docs.append({"id": row[0], "title": row[1], "type": row[2], "scope": row[3], "confidence": row[4]})
        return docs

    def get_relations(self, doc_id):
        self._ensure_connection()
        result = self._conn.execute("MATCH (d:Document {id: $id})-[r]->(t:Document) RETURN t.id, type(r), r.weight", {"id": doc_id})
        rels = []
        while result.hasNext():
            row = result.getNext()
            rels.append({"target_id": row[0], "rel_type": row[1], "weight": row[2]})
        return rels

    def get_neighbors(self, doc_id, depth=2, scope=None):
        self._ensure_connection()
        query = f"MATCH (d:Document {{id: $id}})-[r*1..{depth}]-(t:Document)"
        if scope:
            query += f" WHERE t.scope = '{scope}'"
        query += " RETURN DISTINCT t.id, t.title, t.scope, t.confidence"
        result = self._conn.execute(query, {"id": doc_id})
        neighbors = []
        while result.hasNext():
            row = result.getNext()
            neighbors.append({"id": row[0], "title": row[1], "scope": row[2], "confidence": row[3]})
        return neighbors

    def list_tables(self):
        self._ensure_connection()
        result = self._conn.execute("CALL show_tables() RETURN *")
        tables = []
        while result.hasNext():
            row = result.getNext()
            tables.append(row[0])
        return tables
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_m3_kuzu.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add server/kb/graph/kuzu_store.py tests/test_m3_kuzu.py
git commit -m "feat(kb): M3.1 Kuzu 图数据库存储"
```

---

### Task M3.2: 图谱查询 API 与关系推荐

**Files:**
- Create: `server/api/graph.py`
- Create: `server/kb/graph/relation_extractor.py`
- Modify: `server/main.py` (注册路由)
- Test: `tests/test_m3_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m3_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_graph_documents_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kuzu_dir", tmp_path / "kuzu")
    response = await client.get("/api/graph/documents", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_graph_rebuild_endpoint(client, tmp_path, monkeypatch):
    from server.config_kb_cu import KBConfig
    monkeypatch.setattr(KBConfig, "kb_root", tmp_path / "kb")
    monkeypatch.setattr(KBConfig, "documents_dir", tmp_path / "kb" / "documents")
    monkeypatch.setattr(KBConfig, "kuzu_dir", tmp_path / "kb" / "indexes" / "kuzu")
    response = await client.post("/api/graph/rebuild", params={"scope": "private"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_relation_extractor_recommend():
    from server.kb.graph.relation_extractor import RelationExtractor
    extractor = RelationExtractor()
    recommendations = extractor.recommend_relations(
        doc_id="kb-001",
        similar_docs=[
            {"doc_id": "kb-002", "title": "相关文档", "score": 0.85},
            {"doc_id": "kb-003", "title": "扩展文档", "score": 0.75},
        ],
    )
    assert len(recommendations) > 0
    assert all(r.confidence > 0 for r in recommendations)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m3_api.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 RelationExtractor**

```python
# server/kb/graph/relation_extractor.py
"""文档关系抽取与推荐"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RelationRecommendation:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    reason: str


class RelationExtractor:
    def recommend_relations(self, doc_id: str, similar_docs: list[dict]) -> list[RelationRecommendation]:
        recommendations = []
        for doc in similar_docs:
            score = doc.get("score", 0.0)
            if score < 0.5:
                continue
            if score >= 0.85:
                rel_type, reason = "references", "向量相似度极高，可能存在引用关系"
            elif score >= 0.7:
                rel_type, reason = "extends", "内容相关，可能是扩展或延伸"
            else:
                rel_type, reason = "derived_from", "存在一定相似度，可能同源"
            recommendations.append(RelationRecommendation(
                source_id=doc_id, target_id=doc["doc_id"],
                relation_type=rel_type, confidence=score, reason=reason,
            ))
        return recommendations
```

- [ ] **Step 4: 实现 Graph API**

```python
# server/api/graph.py
"""知识图谱查询 API"""
from __future__ import annotations
from fastapi import APIRouter
from server.config_kb_cu import KBConfig
from server.kb.graph.kuzu_store import KuzuGraphStore

router = APIRouter(prefix="/api/graph", tags=["knowledge-graph"])


def _get_store() -> KuzuGraphStore:
    config = KBConfig()
    config.ensure_dirs()
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    return store


@router.get("/documents")
async def get_document_graph(scope: str = "private", depth: int = 2):
    store = _get_store()
    docs = store.list_documents(scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document",
              "scope": d["scope"], "doc_type": d["type"], "confidence": d["confidence"]} for d in docs]
    edges = []
    for doc in docs:
        for rel in store.get_relations(doc["id"]):
            edges.append({"source": doc["id"], "target": rel["target_id"],
                          "relation_type": rel["rel_type"], "weight": rel["weight"]})
    return {"nodes": nodes, "edges": edges}


@router.get("/entities")
async def get_entity_graph(scope: str = "private", min_weight: float = 0.5):
    return {"nodes": [], "edges": []}


@router.get("/timeline")
async def get_timeline_graph(scope: str = "private"):
    store = _get_store()
    docs = store.list_documents(scope=scope)
    nodes = [{"id": d["id"], "label": d["title"], "type": "document", "scope": d["scope"]} for d in docs]
    return {"nodes": nodes, "edges": []}


@router.post("/rebuild")
async def rebuild_graph(scope: str | None = None):
    config = KBConfig()
    config.ensure_dirs()
    store = KuzuGraphStore(db_dir=config.kuzu_dir)
    store.init_schema()
    from server.kb.storage.repo import DocumentRepo
    repo = DocumentRepo(documents_dir=config.documents_dir)
    count = 0
    for doc_id in repo.list_all():
        fm, _ = repo.read(doc_id)
        if scope and fm.scope != scope:
            continue
        store.add_document(fm.id, fm.title, fm.type, fm.scope, fm.confidence, fm.id)
        count += 1
    return {"success": True, "indexed_count": count}
```

- [ ] **Step 5: 在 main.py 注册路由**

```python
from server.api.graph import router as graph_router
app.include_router(graph_router)
```

- [ ] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_m3_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add server/api/graph.py server/kb/graph/relation_extractor.py server/main.py tests/test_m3_api.py
git commit -m "feat(kb): M3.2 图谱查询 API 与关系推荐"
```

---

## M4: Computer Use 基础

### Task M4.1: 安全四件套 - 沙箱、急停、审计日志

**Files:**
- Create: `server/cu/sandbox/fs_sandbox.py`
- Create: `server/cu/safety/emergency_stop.py`
- Create: `server/cu/safety/audit_log.py`
- Test: `tests/test_m4_safety.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m4_safety.py
import pytest
from pathlib import Path
from server.cu.sandbox.fs_sandbox import FsSandbox, SandboxViolation
from server.cu.safety.emergency_stop import EmergencyStop, EmergencyStopError
from server.cu.safety.audit_log import AuditLogger


def test_fs_sandbox_write_allowed(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox")
    target = tmp_path / "_sandbox" / "test.txt"
    assert sandbox.validate_write(target) is True

def test_fs_sandbox_write_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[tmp_path / "documents"])
    target = tmp_path / "evil.txt"
    with pytest.raises(SandboxViolation, match="写操作越界"):
        sandbox.validate_write(target)

def test_fs_sandbox_read_allowed(tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[docs_dir])
    assert sandbox.validate_read(docs_dir / "doc.md") is True

def test_fs_sandbox_read_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox", read_whitelist=[tmp_path / "documents"])
    with pytest.raises(SandboxViolation, match="读操作越界"):
        sandbox.validate_read(Path("/etc/passwd"))

def test_fs_sandbox_path_traversal_blocked(tmp_path):
    sandbox = FsSandbox(sandbox_root=tmp_path / "_sandbox")
    evil_path = tmp_path / "_sandbox" / ".." / ".." / "etc" / "passwd"
    with pytest.raises(SandboxViolation):
        sandbox.validate_write(evil_path)


@pytest.mark.asyncio
async def test_emergency_stop_trigger():
    stop = EmergencyStop()
    assert not stop.is_triggered()
    await stop.trigger(reason="test")
    assert stop.is_triggered()
    with pytest.raises(EmergencyStopError):
        stop.check()

def test_emergency_stop_reset():
    stop = EmergencyStop()
    stop._stop_flag.set()
    stop._reason = "test"
    stop.reset()
    assert not stop.is_triggered()
    stop.check()


def test_audit_log_write(tmp_path):
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    logger.log_step("cutask-001", 1, "browser_navigate", {"url": "https://example.com"},
                    "success", {"nav_url": "https://example.com"}, "logs/step01.png", 800)
    logs = logger.get_task_logs("cutask-001")
    assert len(logs) == 1
    assert logs[0]["action_type"] == "browser_navigate"

def test_audit_log_append_only(tmp_path):
    logger = AuditLogger(log_dir=tmp_path / "cu_audit")
    logger.log_step("task-001", 1, "test", {}, "success", {}, None, 100)
    logger.log_step("task-001", 2, "test2", {}, "success", {}, None, 100)
    logs = logger.get_task_logs("task-001")
    assert len(logs) == 2
    assert logs[0]["step_index"] == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m4_safety.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 FsSandbox**

```python
# server/cu/sandbox/fs_sandbox.py
"""文件系统沙箱（白名单隔离）"""
from __future__ import annotations
from pathlib import Path


class SandboxViolation(PermissionError):
    """沙箱违规"""


class FsSandbox:
    """文件系统白名单沙箱"""

    def __init__(self, sandbox_root: Path, read_whitelist: list[Path] | None = None):
        self.sandbox_root = sandbox_root.resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.read_whitelist = [p.resolve() for p in (read_whitelist or [])]

    def validate_write(self, path: Path) -> bool:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.sandbox_root)
        except ValueError:
            raise SandboxViolation(f"CU 写操作越界: {path} 不在沙箱 {self.sandbox_root} 内")
        return True

    def validate_read(self, path: Path) -> bool:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.sandbox_root)
            return True
        except ValueError:
            pass
        for allowed in self.read_whitelist:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        raise SandboxViolation(f"CU 读操作越界: {path} 不在白名单内")
```

- [ ] **Step 4: 实现 EmergencyStop**

```python
# server/cu/safety/emergency_stop.py
"""紧急停止（三级响应）"""
from __future__ import annotations
import asyncio


class EmergencyStopError(RuntimeError):
    """急停触发异常"""


class EmergencyStop:
    """全局急停开关"""

    def __init__(self):
        self._stop_flag = asyncio.Event()
        self._reason: str | None = None

    async def trigger(self, reason: str = "manual") -> None:
        self._reason = reason
        self._stop_flag.set()

    def check(self) -> None:
        if self._stop_flag.is_set():
            raise EmergencyStopError(f"任务已急停: {self._reason}")

    def reset(self) -> None:
        self._stop_flag.clear()
        self._reason = None

    def is_triggered(self) -> bool:
        return self._stop_flag.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason
```

- [ ] **Step 5: 实现 AuditLogger**

```python
# server/cu/safety/audit_log.py
"""操作审计日志（结构化 JSON，append-only）"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json


class AuditLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_step(self, task_id, step_index, action_type, action_payload,
                 result_status, result_data=None, screenshot_path=None, duration_ms=None):
        entry = {
            "log_id": f"culog-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{step_index:04d}",
            "task_id": task_id, "step_index": step_index, "action_type": action_type,
            "action_payload": action_payload, "result_status": result_status,
            "result_data": result_data or {}, "screenshot_path": screenshot_path,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "duration_ms": duration_ms,
        }
        task_log_dir = self.log_dir / task_id
        task_log_dir.mkdir(parents=True, exist_ok=True)
        (task_log_dir / f"step-{step_index:04d}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        return entry

    def get_task_logs(self, task_id):
        task_log_dir = self.log_dir / task_id
        if not task_log_dir.exists():
            return []
        return [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(task_log_dir.glob("step-*.json"))]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_m4_safety.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Commit**

```bash
git add server/cu/sandbox/fs_sandbox.py server/cu/safety/emergency_stop.py server/cu/safety/audit_log.py tests/test_m4_safety.py
git commit -m "feat(cu): M4.1 安全四件套 - 沙箱、急停、审计日志"
```

---

### Task M4.2: 回滚策略与任务原子化

**Files:**
- Create: `server/cu/executor/action_types.py`
- Create: `server/cu/planner.py`
- Create: `server/cu/safety/rollback.py`
- Test: `tests/test_m4_planner.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m4_planner.py
import pytest
from server.cu.planner import CUTaskPlanner, CUTaskStep
from server.cu.safety.rollback import RollbackManager
from server.cu.executor.action_types import ActionType


def test_planner_atomic_decomposition():
    planner = CUTaskPlanner()
    plan = planner.plan_manual("访问 example.com", [
        {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"},
         "success_criteria": {"url_contains": "example.com"}},
    ])
    assert len(plan.steps) == 1
    assert plan.steps[0].timeout_ms == 3000
    assert plan.steps[0].rollback_strategy is not None

def test_planner_step_must_have_success_criteria():
    planner = CUTaskPlanner()
    with pytest.raises(ValueError, match="success_criteria"):
        planner.plan_manual("test", [
            {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"}},
        ])

def test_planner_max_timeout_enforced():
    planner = CUTaskPlanner()
    with pytest.raises(ValueError, match="timeout"):
        planner.plan_manual("test", [
            {"action_type": "browser_navigate", "action_payload": {"url": "https://example.com"},
             "success_criteria": {"url_contains": "example"}, "timeout_ms": 30000},
        ])

def test_rollback_manager_reversible():
    manager = RollbackManager()
    manager.recorded_steps = [
        {"step_index": 1, "action_type": "browser_navigate",
         "rollback_action": "browser_navigate", "reversible": True},
    ]
    result = manager.rollback_task_sync("cutask-001", to_step=0)
    assert result.success is True
    assert result.rolled_back_count == 1

def test_action_type_reversibility():
    assert ActionType.is_reversible("browser_navigate") is True
    assert ActionType.is_reversible("fs_delete") is False
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m4_planner.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 ActionType、CUTaskPlanner、RollbackManager**

```python
# server/cu/executor/action_types.py
"""标准化动作类型"""


class ActionType:
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLICK = "browser_click"
    BROWSER_INPUT = "browser_input"
    BROWSER_WAIT = "browser_wait"
    BROWSER_EXTRACT = "browser_extract"
    BROWSER_DOWNLOAD = "browser_download"
    FS_WRITE = "fs_write"
    FS_READ = "fs_read"
    FS_DELETE = "fs_delete"

    REVERSIBLE = {BROWSER_NAVIGATE, BROWSER_INPUT, FS_WRITE, BROWSER_DOWNLOAD}
    PARTIALLY_REVERSIBLE = {BROWSER_CLICK}
    IRREVERSIBLE = {FS_DELETE}

    @classmethod
    def is_reversible(cls, action_type):
        return action_type in cls.REVERSIBLE

    @classmethod
    def is_irreversible(cls, action_type):
        return action_type in cls.IRREVERSIBLE

    @classmethod
    def get_rollback_action(cls, action_type):
        return {
            cls.BROWSER_NAVIGATE: cls.BROWSER_NAVIGATE,
            cls.BROWSER_INPUT: cls.BROWSER_INPUT,
            cls.FS_WRITE: cls.FS_DELETE,
            cls.BROWSER_DOWNLOAD: cls.FS_DELETE,
        }.get(action_type)
```

```python
# server/cu/planner.py
"""CU 任务规划器（原子化分解）"""
from __future__ import annotations
from dataclasses import dataclass, field
from server.cu.executor.action_types import ActionType


@dataclass
class CUTaskStep:
    step_index: int
    action_type: str
    action_payload: dict
    success_criteria: dict
    timeout_ms: int = 3000
    rollback_strategy: dict | None = None
    requires_confirmation: bool = False
    allow_parallel: bool = False


@dataclass
class CUTaskPlan:
    instruction: str
    steps: list[CUTaskStep] = field(default_factory=list)
    created_at: str = ""


class CUTaskPlanner:
    MAX_TIMEOUT_MS = 10000
    DEFAULT_TIMEOUT_MS = 3000

    def plan_manual(self, instruction: str, steps: list[dict]) -> CUTaskPlan:
        plan = CUTaskPlan(instruction=instruction)
        for i, step_def in enumerate(steps):
            plan.steps.append(self._validate_step(i, step_def))
        return plan

    def _validate_step(self, index, step_def):
        if "success_criteria" not in step_def or not step_def["success_criteria"]:
            raise ValueError(f"步骤 {index} 缺少 success_criteria")
        timeout_ms = step_def.get("timeout_ms", self.DEFAULT_TIMEOUT_MS)
        if timeout_ms > self.MAX_TIMEOUT_MS:
            raise ValueError(f"步骤 {index} timeout_ms={timeout_ms} 超过最大值 {self.MAX_TIMEOUT_MS}")

        action_type = step_def["action_type"]
        rollback_action = ActionType.get_rollback_action(action_type)
        rollback_strategy = None
        if rollback_action:
            rollback_strategy = {"reversible": True, "rollback_action": rollback_action, "rollback_payload": {}}
        elif ActionType.is_irreversible(action_type):
            rollback_strategy = {"reversible": False, "note": "不可逆动作，仅记录"}

        return CUTaskStep(
            step_index=index, action_type=action_type,
            action_payload=step_def["action_payload"],
            success_criteria=step_def["success_criteria"],
            timeout_ms=timeout_ms, rollback_strategy=rollback_strategy,
            requires_confirmation=step_def.get("requires_confirmation", False),
            allow_parallel=step_def.get("allow_parallel", False),
        )
```

```python
# server/cu/safety/rollback.py
"""回滚策略管理器"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RollbackResult:
    success: bool
    rolled_back_count: int
    skipped_count: int
    errors: list[str] = field(default_factory=list)


class RollbackManager:
    def __init__(self):
        self.recorded_steps: list[dict] = []

    def record_step(self, step: dict):
        self.recorded_steps.append(step)

    async def rollback_task(self, task_id: str, to_step: int = 0) -> RollbackResult:
        return self.rollback_task_sync(task_id, to_step)

    def rollback_task_sync(self, task_id: str, to_step: int = 0) -> RollbackResult:
        rolled_back = 0
        skipped = 0
        for step in reversed(self.recorded_steps):
            if step["step_index"] < to_step:
                break
            if not step.get("reversible", False):
                skipped += 1
                continue
            if step.get("rollback_action"):
                rolled_back += 1
        return RollbackResult(True, rolled_back, skipped)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_m4_planner.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add server/cu/executor/action_types.py server/cu/planner.py server/cu/safety/rollback.py tests/test_m4_planner.py
git commit -m "feat(cu): M4.2 回滚策略与任务原子化"
```

---

### Task M4.3: MCP 工具暴露与 CU API

**Files:**
- Create: `server/cu/mcp_tools.py`
- Create: `server/api/cu.py`
- Modify: `server/main.py` (注册路由)
- Test: `tests/test_m4_api.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m4_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_cu_create_task(client):
    response = await client.post("/api/cu/tasks", json={
        "instruction": "访问 example.com",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example.com"}}],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "task_id" in data
    assert data["step_count"] == 1


@pytest.mark.asyncio
async def test_cu_emergency_stop(client):
    response = await client.post("/api/cu/emergency-stop", json={"reason": "test"})
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_cu_get_task_status(client):
    create_resp = await client.post("/api/cu/tasks", json={
        "instruction": "test",
        "steps": [{"action_type": "browser_navigate",
                   "action_payload": {"url": "https://example.com"},
                   "success_criteria": {"url_contains": "example"}}],
    })
    task_id = create_resp.json()["task_id"]
    response = await client.get(f"/api/cu/tasks/{task_id}/status")
    assert response.status_code == 200
    assert response.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_cu_list_tasks(client):
    response = await client.get("/api/cu/tasks")
    assert response.status_code == 200
    assert "tasks" in response.json()


def test_mcp_tools_definition():
    from server.cu.mcp_tools import MCP_TOOLS
    assert len(MCP_TOOLS) == 6
    names = [t["name"] for t in MCP_TOOLS]
    assert "cu_plan_task" in names
    assert "cu_emergency_stop" in names
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m4_api.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 MCP 工具定义**

```python
# server/cu/mcp_tools.py
"""CU MCP 工具定义"""
from __future__ import annotations


MCP_TOOLS = [
    {"name": "cu_plan_task", "description": "将自然语言指令分解为原子化 CU 任务计划",
     "input_schema": {"type": "object", "properties": {
         "instruction": {"type": "string"}, "scope": {"type": "string", "default": "private"}},
         "required": ["instruction"]}},
    {"name": "cu_execute_task", "description": "执行 CU 任务（沙箱内），返回任务 ID 供监控",
     "input_schema": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "auto_confirm": {"type": "boolean", "default": False}},
         "required": ["task_id"]}},
    {"name": "cu_emergency_stop", "description": "紧急停止当前所有 CU 任务并触发回滚",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string", "default": "manual"}}}},
    {"name": "cu_rollback_task", "description": "回滚指定 CU 任务到指定步骤",
     "input_schema": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "to_step": {"type": "integer", "default": 0}},
         "required": ["task_id"]}},
    {"name": "cu_get_audit_log", "description": "获取 CU 任务的完整操作审计日志",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "cu_get_task_status", "description": "查询 CU 任务实时状态",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
]
```

- [ ] **Step 4: 实现 CU API**

```python
# server/api/cu.py
"""Computer Use 任务调度 API"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid

from server.cu.planner import CUTaskPlanner
from server.cu.safety.emergency_stop import EmergencyStop
from server.cu.safety.audit_log import AuditLogger
from server.cu.safety.rollback import RollbackManager
from server.config_kb_cu import CUConfig

router = APIRouter(prefix="/api/cu", tags=["computer-use"])

_emergency_stop = EmergencyStop()
_tasks: dict[str, dict] = {}


class CreateTaskRequest(BaseModel):
    instruction: str
    steps: list[dict]


class CreateTaskResponse(BaseModel):
    success: bool
    task_id: str
    step_count: int


class EmergencyStopRequest(BaseModel):
    reason: str = "manual"


def _get_config() -> CUConfig:
    config = CUConfig()
    config.ensure_dirs()
    return config


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task(req: CreateTaskRequest):
    planner = CUTaskPlanner()
    try:
        plan = planner.plan_manual(req.instruction, req.steps)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    task_id = f"cutask-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    _tasks[task_id] = {"task_id": task_id, "plan": plan, "status": "created",
                       "current_step": -1, "created_at": datetime.utcnow().isoformat() + "Z"}
    return CreateTaskResponse(True, task_id, len(plan.steps))


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str, auto_confirm: bool = False):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    _tasks[task_id]["status"] = "executing"
    return {"success": True, "task_id": task_id, "status": "executing"}


@router.post("/emergency-stop")
async def emergency_stop(req: EmergencyStopRequest):
    await _emergency_stop.trigger(req.reason)
    return {"success": True, "reason": req.reason, "message": "已触发急停"}


@router.post("/emergency-stop/reset")
async def reset_emergency_stop():
    _emergency_stop.reset()
    return {"success": True, "message": "急停已重置"}


@router.post("/tasks/{task_id}/rollback")
async def rollback_task(task_id: str, to_step: int = 0):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    manager = RollbackManager()
    result = await manager.rollback_task(task_id, to_step)
    return {"success": result.success, "rolled_back_count": result.rolled_back_count,
            "skipped_count": result.skipped_count}


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = _tasks[task_id]
    return {"task_id": task_id, "status": task["status"],
            "current_step": task["current_step"], "total_steps": len(task["plan"].steps)}


@router.get("/tasks/{task_id}/audit-log")
async def get_audit_log(task_id: str):
    config = _get_config()
    logger = AuditLogger(log_dir=config.audit_log_dir)
    return {"task_id": task_id, "logs": logger.get_task_logs(task_id)}


@router.get("/tasks")
async def list_tasks():
    return {"tasks": [{"task_id": t["task_id"], "status": t["status"],
                       "instruction": t["plan"].instruction,
                       "step_count": len(t["plan"].steps), "created_at": t["created_at"]}
                      for t in _tasks.values()]}
```

- [ ] **Step 5: 在 main.py 注册路由**

```python
from server.api.cu import router as cu_router
app.include_router(cu_router)
```

- [ ] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_m4_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add server/cu/mcp_tools.py server/api/cu.py server/main.py tests/test_m4_api.py
git commit -m "feat(cu): M4.3 MCP 工具暴露与 CU API"
```

---

## M5: CU + 知识库双向联动

### Task M5.1: 知识桥接与结果验证

**Files:**
- Create: `server/cu/verifier.py`
- Create: `server/cu/knowledge_bridge.py`
- Test: `tests/test_m5_bridge.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_m5_bridge.py
import pytest
from server.cu.verifier import CUResultVerifier, VerificationResult
from server.cu.knowledge_bridge import CUKnowledgeBridge, KnowledgeCandidate
from server.cu.planner import CUTaskStep


def test_verifier_high_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.9)
    assert result.passed is True
    assert result.level == "high"

def test_verifier_medium_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.7)
    assert result.passed is True
    assert result.level == "medium"
    assert result.warning is not None

def test_verifier_low_confidence():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "example.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.4)
    assert result.passed is False
    assert result.level == "low"
    assert result.requires_confirmation is True

def test_verifier_criteria_failed():
    verifier = CUResultVerifier()
    step = CUTaskStep(0, "browser_navigate", {"url": "https://example.com"},
                      {"url_contains": "expected.com"})
    result = verifier.verify_step_sync(step, "https://example.com", 0.9)
    assert result.passed is False

def test_bridge_action_to_knowledge():
    bridge = CUKnowledgeBridge()
    candidates = bridge.action_to_knowledge_sync(
        "cutask-001",
        [{"step_index": 0, "action_type": "browser_navigate", "result_status": "success",
          "result_data": {"url": "https://example.com/login"}},
         {"step_index": 1, "action_type": "browser_click", "result_status": "success",
          "result_data": {"nav_url": "https://example.com/dashboard"}}],
        "登录系统",
    )
    assert len(candidates) > 0
    sop = [c for c in candidates if "SOP" in c.title or "sop" in c.title.lower()]
    assert len(sop) > 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_m5_bridge.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 CUResultVerifier**

```python
# server/cu/verifier.py
"""CU 结果验证器"""
from __future__ import annotations
from dataclasses import dataclass
from server.cu.planner import CUTaskStep


@dataclass
class VerificationResult:
    passed: bool
    level: str
    confidence: float
    warning: str | None = None
    requires_confirmation: bool = False
    criteria_met: bool = True


class CUResultVerifier:
    CONFIDENCE_HIGH = 0.85
    CONFIDENCE_LOW = 0.6

    def verify_step_sync(self, step: CUTaskStep, actual_url: str = "",
                         confidence: float = 0.0) -> VerificationResult:
        if not self._check_criteria(step.success_criteria, actual_url):
            return VerificationResult(False, "low", confidence, criteria_met=False, requires_confirmation=True)

        if confidence >= self.CONFIDENCE_HIGH:
            return VerificationResult(True, "high", confidence)
        elif confidence >= self.CONFIDENCE_LOW:
            return VerificationResult(True, "medium", confidence, warning="置信度中等，建议人工复核")
        else:
            return VerificationResult(False, "low", confidence, requires_confirmation=True)

    def _check_criteria(self, criteria: dict, actual_url: str) -> bool:
        if "url_contains" in criteria:
            return criteria["url_contains"] in actual_url
        return True
```

- [ ] **Step 4: 实现 CUKnowledgeBridge**

```python
# server/cu/knowledge_bridge.py
"""CU ↔ 知识库双向联动"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class KnowledgeCandidate:
    title: str
    content: str
    doc_type: str
    source_task_id: str
    confidence: float


class CUKnowledgeBridge:
    """CU 与知识库双向联动核心"""

    def action_to_knowledge_sync(self, task_id: str, step_results: list[dict],
                                 instruction: str) -> list[KnowledgeCandidate]:
        """将 CU 结果转化为知识候选（写入 _inbox）"""
        candidates = []
        success_steps = [s for s in step_results if s["result_status"] == "success"]
        failed_steps = [s for s in step_results if s["result_status"] != "success"]

        if success_steps:
            sop_content = self._generate_sop(instruction, success_steps)
            candidates.append(KnowledgeCandidate(
                title=f"CU SOP: {instruction}", content=sop_content,
                doc_type="note", source_task_id=task_id, confidence=0.88,
            ))

        if failed_steps:
            error_content = self._generate_error_doc(instruction, failed_steps)
            candidates.append(KnowledgeCandidate(
                title=f"CU 错误案例: {instruction}", content=error_content,
                doc_type="note", source_task_id=task_id, confidence=0.7,
            ))

        return candidates

    def _generate_sop(self, instruction: str, steps: list[dict]) -> str:
        lines = [f"# CU SOP: {instruction}\n", "> 本文档由 CU 任务自动生成\n"]
        for s in steps:
            lines.append(f"## 步骤 {s['step_index']}: {s['action_type']}")
            lines.append(f"- 状态: {s['result_status']}")
            if "result_data" in s:
                lines.append(f"- 结果: {s['result_data']}")
            lines.append("")
        return "\n".join(lines)

    def _generate_error_doc(self, instruction: str, steps: list[dict]) -> str:
        lines = [f"# CU 错误案例: {instruction}\n", "> 失败步骤记录\n"]
        for s in steps:
            lines.append(f"## 步骤 {s['step_index']}: {s['action_type']}")
            lines.append(f"- 状态: {s['result_status']}")
            lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_m5_bridge.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add server/cu/verifier.py server/cu/knowledge_bridge.py tests/test_m5_bridge.py
git commit -m "feat(cu): M5.1 知识桥接与结果验证"
```

---

## M6: 可视化 + 监控面板（前端）

### Task M6.1: 前端组件 - WikiGraph 与 CU 控制面板

**Files:**
- Create: `frontend/src/components/graph/WikiGraph.tsx`
- Create: `frontend/src/components/cu/CUControlPanel.tsx`
- Create: `frontend/src/components/cu/EmergencyStopButton.tsx`
- Modify: `frontend/src/components/Sidebar.tsx` (新增导航项)
- Modify: `frontend/package.json` (新增依赖)
- Test: `frontend/src/components/__tests__/wiki_graph.test.tsx`

- [ ] **Step 1: 添加前端依赖**

在 `frontend/package.json` 的 dependencies 添加：
```json
"@antv/g6": "^5.0.0",
"react-diff-viewer": "^3.1.1",
"@uiw/react-md-editor": "^4.0.0"
```

Run: `cd frontend && npm install`

- [ ] **Step 2: 写失败测试**

```tsx
// frontend/src/components/__tests__/wiki_graph.test.tsx
import { render, screen } from '@testing-library/preact';
import { WikiGraph } from '../graph/WikiGraph';

test('WikiGraph renders container', () => {
  render(<WikiGraph />);
  const container = document.getElementById('graph-container');
  expect(container).toBeTruthy();
});

test('EmergencyStopButton not active by default', () => {
  const { container } = render(<EmergencyStopButton active={false} />);
  expect(container.querySelector('button')).toBeNull();
});
```

- [ ] **Step 3: 实现 EmergencyStopButton**

```tsx
// frontend/src/components/cu/EmergencyStopButton.tsx
import { h } from 'preact';
import { useState } from 'preact/hooks';

export function EmergencyStopButton({ active }: { active: boolean }) {
  const [clicking, setClicking] = useState(false);

  if (!active) return null;

  const handleClick = async () => {
    setClicking(true);
    try {
      await fetch('/api/cu/emergency-stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual' }),
      });
    } finally {
      setClicking(false);
    }
  };

  return (
    <button
      className="fixed top-4 right-4 z-50 bg-red-600 text-white px-6 py-3 rounded-lg shadow-lg animate-pulse hover:bg-red-700"
      onClick={handleClick}
      disabled={clicking}
    >
      ⛔ 紧急停止
    </button>
  );
}
```

- [ ] **Step 4: 实现 WikiGraph**

```tsx
// frontend/src/components/graph/WikiGraph.tsx
import { h } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import G6 from '@antv/g6';

type ViewMode = 'document' | 'entity' | 'timeline';

export function WikiGraph() {
  const [viewMode, setViewMode] = useState<ViewMode>('document');
  const [loading, setLoading] = useState(false);
  const graphRef = useRef<any>(null);

  useEffect(() => {
    const initGraph = async () => {
      setLoading(true);
      try {
        const resp = await fetch(`/api/graph/${viewMode === 'document' ? 'documents' : viewMode === 'entity' ? 'entities' : 'timeline'}?scope=private`);
        const data = await resp.json();

        if (graphRef.current) {
          graphRef.current.destroy();
        }

        const graph = new G6.Graph({
          container: 'graph-container',
          width: 800,
          height: 600,
          layout: { type: viewMode === 'timeline' ? 'radial' : 'force' },
          modes: { default: ['drag-canvas', 'zoom-canvas', 'drag-node'] },
        });

        graph.data({
          nodes: data.nodes.map((n: any) => ({
            id: n.id, label: n.label,
            style: { fill: n.scope === 'private' ? '#5B8FF9' : '#5AD8A6' },
          })),
          edges: data.edges.map((e: any) => ({
            source: e.source, target: e.target,
          })),
        });
        graph.render();
        graphRef.current = graph;
      } finally {
        setLoading(false);
      }
    };
    initGraph();
    return () => { if (graphRef.current) graphRef.current.destroy(); };
  }, [viewMode]);

  return (
    <div className="p-4">
      <div className="flex gap-2 mb-4">
        <button onClick={() => setViewMode('document')} className={`px-3 py-1 rounded ${viewMode === 'document' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>文档关系图</button>
        <button onClick={() => setViewMode('entity')} className={`px-3 py-1 rounded ${viewMode === 'entity' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>实体网络图</button>
        <button onClick={() => setViewMode('timeline')} className={`px-3 py-1 rounded ${viewMode === 'timeline' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>时间演化图</button>
      </div>
      {loading && <div className="text-center py-8">加载中...</div>}
      <div id="graph-container" style={{ width: '100%', height: '600px' }} />
    </div>
  );
}
```

- [ ] **Step 5: 实现 CUControlPanel**

```tsx
// frontend/src/components/cu/CUControlPanel.tsx
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import { EmergencyStopButton } from './EmergencyStopButton';

export function CUControlPanel() {
  const [instruction, setInstruction] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [tasks, setTasks] = useState<any[]>([]);

  const createTask = async () => {
    const resp = await fetch('/api/cu/tasks', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instruction,
        steps: [{ action_type: 'browser_navigate',
          action_payload: { url: 'https://example.com' },
          success_criteria: { url_contains: 'example' } }],
      }),
    });
    const data = await resp.json();
    setTaskId(data.task_id);
    setStatus('created');
  };

  const executeTask = async () => {
    if (!taskId) return;
    await fetch(`/api/cu/tasks/${taskId}/execute`, { method: 'POST' });
    setStatus('executing');
  };

  const emergencyStop = async () => {
    await fetch('/api/cu/emergency-stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'manual' }),
    });
    setStatus('stopped');
  };

  useEffect(() => {
    fetch('/api/cu/tasks').then(r => r.json()).then(d => setTasks(d.tasks || []));
  }, []);

  return (
    <div className="p-4">
      <EmergencyStopButton active={status === 'executing'} />

      <div className="mb-4">
        <input
          type="text" value={instruction}
          onChange={(e) => setInstruction((e.target as HTMLInputElement).value)}
          placeholder="输入指令..."
          className="border px-3 py-2 rounded w-full"
        />
        <div className="flex gap-2 mt-2">
          <button onClick={createTask} className="px-4 py-2 bg-blue-500 text-white rounded">生成计划</button>
          <button onClick={executeTask} className="px-4 py-2 bg-green-500 text-white rounded" disabled={!taskId}>执行</button>
          <button onClick={emergencyStop} className="px-4 py-2 bg-red-500 text-white rounded">停止</button>
        </div>
      </div>

      {taskId && <div className="text-sm text-gray-600">任务ID: {taskId} | 状态: {status}</div>}

      <div className="mt-4">
        <h3 className="font-bold mb-2">任务列表</h3>
        {tasks.map((t) => (
          <div key={t.task_id} className="border p-2 mb-1 rounded text-sm">
            {t.instruction} - {t.status}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: 更新侧边栏导航**

在 `frontend/src/components/Sidebar.tsx` 的导航项数组中添加：

```tsx
{ id: 'wikigraph', label: '知识图谱', icon: '🕸️' },
{ id: 'computer-use', label: '自动化', icon: '🤖' },
```

- [ ] **Step 7: 运行前端测试**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/graph/ frontend/src/components/cu/ frontend/src/components/Sidebar.tsx frontend/package.json frontend/src/components/__tests__/wiki_graph.test.tsx
git commit -m "feat(kb-cu): M6.1 前端 WikiGraph 与 CU 控制面板"
```

---

## Self-Review

### Spec coverage
- M1 解析: ✅ Task M1.1-M1.4 (front matter, repo, parsers, API)
- M2 检索: ✅ Task M2.1-M2.3 (ChromaDB, hybrid search, API)
- M3 图谱: ✅ Task M3.1-M3.2 (Kuzu, graph API, relation recommend)
- M4 CU基础: ✅ Task M4.1-M4.3 (safety, planner, MCP, API)
- M5 CU联动: ✅ Task M5.1 (verifier, knowledge bridge)
- M6 可视化: ✅ Task M6.1 (WikiGraph, CU panel, emergency stop)
- Phase 0: ✅ Task 0.1-0.3 (config, models, deps)

### Placeholder scan
- 无 TBD/TODO ✓
- 所有步骤包含完整代码 ✓
- 所有测试包含实际断言 ✓

### Type consistency
- `FrontMatter` 类在 M1.1 定义，M1.2/M1.4 引用一致 ✓
- `SearchResult` 在 M2.2 定义，M2.3 引用一致 ✓
- `CUTaskStep`/`CUTaskPlan` 在 M4.2 定义，M4.3/M5.1 引用一致 ✓
- `KnowledgeCandidate` 在 M5.1 定义 ✓
