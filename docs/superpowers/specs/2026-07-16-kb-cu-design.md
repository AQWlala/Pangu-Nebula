# 轻量级 GraphRAG 知识库 + Computer Use 架构设计

**日期**: 2026-07-16
**项目**: Pangu Nebula
**状态**: 已通过七专家评审，待实施

---

## 1. 概述

### 1.1 目标
为 Pangu Nebula 增加轻量级多模态知识库与 Computer Use (GUI 自动化) 能力，实现：
- 向量查询、可视知识图谱、文档关系推荐
- 混合检索、自动分类、多模态解析
- Computer Use 与知识库深度集成
- CU 操作全链路可审计、可中断、可回滚

### 1.2 用户画像
开发者为小白，追求低运维、可解释、安全可控。

### 1.3 关键约束
- CU 必须与知识库深度集成且写入安全
- 所有 CU 操作必须可审计、可中断、可回滚
- 拒绝 RAGFlow / Neo4j Enterprise / 本地 OCR/CV / 无沙箱裸机 CU 执行

### 1.4 技术栈强制要求
| 组件 | 选型 |
|---|---|
| 知识本体存储 | 本地 Markdown + YAML Front Matter（唯一事实来源） |
| 元数据索引 | SQLite |
| 向量检索 | LlamaIndex + ChromaDB（嵌入式） |
| 图谱引擎 | LightRAG + Kuzu（嵌入式，增量更新） |
| 文档解析 | Marker + Pandas + Qwen-VL/GPT-4o API 插槽（当前仅本地解析） |
| Computer Use | Browser-Use + Playwright + FastAPI MCP Server |
| 可视化前端 | AntV G6 + Preact + CU 操作实时预览面板 |
| 后端接口 | Python FastAPI |
| 禁止项 | ❌ RAGFlow ❌ Neo4j Enterprise ❌ Rust/Tauri（用于 CU/KB 新功能）❌ 本地 OCR/CV ❌ 无沙箱裸机 CU |

### 1.5 集成策略
**方案 A: 全量替换** — 替换现有 mock 实现（rag_service.py TF-IDF mock、computer_use_rust.py Rust mock）为真实 Python 实现。现有 Tauri 2 外壳保留为桌面容器，CU/KB 新功能全部用 Python 实现。

---

## 2. 整体架构与目录结构

### 2.1 目录结构

```
server/
├── kb/                          # 知识库核心 (M1-M3)
│   ├── __init__.py
│   ├── parser/                  # M1: 文档解析
│   │   ├── __init__.py
│   │   ├── markdown_parser.py   # MD + YAML front matter 解析
│   │   ├── pdf_parser.py        # Marker PDF→MD
│   │   ├── office_parser.py     # Pandas Excel/Word→MD
│   │   ├── image_parser.py      # 多模态API插槽(降级占位)
│   │   └── validator.py         # 解析校验 + 置信度阈值
│   ├── storage/                 # Markdown 中心存储
│   │   ├── __init__.py
│   │   ├── repo.py              # 本地 MD 文件仓库 (CRUD)
│   │   ├── frontmatter.py       # YAML front matter 读写
│   │   └── inbox.py             # _inbox/ 暂存回写
│   ├── retrieval/               # M2: 向量检索
│   │   ├── __init__.py
│   │   ├── indexer.py           # LlamaIndex 索引构建
│   │   ├── vectorstore.py       # ChromaDB 嵌入式存储
│   │   ├── hybrid.py            # 混合检索(向量+关键词+图谱)
│   │   └── scope.py             # 作用域硬隔离过滤
│   └── graph/                   # M3: 知识图谱
│       ├── __init__.py
│       ├── lightrag_engine.py   # LightRAG 增量图谱
│       ├── kuzu_store.py        # Kuzu 嵌入式图数据库
│       └── relation_extractor.py # 文档关系抽取
├── cu/                          # Computer Use 核心 (M4-M5)
│   ├── __init__.py
│   ├── planner.py               # 任务规划(原子化分解)
│   ├── executor/                # 动作执行
│   │   ├── __init__.py
│   │   ├── browser_use_exec.py  # Browser-Use + Playwright
│   │   └── action_types.py      # 标准化动作类型
│   ├── sandbox/                 # 沙箱隔离
│   │   ├── __init__.py
│   │   ├── fs_sandbox.py        # 文件系统白名单
│   │   └── browser_context.py   # Playwright 上下文隔离
│   ├── safety/                  # 安全四件套
│   │   ├── __init__.py
│   │   ├── emergency_stop.py    # 紧急停止
│   │   ├── rollback.py          # 回滚策略
│   │   └── audit_log.py         # 操作日志(结构化JSON)
│   ├── verifier.py              # 结果验证 + 置信度
│   ├── knowledge_bridge.py      # CU↔知识库双向联动
│   └── mcp_tools.py             # MCP Server 工具暴露
├── api/
│   ├── kb.py                    # 知识库 CRUD API
│   ├── cu.py                    # CU 任务调度 API
│   └── graph.py                 # 图谱查询 API (wikigraph)
└── services/
    └── (现有服务保留)

frontend/src/components/
├── knowledge/                   # 知识库组件（新增）
│   ├── KnowledgeBase.tsx
│   ├── DocumentEditor.tsx
│   ├── ImportPanel.tsx
│   ├── ReviewInbox.tsx          # 增强现有 WikiReviewInbox
│   └── SearchPanel.tsx
├── graph/                       # 图谱组件（新增，wikigraph）
│   ├── WikiGraph.tsx
│   ├── GraphToolbar.tsx
│   ├── GraphNodeDetail.tsx
│   └── GraphLegend.tsx
└── cu/                          # CU 控制组件（新增）
    ├── CUControlPanel.tsx
    ├── CUTaskBuilder.tsx
    ├── CUStepViewer.tsx
    ├── CUAuditLog.tsx
    └── EmergencyStopButton.tsx
```

### 2.2 数据存储布局

```
~/.pangu-nebula/
├── knowledge_base/              # 知识库根目录
│   ├── _inbox/                  # CU/Crawler 产出暂存
│   ├── _sandbox/                # CU 文件操作沙箱
│   ├── _archive/                # 归档版本
│   ├── documents/               # Markdown 文档（唯一事实来源）
│   │   ├── note-001.md          # + YAML front matter
│   │   └── ...
│   ├── indexes/
│   │   ├── chroma/              # ChromaDB 向量索引
│   │   └── kuzu/                # Kuzu 图数据库
│   └── meta.db                  # SQLite 元数据索引
└── logs/
    └── cu_audit/                # CU 操作审计日志（JSON）
```

### 2.3 与现有架构的集成点
1. **FastAPI 路由注册**：在 server/main.py 注册 `/api/kb`、`/api/cu`、`/api/graph` 新路由
2. **SQLite 共享**：复用 server/db/engine.py，新增 KB/CU 相关表
3. **MCP Server 复用**：在 server/services/mcp_server.py 注册 CU 工具
4. **前端组件**：新增组件到 frontend/src/components/，侧边栏新增三个导航项

### 2.4 核心架构原则

#### Staged Write-back（暂存回写）
- CU 产生的所有知识写入 → `_inbox/` 暂存 → Diff 预览 → 人工确认 → Merge
- CU 产生的所有文件/系统修改 → `_sandbox/` 隔离执行 → 操作日志记录 → 人工确认 → 应用到真实环境

#### Scoped Retrieval & Action（作用域硬隔离）
- 知识库查询：服务端代码级强制 Scope 过滤
- CU 操作范围：通过 Playwright 上下文隔离 + 文件系统白名单限制

#### Markdown-Centric + Operation Log
- 知识以 Markdown 为主存储；CU 操作以结构化 JSON Log 为主存储
- 两者均可追溯、可重建、可版本控制

#### Computer Use as First-Class Citizen
- CU 是系统内置能力，包含：任务规划、GUI 感知、动作执行、结果验证、异常恢复
- CU 与知识库双向联动：知识指导 CU 操作；CU 操作结果反哺知识库
- 所有 CU 动作必须通过 MCP Server 暴露为标准化工具，禁止硬编码脚本

---

## 3. M1: 文档解析与 Markdown 中心存储

### 3.1 Front Matter Schema 规范

每个知识库 MD 文件头部必须包含 YAML front matter：

```yaml
---
id: kb-20260716-001              # 全局唯一 ID（时间戳+序号）
title: "文档标题"
type: note                        # note | doc | snippet | cu_log
source:                           # 来源溯源
  type: manual                    # manual | import | cu | crawler
  original_path: ""               # 原始文件路径（导入时）
  imported_at: 2026-07-16T10:00:00Z
scope: private                    # private | project | public（作用域硬隔离）
tags: [python, fastapi]
categories: [tech, backend]
relations:                        # 显式关系声明（补充图谱自动抽取）
  - target: kb-20260716-002
    type: references              # references | extends | contradicts | derived_from
    weight: 0.8
confidence: 0.95                  # 内容置信度（CU/解析产出）
checksum: sha256:abc123...        # 内容校验和（检测篡改）
---

# 正文内容（标准 Markdown）
```

### 3.2 解析流水线

```
原始文件 (PDF/Excel/Word/MD/TXT/HTML)
    │
    ▼
FormatDetector  (按扩展名 + magic bytes 分发)
    │
    ├── PDF  ──► PdfParser (Marker) ─────► MD + 图片资产
    ├── Excel ──► OfficeParser (Pandas) ─► MD 表格
    ├── Word ──► OfficeParser (python-docx) ─► MD
    ├── HTML ──► HtmlParser (trafilatura) ─► MD
    ├── IMG  ──► ImageParser (降级占位) ──► MD 描述（待多模态API启用）
    └── MD/TXT ► MarkdownParser ─────────► 直接校验 front matter
    │
    ▼
Validator  (校验 front matter 完整性 / id 唯一性 / scope 合法性 / checksum 一致)
    │
    ▼
InboxWriter  (写入 _inbox/ 等待审核，生成 front matter，计算 checksum，暂存待 Diff 预览)
```

### 3.3 关键设计决策

**Marker 作为 PDF 解析器**：
- 纯 Python，无需 GPU，保留文档结构（标题/段落/表格）
- 降级策略：Marker 失败 → 退回 pypdf 纯文本提取
- 表格识别：Marker 内置表格检测，失败时降级为代码块标注

**Pandas Excel→MD 转换规则**：
- 每个 Sheet → 一个 `## Sheet名称` 二级标题
- 表格 → 标准 MD 表格语法
- 空行/合并单元格 → 显式标注 `<!-- merged: A1:B2 -->`
- 公式 → 保留为 `<!-- formula: =SUM(A1:A10) -->` 注释
- 置信度：转换成功率 ≥ 95% 标记为高置信，否则降级为 `confidence: 0.6`

**图片/扫描件降级策略**（无多模态 API）：
- 提取图片资产到 `documents/assets/`
- MD 中插入 `![image](assets/xxx.png) <!-- 待多模态解析 -->`
- 置信度强制设为 `0.3`
- 预留 `ImageParser.parse_with_vl(api_client, image_path)` 插槽，配置 API Key 后自动启用

**_inbox 暂存回写机制**：
```
_inbox/
├── pending-{timestamp}-{uuid}/
│   ├── original.ext              # 原始文件副本
│   ├── converted.md              # 转换后的 MD
│   ├── frontmatter.yaml          # 待确认的 front matter
│   ├── diff.patch                # 与现有内容的 diff（更新场景）
│   └── meta.json                 # 来源/时间/解析器/置信度
```
- CU 产出和导入产出统一进 `_inbox/`，禁止直写 `documents/`

### 3.4 SQLite 元数据表（新增）

```sql
-- 文档元数据索引（MD 文件的投影）
CREATE TABLE kb_documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    source_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    checksum TEXT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    indexed_at TIMESTAMP,
    graph_built_at TIMESTAMP
);

-- 关系索引（显式 + 自动抽取）
CREATE TABLE kb_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    source_method TEXT NOT NULL,   -- explicit | lightrag | keyword
    created_at TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES kb_documents(id),
    FOREIGN KEY (target_id) REFERENCES kb_documents(id)
);

-- CU 操作审计日志
CREATE TABLE cu_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    action_payload TEXT NOT NULL,
    result_status TEXT NOT NULL,
    result_data TEXT,
    screenshot_path TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER
);
```

---

## 4. M2: 向量检索与混合检索

### 4.1 向量存储选型：ChromaDB 嵌入式

- 纯 Python，`pip install chromadb` 即用
- 嵌入式模式，数据落本地 `~/.pangu-nebula/knowledge_base/indexes/chroma/`
- 无需独立服务进程，与 FastAPI 同进程
- 持久化存储，重启不丢失

**嵌入模型**：
- 默认：`sentence-transformers/all-MiniLM-L6-v2`（本地运行，384 维）
- 切换插槽：通过 config 指定 `embedding_provider`，未来可换 OpenAI/BGE
- 首次使用自动下载模型，缓存到 `~/.cache/torch/sentence_transformers/`

### 4.2 索引构建流水线

```
kb_documents (MD 文件)
    │
    ▼
DocumentLoader (从 documents/ 加载 MD，读取 front matter，按 ## 标题分块)
    │
    ▼
Chunker (LlamaIndex SemanticChunker, chunk_size=512, overlap=50, 保留章节边界)
    │
    ▼
EmbeddingBuilder (本地 MiniLM 批量推理, 附带 metadata: {doc_id, scope, tags, chunk_idx, section})
    │
    ▼
ChromaVectorStore (写入 collection: kb_chunks, upsert 增量更新, checksum 对比跳过未变更)
```

### 4.3 增量索引策略

- 变更检测：扫描 `kb_documents.indexed_at` vs `updated_at`
- 仅对 `updated_at > indexed_at` 的文档重新分块嵌入
- 删除文档时，从 ChromaDB 中按 `where={"doc_id": ...}` 删除对应 chunks
- 全量重建时间 < 10min，增量更新 < 30s

### 4.4 混合检索架构

```
用户查询 query
    │
    ├──► [向量检索] ChromaDB top-k=20
    ├──► [关键词检索] SQLite FTS5 top-k=20 (title + tags + 全文匹配, BM25 排序)
    ├──► [图谱检索] Kuzu 图遍历 2跳邻居 top-k=10
    │
    ▼
FusionRanker (RRF - Reciprocal Rank Fusion)
  - 三路结果按 rank 倒数加权
  - weight: vector=0.5, keyword=0.3, graph=0.2
  - 去重（同一 doc_id 合并）
    │
    ▼
ScopeFilter (E2 硬隔离)
  - 服务端代码级强制过滤 metadata.scope
  - 在 ChromaDB 查询时 where={"scope": user_scope}
  - 在 SQLite 查询时 WHERE scope = ?
  - 双重保险：检索后再次校验 scope
    │
    ▼
返回 top-k=5 结果（含 doc_id, chunk, score, source_method）
```

### 4.5 检索 API

```python
async def hybrid_search(
    query: str,
    scope: str = "private",          # 强制作用域
    top_k: int = 5,
    filters: dict | None = None,     # tags, type, date_range
    methods: list[str] | None = None # ["vector","keyword","graph"] 默认全开
) -> list[SearchResult]:
    """混合检索入口，scope 在此函数内代码级强制过滤"""
```

### 4.6 性能预算

| 检索类型 | 延迟上限 | 实现 |
|---|---|---|
| 纯向量 | < 800ms | ChromaDB HNSW |
| 纯关键词 | < 200ms | SQLite FTS5 |
| 图谱遍历 | < 500ms | Kuzu 2跳 |
| 混合检索 | < 2000ms | 三路并行 + RRF |

### 4.7 关键设计决策

**SQLite FTS5 而非独立关键词引擎**：已有 SQLite，零新增依赖，FTS5 内置 BM25 排序。

**RRF 融合而非交叉编码器重排**：小白场景无需 GPU 重排，RRF 无需训练、可解释。预留 Reranker 接口插槽。

**检索结果溯源**：每个 SearchResult 包含 source_method（vector/keyword/graph），前端展示命中来源。

---

## 5. M3: 知识图谱 + wikigraph 可视化

### 5.1 图谱引擎选型：LightRAG + Kuzu

| 组件 | 职责 | 选型理由 |
|---|---|---|
| LightRAG | 实体抽取、关系推理、图谱增强检索 | 增量更新、轻量级、无需 GPU |
| Kuzu | 图结构持久化存储、Cypher 查询 | 嵌入式、零运维、事务支持 |

### 5.2 图谱构建流水线

```
kb_documents (MD 文件)
    │
    ▼
RelationExtractor (LightRAG)
  - LLM 抽取实体（人物/概念/项目）
  - LLM 抽取关系（属于/依赖/引用）
  - 增量：仅处理新文档/变更文档
  - 置信度阈值：relation < 0.5 丢弃
    │
    ├──► 显式关系（front matter relations 字段）
    ├──► 自动抽取关系（LightRAG）
    └──► 关键词共现关系（同文档/同段落共现）
         │
         ▼ 合并去重
KuzuGraphStore
  - Node: Document/Entity
  - Edge: relation_type
  - 写入 kb_relations 表
  - 增量 upsert
```

### 5.3 Kuzu 图 Schema

```cypher
CREATE NODE TABLE Document (
    id STRING PRIMARY KEY,
    title STRING,
    type STRING,
    scope STRING,
    confidence DOUBLE,
    file_path STRING,
    updated_at TIMESTAMP
);

CREATE NODE TABLE Entity (
    id STRING PRIMARY KEY,
    name STRING,
    entity_type STRING,         // person | concept | project | tool
    description STRING,
    mention_count INT64
);

CREATE REL TABLE References (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP);
CREATE REL TABLE Extends (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP);
CREATE REL TABLE Contradicts (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP);
CREATE REL TABLE DerivedFrom (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP);
CREATE REL TABLE Mentions (FROM Document TO Entity, count INT64, first_seen TIMESTAMP);
CREATE REL TABLE RelatedTo (FROM Entity TO Entity, relation STRING, weight DOUBLE);
```

### 5.4 wikigraph 可视化（AntV G6 v5）

**三种视图**：
1. **文档关系图**：节点=文档，边=references/extends/contradicts/derived_from
2. **实体网络图**：节点=抽取的实体，边=实体间关系
3. **时间演化图**：Radial 布局，按 created_at 排列

**G6 视觉规范**：
| 元素 | 样式 | 编码 |
|---|---|---|
| 文档节点 | 圆形 | 颜色=scope（private蓝/project绿/public橙） |
| 实体节点 | 菱形 | 颜色=entity_type（person人/concept紫/project红） |
| 节点大小 | 半径 10-30 | 连接度越高越大 |
| references 边 | 实线灰 | 引用关系 |
| extends 边 | 实线绿 | 扩展关系 |
| contradicts 边 | 虚线红 | 矛盾关系 |
| derived_from 边 | 点线蓝 | 派生关系 |

**交互**：双击节点→文档详情，悬停边→关系详情，框选→批量操作，布局切换（Force/Dagre/Radial/Circular）

### 5.5 图谱查询 API

```python
@router.get("/graph/documents")      # 文档关系图数据
@router.get("/graph/entities")       # 实体网络图数据
@router.get("/graph/timeline")       # 时间演化图数据
@router.post("/graph/rebuild")       # 手动触发增量重建
```

### 5.6 增量更新策略

- 文档变更触发：`kb_documents.graph_built_at < updated_at` 时标记待构建
- 后台任务：FastAPI BackgroundTasks 异步执行，不阻塞检索
- LightRAG 增量：传入新文档片段，仅抽取新实体/关系，merge 到现有图谱
- Kuzu 事务：批量 upsert 在单事务内完成，失败回滚
- 全量重建 1000 文档 < 10min，增量单文档 < 5s

### 5.7 文档关系推荐

```python
async def recommend_relations(doc_id: str, top_k: int = 5) -> list[RelationRecommendation]:
    """为新文档推荐可能的关系
    策略：
    1. 向量相似文档 → 候选 references
    2. 共享实体文档 → 候选 extends
    3. 关键词重叠高 → 候选 derived_from
    4. 矛盾检测 → 候选 contradicts
    返回带置信度的推荐，写入 _inbox/ 待人工确认
    """
```

### 5.8 关键设计决策

**LightRAG + Kuzu 分离**：LightRAG 专注 NLP 抽取，Kuzu 专注图存储查询。职责分离，可独立替换。

**G6 v5 而非 Neovis.js**：G6 中文文档完善、活跃维护、v5 支持万级节点、内置多种布局。

**图谱数据不作为事实来源**：图谱是 MD 文档的投影，可随时从 MD 重建。

---

## 6. M4: Computer Use 基础（安全四件套 + 任务原子化）

### 6.1 CU 安全四件套

任何 CU 任务必须四件齐备，缺一不可执行：
1. **沙箱隔离**
2. **操作日志**
3. **紧急停止**
4. **回滚策略**

### 6.2 沙箱隔离机制（双层）

**外层：Playwright 浏览器上下文隔离**
- 独立 user_data_dir（临时的）
- 禁用文件下载到真实路径
- 代理白名单（SSRF 防护）
- Cookie/LocalStorage 隔离

**内层：文件系统白名单**
- 仅允许写入 `_sandbox/` 目录
- 读操作：白名单路径列表
- 网络操作：通过 Playwright，禁止直接 requests
- 进程操作：完全禁止

```python
SANDBOX_ROOT = Path("~/.pangu-nebula/knowledge_base/_sandbox/").expanduser()
READ_WHITELIST = [
    Path("~/.pangu-nebula/knowledge_base/documents/").expanduser(),
    Path("/tmp/cu_assets/"),
]

class FsSandbox:
    def validate_write(self, path: Path) -> bool:
        resolved = path.resolve()
        if not str(resolved).startswith(str(SANDBOX_ROOT)):
            raise PermissionError(f"CU 写操作越界: {path} 不在沙箱内")
        return True

    def validate_read(self, path: Path) -> bool:
        resolved = path.resolve()
        for allowed in READ_WHITELIST:
            if str(resolved).startswith(str(allowed)):
                return True
        raise PermissionError(f"CU 读操作越界: {path} 不在白名单内")
```

### 6.3 操作日志（结构化 JSON）

每个原子动作记录：

```json
{
    "log_id": "culog-20260716100000-001",
    "task_id": "cutask-20260716-001",
    "step_index": 3,
    "step_total": 8,
    "action_type": "browser_click",
    "action_payload": {
        "selector": "button#submit",
        "wait_strategy": "visible",
        "timeout_ms": 3000
    },
    "pre_state": {
        "url": "https://example.com/form",
        "screenshot": "logs/cu_audit/task001/step03_pre.png"
    },
    "result_status": "success",
    "result_data": {
        "clicked": true,
        "nav_url": "https://example.com/success"
    },
    "post_state": {
        "url": "https://example.com/success",
        "screenshot": "logs/cu_audit/task001/step03_post.png"
    },
    "rollback_info": {
        "reversible": true,
        "rollback_action": "browser_navigate",
        "rollback_payload": {"url": "https://example.com/form"}
    },
    "started_at": "2026-07-16T10:00:00.123Z",
    "completed_at": "2026-07-16T10:00:01.456Z",
    "duration_ms": 1333
}
```

- 日志同时写入 SQLite `cu_audit_logs` 表和 JSON 文件（双写冗余）
- 每步操作前后自动截图
- 日志不可篡改：append-only，按 task_id 分目录

### 6.4 紧急停止（三级响应）

```python
class EmergencyStop:
    """全局急停开关，三级响应"""

    async def trigger(self, reason: str = "manual") -> None:
        """触发急停：立即停止当前步骤，取消后续所有步骤
        1. 关闭所有 Playwright 浏览器上下文
        2. 取消所有 asyncio.Task
        3. 触发当前任务的回滚流程
        4. 记录急停事件到日志
        """

    def check(self) -> None:
        """每个原子动作执行前必须调用，被触发则抛 EmergencyStopError"""

    def reset(self) -> None:
        """重置急停状态（人工确认后）"""
```

**急停触发途径**（三重保险）：
- 前端「停止」按钮 → `/api/cu/emergency-stop` 端点
- 超时自动触发：单步动作 > 3s 警告，> 10s 自动急停
- 异常检测触发：检测到非预期导航/CPU 飙升/内存异常

### 6.5 回滚策略

```python
class RollbackManager:
    """每个原子动作记录 rollback_info，支持逆序回滚"""

    async def rollback_task(self, task_id: str, to_step: int = 0) -> RollbackResult:
        """回滚指定任务到指定步骤
        - 逆序执行已记录的 rollback_action
        - 不可逆动作标记 irreversible，记录但不执行
        - 文件操作：从 _sandbox/ 恢复到 pre_state
        - 浏览器操作：navigate 回原 URL
        - 回滚结果同样记录日志
        """

    async def rollback_step(self, task_id: str, step_index: int) -> RollbackResult:
        """回滚单个步骤"""
```

**可逆性分类**：
| 动作类型 | 可逆 | 回滚方式 |
|---|---|---|
| browser_navigate | ✅ | navigate 回原 URL |
| browser_click | ⚠️ | 仅能 navigate 回前页（表单提交不可逆） |
| browser_input | ✅ | 清空输入 |
| fs_write | ✅ | 删除文件或恢复备份 |
| fs_delete | ❌ | 不可逆，标记并记录原文 |
| browser_download | ✅ | 删除下载文件 |

### 6.6 任务原子化分解

```python
class CUTaskPlanner:
    """将用户高层指令分解为原子化步骤"""

    async def plan(self, instruction: str, context: dict) -> CUTaskPlan:
        """分解原则（E6 强制）：
        1. 每步只执行一个原子动作（导航/点击/输入/读取/写入）
        2. 每步必须有明确的成功条件（success_criteria）
        3. 每步必须有超时阈值（默认 3s，最大 10s）
        4. 每步必须有回滚策略（或标记 irreversible）
        5. 步骤间显式声明依赖关系（allow_parallel 标记）
        """
```

### 6.7 动作执行器（Browser-Use + Playwright）

```python
class BrowserUseExecutor:
    async def execute_step(self, step: CUTaskStep) -> StepResult:
        """执行单个原子步骤
        1. emergency_stop.check()  # 急停检查
        2. 记录 pre_state + 截图
        3. 执行动作（含 wait_for_selector 显式等待）
        4. 验证 success_criteria（置信度阈值）
        5. 记录 post_state + 截图
        6. 写入 audit_log
        7. 注册 rollback_info
        """

    async def _wait_for_element(self, selector: str, strategy: str, timeout: int):
        """显式元素等待策略
        strategy: visible | attached | stable | enabled
        超时后触发重试（最多2次），仍失败则标记步骤失败
        """
```

### 6.8 MCP 工具暴露

```python
MCP_TOOLS = [
    {"name": "cu_plan_task", "description": "将自然语言指令分解为原子化 CU 任务计划"},
    {"name": "cu_execute_task", "description": "执行 CU 任务（沙箱内），返回任务 ID 供监控"},
    {"name": "cu_emergency_stop", "description": "紧急停止当前所有 CU 任务并触发回滚"},
    {"name": "cu_rollback_task", "description": "回滚指定 CU 任务到指定步骤"},
    {"name": "cu_get_audit_log", "description": "获取 CU 任务的完整操作审计日志"},
    {"name": "cu_get_task_status", "description": "查询 CU 任务实时状态（含当前步骤、截图）"}
]
# 注册到 server/services/mcp_server.py
```

### 6.9 CU API 端点

```python
@router.post("/cu/tasks")               # 创建 CU 任务
@router.post("/cu/tasks/{id}/execute")  # 执行任务
@router.post("/cu/emergency-stop")      # 触发急停
@router.post("/cu/tasks/{id}/rollback") # 回滚任务
@router.get("/cu/tasks/{id}/status")    # 实时状态（SSE）
@router.get("/cu/tasks/{id}/audit-log") # 审计日志
@router.get("/cu/tasks")                # 任务列表
```

### 6.10 关键设计决策

**Browser-Use 而非裸 Playwright**：Browser-Use 提供智能元素定位（LLM 辅助 selector 生成），底层仍是 Playwright，可降级为纯 Playwright。禁止裸机执行：所有 Browser-Use 调用必须经过沙箱+日志包装。

**前后双截图作为操作证据**：每步操作前后自动截图，前端实时展示，截图也是结果验证依据。

**人工确认门控**：高风险动作（fs_delete/表单提交/支付类）标记 `requires_confirmation: true`，执行到此类步骤自动暂停，写入 `_inbox/` 等待人工 approve。

---

## 7. M5: CU + 知识库双向联动

### 7.1 双向联动架构

```
知识库 (MD+图谱) ──知识指导操作──► CU 执行器
知识库 (MD+图谱) ◄─操作结果反哺── CU 执行器
                    │
          联动编排器 CUKnowledgeBridge
```

### 7.2 方向一：知识库指导 CU 操作

```python
class CUKnowledgeBridge:
    async def knowledge_to_action(
        self, instruction: str, scope: str
    ) -> EnhancedCUTaskPlan:
        """用知识库内容增强 CU 任务规划
        1. 从 instruction 中识别关键实体和意图
        2. 检索知识库（M2 混合检索）找相关 SOP/操作记录
        3. 图谱遍历（M3）找关联的操作步骤文档
        4. 将检索到的知识注入 CU Planner 的 context
        5. CU Planner 基于知识生成分步计划
        """
```

知识注入格式：
```json
{
    "instruction": "登录系统并导出报表",
    "retrieved_knowledge": [
        {"doc_id": "kb-...", "title": "系统登录操作SOP", "content": "...", "source": "vector_search", "score": 0.92},
        {"doc_id": "kb-...", "title": "报表导出步骤", "content": "...", "source": "graph_traversal", "score": 0.85}
    ],
    "graph_context": {"related_entities": ["报表系统"], "related_docs": ["kb-..."]}
}
```

### 7.3 方向二：CU 操作结果反哺知识库

```python
class CUKnowledgeBridge:
    async def action_to_knowledge(
        self, task_id: str, step_results: list[StepResult]
    ) -> list[KnowledgeCandidate]:
        """将 CU 执行结果转化为知识库候选条目
        生成内容：
        1. 操作 SOP 文档（成功步骤的标准化记录）
        2. 错误案例文档（失败步骤 + 原因分析）
        3. 页面结构文档（截图 + 元素分析）
        4. 数据提取结果（CU 从页面提取的信息）
        全部写入 _inbox/ 待人工确认（Staged Write-back）
        """
```

反哺知识类型：
| CU 产出 | 转化为 | front matter type | 写入路径 |
|---|---|---|---|
| 成功操作序列 | SOP 文档 | `note` | `_inbox/cu-sop-{task_id}.md` |
| 失败步骤 + 错误 | 错误案例 | `note` | `_inbox/cu-error-{task_id}.md` |
| 页面截图 + 结构 | 页面知识 | `doc` | `_inbox/cu-page-{task_id}.md` |
| 提取的数据表格 | 结构化数据 | `snippet` | `_inbox/cu-data-{task_id}.md` |
| CU 审计日志 | 操作记录 | `cu_log` | `_inbox/cu-log-{task_id}.md` |

### 7.4 CU 任务状态机

```
created → planning → pending_confirm → executing ⇄ paused_confirm
                              │              │
                              │         急停/失败
                              │              ▼
                              │         rolling_back
                              │              │
                              ▼              ▼
                         completed → knowledge_feedback → closed
```

### 7.5 结果验证与置信度

```python
class CUResultVerifier:
    async def verify_step(self, step: CUTaskStep, result: StepResult) -> VerificationResult:
        """验证单步结果
        验证维度：
        1. success_criteria 检查（URL/元素/文本）
        2. 截图对比（pre/post 差异分析）
        3. 置信度计算（综合多维度）
        
        置信度阈值：
        - ≥ 0.85: 高置信，自动通过
        - 0.6-0.85: 中置信，标记 warning 但继续
        - < 0.6: 低置信，暂停等待人工确认
        """

    async def verify_task(self, task_id: str) -> TaskVerification:
        """整体验证：所有步骤是否达成预期目标"""
```

### 7.6 关键设计决策

**反哺必须走 _inbox**：CU 产出的知识绝不直接写入 `documents/`，全部进 `_inbox/` 经 Diff 预览 + 人工确认后 merge。

**知识注入而非硬编码**：CU Planner 从知识库检索 SOP，而非在代码中硬编码流程。知识库更新后，下次 CU 任务自动使用新知识。

**错误也是知识**：失败步骤同样反哺为知识库条目（错误案例），下次相同场景 CU 可检索到并调整策略。

**联动通过 MCP 标准化**：`cu_plan_task` 工具内部自动调用知识检索，`cu_execute_task` 完成后自动触发知识反哺。

---

## 8. M6: 可视化 + 监控面板（前端）

### 8.1 前端组件架构

```
frontend/src/components/
├── knowledge/                   # 知识库组件
│   ├── KnowledgeBase.tsx        # 知识库主页
│   ├── DocumentEditor.tsx       # MD 编辑器
│   ├── ImportPanel.tsx          # 文档导入面板
│   ├── ReviewInbox.tsx          # _inbox 审核面板
│   └── SearchPanel.tsx          # 混合检索面板
├── graph/                       # 图谱组件（wikigraph）
│   ├── WikiGraph.tsx            # G6 主容器
│   ├── GraphToolbar.tsx         # 控制栏
│   ├── GraphNodeDetail.tsx      # 节点详情
│   └── GraphLegend.tsx          # 图例
├── cu/                          # CU 控制组件
│   ├── CUControlPanel.tsx       # CU 任务主控面板
│   ├── CUTaskBuilder.tsx        # 任务构建器
│   ├── CUStepViewer.tsx         # 步骤实时预览
│   ├── CUAuditLog.tsx           # 审计日志查看器
│   └── EmergencyStopButton.tsx  # 全局急停按钮
```

### 8.2 WikiGraph 可视化（AntV G6 v5）

```tsx
export function WikiGraph() {
    const [viewMode, setViewMode] = useState<'document' | 'entity' | 'timeline'>('document');
    const graphRef = useRef<G6.Graph | null>(null);
    const { data, loading } = useGraphData(viewMode, scope);

    const graphConfig = {
        container: 'graph-container',
        layout: viewMode === 'timeline' ? radialLayout : forceLayout,
        modes: { default: ['drag-canvas', 'zoom-canvas', 'drag-node'] },
    };
    // 交互：双击节点→文档详情, 悬停边→关系详情, 框选→批量操作
}
```

### 8.3 CU 实时预览面板

布局包含：
- 任务构建区（指令输入 + 生成计划/执行/暂停/回滚按钮）
- 任务计划列表（步骤进度，✓/►/○ 状态标记）
- 实时预览区（当前步骤截图 + URL + 状态 + 置信度 + 耗时）
- 操作日志（实时滚动）

实时通信：SSE 推送步骤进度，复用现有 apiStream 机制。`/api/cu/tasks/{id}/status` 返回 SSE 流。

### 8.4 Review Inbox 增强

复用现有 WikiReviewInbox.tsx，增强为统一审核中心：
- 分页签：全部 / 文档导入 / CU反哺 / 关系推荐
- Diff 预览：批准 / 拒绝 / 编辑后批准

### 8.5 侧边栏导航更新

新增三个导航项：知识库 📚 / 知识图谱 🕸️ / 自动化 🤖

### 8.6 急停按钮全局常驻

CU 执行期间急停按钮必须始终可见（E2 一票否决），红色闪烁样式，fixed 定位，不受路由切换影响。

### 8.7 前端依赖新增

```json
{
    "dependencies": {
        "@antv/g6": "^5.0.0",
        "react-diff-viewer": "^3.1.1",
        "@uiw/react-md-editor": "^4.0.0"
    }
}
```

### 8.8 关键设计决策

**G6 v5 而非 D3 直接操作**：G6 封装了图可视化常用交互，v5 性能优化支持万级节点。

**SSE 复用现有 apiStream 机制**：项目已有 SSE 基础设施，零新增通信基础设施。

**急停按钮常驻**：CU 执行期间必须始终可见，红色闪烁样式确保视觉警示。

---

## 9. 七专家评审协议

### 9.1 评审流程

```
GENERATE → REVIEW (E1→E2→E3→E4→E5→E6→E7) → 存在VETO? → REVISE (最多3轮) → DELIVER
```

### 9.2 专家面板

| 编号 | 专家角色 | 评审焦点 | 一票否决权 |
|---|---|---|---|
| E1 | 小白体验官 | 技术栈轻量？配置≤3步？CU 安装一键完成？ | Docker >2服务 / CU 需手动配驱动 → 否决 |
| E2 | 安全审计员 | _inbox/_sandbox 完整？SSRF/路径遍历防护？Scope 隔离？急停按钮？ | Direct Write / 无沙箱 CU / 无急停 → 否决 |
| E3 | 架构守门人 | Markdown-Centric？无禁止项？CU 工具 MCP 标准化？组件可替换？ | CU 硬编码 / 向量库当主存 → 否决 |
| E4 | 数据质量师 | 解析校验？Excel→MD 可靠？CU 结果置信度阈值？ | 无解析降级 / CU 结果无校验 → 否决 |
| E5 | 性能优化师 | 检索<2s？图谱增量？CU 单步<3s？嵌入成本合理？ | CU 动作超时 / 全量重建>10min → 否决 |
| E6 | CU 专项专家 | 任务原子化？GUI 定位鲁棒？失败重试/回滚？日志完整？MCP 描述准确？ | 无原子任务 / 无回滚 / 日志缺失 → 否决 |
| E7 | 交付验收官 | 符合里程碑 DoD？测试覆盖边界？CU 端到端用例？下一步明确？ | 无 CU 验收用例 / 无行动项 → 否决 |

### 9.3 评审记录存储

评审记录存档到 `docs/superpowers/reviews/` 目录，YAML front matter + 评审详情。

### 9.4 本设计评审摘要表

| 专家 | 结论 | 关键问题 | 解决状态 |
|---|---|---|---|
| E1 小白体验官 | ✅ PASS | 无 | - |
| E2 安全审计员 | ✅ PASS | 无 | - |
| E3 架构守门人 | ✅ PASS | 无 | - |
| E4 数据质量师 | ✅ PASS | 无 | - |
| E5 性能优化师 | ✅ PASS | 无 | - |
| E6 CU 专项专家 | ✅ PASS | 无 | - |
| E7 交付验收官 | ✅ PASS | 无 | - |

**评审结论**：全票通过，可进入实施阶段。

---

## 10. 里程碑与验收标准

### 10.1 里程碑 DoD

| 里程碑 | 交付物 | 验收标准 |
|---|---|---|
| M1 解析 | parser/ + storage/ + inbox | PDF/Excel/Word/HTML→MD 转换 + front matter 校验 + _inbox 暂存 |
| M2 检索 | retrieval/ + ChromaDB | 混合检索<2s + scope 隔离 + 增量索引 |
| M3 图谱 | graph/ + Kuzu + G6 | LightRAG 抽取 + wikigraph 三视图 + 关系推荐 |
| M4 CU基础 | cu/ + Browser-Use | 安全四件套 + 原子化任务 + MCP 工具 |
| M5 CU联动 | knowledge_bridge | 知识注入 + 结果反哺 _inbox + 状态机 |
| M6 可视化 | 前端组件 | WikiGraph + CUControlPanel + ReviewInbox + 急停 |

### 10.2 测试策略

| 层级 | 覆盖范围 | 工具 |
|---|---|---|
| 单元测试 | 每个解析器/检索器/执行器 | pytest |
| 安全测试 | 沙箱越界/直写拒绝/scope 穿透 | pytest + 异常断言 |
| 集成测试 | CU→知识库→图谱 端到端 | pytest + mock LLM |
| 前端 e2e | 图谱渲染/CU 面板/审核流程 | Playwright |
| 性能测试 | 检索延迟/索引速度/图谱构建 | pytest-benchmark |

---

## 11. 新增依赖清单

### 11.1 Python 后端

```
# 知识库
chromadb>=0.5.0
llama-index>=0.11.0
lightrag-hku>=1.0.0
kuzu>=0.4.0
marker-pdf>=0.2.0
python-docx>=1.1.0
trafilatura>=1.12.0
pyyaml>=6.0

# Computer Use
browser-use>=0.1.0
playwright>=1.45.0
```

### 11.2 前端

```
@antv/g6@^5.0.0
react-diff-viewer@^3.1.1
@uiw/react-md-editor@^4.0.0
```

---

## 12. 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| LightRAG LLM 抽取成本 | 增量更新减少调用；置信度阈值过滤低质量关系 |
| Browser-Use 元素定位失败 | wait_for_selector 显式等待 + 重试2次 + 降级纯 Playwright |
| ChromaDB 大规模性能 | HNSW 索引；1万文档内 < 800ms；超规模时分片 |
| CU 操作误伤真实环境 | 双层沙箱 + 人工确认门控 + 完整回滚链 |
| 全量替换破坏现有测试 | 分模块并行实现 + 每模块完成后回归 pytest |
