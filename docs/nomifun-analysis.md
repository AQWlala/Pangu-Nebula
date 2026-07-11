# NomiFun (nomifun-tauri) — 7专家协议分析报告

> **分析日期**: 2026-07-11
> **分析目的**: 为 Pangu Nebula 项目提供架构借鉴和融合参考
> **分析对象**: GitHub 仓库 `nomifun/nomifun-tauri` (Apache-2.0, v0.2.10)
> **分析方法**: 7专家协议(架构师/安全专家/性能专家/AI专家/前端专家/DevOps专家/产品经理)

---

## 1. 项目概览

### 1.1 基本信息

| 属性 | 值 |
|------|-----|
| 仓库名 | nomifun/nomifun-tauri |
| 许可证 | Apache-2.0 |
| 版本 | workspace 0.2.10 / 前端 0.2.16 |
| 状态 | pre-1.0 |
| 平台 | macOS / Windows / Linux |
| 技术栈 | Rust 2024 edition + Tauri 2 + React 19 |
| 前端框架 | Vite 6.4 + UnoCSS + Arco Design |
| 后端框架 | Axum 0.8 + tokio + SQLx(rusqlite) |

### 1.2 核心定位

NomiFun 是一个**完全开源、本地优先的超级 AI 工作站**。一个 React 前端 + 一个 Rust 后端,提供:

- 不断进化的桌面伴侣(自定义形象、共享记忆、技能生成、IM 渠道连接)
- 对话原生编排(从普通对话扩展为 DAG 多Agent编排,节点级预检控制)
- 无人值守自动化(需求平台 + AutoWork + IDMM智能决策系统)
- 统一知识库(集中管理、安全写回、URL快照、范围检索)
- 原生 Computer Use 和 Browser Use(进程内 Rust 实现,无 Playwright/Node 依赖)
- 开放能力总线(MCP + REST,~20域 150+工具)

### 1.3 数据安全承诺

所有数据本地存储,唯一出站网络调用是用户配置的 LLM 请求。无遥测、无第三方服务集成。

---

## 2. 架构分析

### 2.1 整体架构

```
┌── nomifun-desktop (Tauri 进程) ──────────────────────────────┐
│  Tauri 壳 (窗口/托盘/对话框/深度链接/更新器)                       │
│  └─ tokio 任务: nomifun_app 嵌入式 axum 在 127.0.0.1:<port>     │
│  WebView2/WKWebView/WebKitGTK ── HTTP ──▶ 127.0.0.1:<p>/api   │
└────────────────────────────────────────────────────────────────┘
```

**核心设计**: 统一 Rust 后端 `nomifun-app` 被链接进 Tauri 进程内,无 spawned 二进制文件。双主机模式:
- **嵌入式**(Tauri 桌面壳): 本地无认证模式
- **独立服务器**(`nomifun-web`): 认证模式,也提供 SPA 静态文件

### 2.2 Workspace 结构(40+ Rust crates)

```
nomifun-tauri/
├── apps/
│   ├── desktop/          — Tauri 桌面壳(main.rs 45KB, relocate.rs 48KB, memory_panel_window.rs)
│   └── web/              — 独立 Web 主机(main.rs 9.8KB)
├── crates/
│   ├── agent/            — Agent 能力(14+ crates)
│   │   ├── nomi-agent/       — 核心 Agent 引擎(engine.rs 127KB!, orchestration.rs 49KB, context.rs 48KB)
│   │   ├── nomi-compact/     — 上下文压缩(fold/json/level)
│   │   ├── nomi-providers/   — 多模型提供商(26+ 提供商)
│   │   ├── nomi-memory/      — 记忆系统
│   │   ├── nomi-skills/      — 技能系统(skill_tool.rs 48KB)
│   │   ├── nomi-tools/       — 工具注册表
│   │   ├── nomi-mcp/         — MCP 协议
│   │   ├── nomi-computer/    — Computer Use(进程内 Rust)
│   │   ├── nomi-a11y/        — 无障碍树(跨平台: macOS AXUIElement+Vision / Windows UI Automation / Linux AT-SPI2)
│   │   ├── nomi-browser/     — Browser Use(tool.rs 276KB!)
│   │   ├── nomi-browser-engine/ — 自托管 CDP 浏览器引擎(无 Playwright)
│   │   ├── nomi-cli/         — CLI 工具
│   │   ├── nomi-types/       — 类型定义
│   │   ├── nomi-protocol/    — 协议定义
│   │   └── nomi-config/      — 配置管理
│   ├── backend/          — 后端域服务(30+ crates)
│   │   ├── nomifun-app/          — 统一应用层(核心组装,lib.rs + router + services + bootstrap)
│   │   ├── nomifun-db/           — 数据库(SQLite via sqlx + rusqlite)
│   │   ├── nomifun-ai-agent/     — AI Agent 集成
│   │   ├── nomifun-conversation/ — 会话管理
│   │   ├── nomifun-knowledge/    — 知识库(安全写回/URL快照/范围检索)
│   │   ├── nomifun-orchestrator/ — 编排器(DAG 多Agent)
│   │   ├── nomifun-channel/      — IM 渠道(12平台: Telegram/Lark/DingTalk/WeChat/WeCom/Discord/Matrix/Mattermost/Slack/Twitch/Nostr/QQBot)
│   │   ├── nomifun-cron/         — 定时任务
│   │   ├── nomifun-mcp/          — MCP 协议(rmcp 1.5)
│   │   ├── nomifun-companion/    — 桌面伴侣
│   │   ├── nomifun-terminal/     — 终端 PTY(portable-pty)
│   │   ├── nomifun-office/       — Office 文档(calamine/rust_xlsxwriter)
│   │   ├── nomifun-auth/         — 认证(jsonwebtoken/bcrypt/aes-gcm/ed25519)
│   │   ├── nomifun-secret/       — 密钥管理
│   │   ├── nomifun-requirement/  — 需求平台
│   │   ├── nomifun-idmm/         — 智能决策系统
│   │   ├── nomifun-extension/    — 扩展系统
│   │   ├── nomifun-gateway/      — 能力网关
│   │   ├── nomifun-webhook/      — Webhook 通知
│   │   ├── nomifun-realtime/     — 实时通信(WebSocket)
│   │   └── ... (共 30+ 域 crate)
│   └── shared/           — 共享库
│       ├── nomifun-net/     — 网络工具
│       └── nomi-redact/     — 敏感信息脱敏
└── ui/                   — React 19 前端(Vite + UnoCSS + Arco Design)
```

### 2.3 关键依赖栈

| 类别 | 依赖 | 版本 | 用途 |
|------|------|------|------|
| Web框架 | axum | 0.8 | HTTP服务器(multipart, ws) |
| 异步运行时 | tokio | 1 (full) | 异步运行时 |
| 数据库 | sqlx + rusqlite | 0.8 / 0.32 | SQLite(rusqlite bundled) |
| 序列化 | serde / serde_json / serde_yaml | 1 / 1 / 0.9 | |
| 认证加密 | jsonwebtoken / bcrypt / aes-gcm / ed25519-dalek | 10 / 0.17 / 0.10 / 2 | JWT + bcrypt + AES-256-GCM + Ed25519 |
| HTTP客户端 | reqwest | 0.12 | rustls-tls, socks, system-proxy |
| WebSocket | tokio-tungstenite | 0.26 | rustls-tls-native-roots |
| 文件监控 | notify | 8 | 文件系统监听 |
| Git | git2 | 0.20 | libgit2 绑定 |
| PTY | portable-pty | 0.8 | 跨平台终端 |
| Office | calamine / rust_xlsxwriter | 0.26 / 0.82 | Excel 读写 |
| 截屏 | xcap | 0.9 | 跨平台截屏 |
| 输入模拟 | enigo | 0.6 | 键鼠控制 |
| 浏览器自动化 | chromiumoxide | 0.9 | CDP 协议 |
| MCP | rmcp | 1.5 | MCP server |
| AWS | aws-sdk-bedrock | 1 | Bedrock 模型 |
| OAuth | oauth2 | 5.0.0-rc.1 | OAuth 认证 |
| Nostr | nostr | 0.37 | Nostr 协议(nip04) |

### 2.4 前端技术栈

| 类别 | 依赖 | 版本 |
|------|------|------|
| UI框架 | React | 19.1 |
| 构建工具 | Vite | 6.4 |
| CSS框架 | UnoCSS | 66.3 |
| 组件库 | Arco Design Web React | 2.66 |
| 路由 | react-router-dom | 7.8 |
| 状态管理 | SWR | 2.3 |
| 代码编辑器 | Monaco Editor + CodeMirror 6 | |
| 终端 | xterm.js | 5.5 (addon-fit/web-links/webgl) |
| 流程图/DAG | @xyflow/react | 12.11 |
| Markdown | react-markdown 10.1 + remark/rehype | |
| 数学公式 | katex | 0.16 |
| 图表 | mermaid | 11.13 |
| 差异展示 | diff2html | 3.4 |
| ONNX推理 | onnxruntime-web | 1.26 |
| 国际化 | i18next + react-i18next | 23.7 / 14.0 |
| AI SDK | @anthropic-ai/sdk, @google/genai, openai, @aws-sdk/client-bedrock | |
| MCP | @modelcontextprotocol/sdk | 1.20 |
| ACP | @agentclientprotocol/sdk | 0.18 |
| IM SDK | grammy, @larksuiteoapi/node-sdk, dingtalk-stream, @wecom/aibot-node-sdk | |
| 文档处理 | docx, mammoth, officeparser, pptx2json, xlsx-republish | |

---

## 3. 七专家分析

### 3.1 架构师视角

**优势**:
- **进程内嵌入式后端**: 无 spawned 二进制,统一 Rust 后端链接进 Tauri 进程,降低 IPC 开销
- **Workspace 模块化**: 40+ crates 按域清晰划分(backend 30+ / agent 14+ / shared 2),可维护性高
- **双主机模式**: 同一后端代码支持桌面嵌入式(无认证)和独立服务器(认证模式),复用性强
- **DI 容器模式**: `AppServices` 从配置和数据库构建所有域服务,依赖注入清晰
- **Feature Flag 控制**: IM 渠道(12平台)和 Computer/Browser Use 通过 feature flag 编译控制

**风险**:
- **过度模块化**: 40+ crates 带来编译时间和管理成本上升,对小团队是负担
- **engine.rs 127KB**: 核心 Agent 引擎单文件过大,违反单一职责原则
- **tool.rs 276KB**: 浏览器工具单文件过大,维护困难

**对 Pangu Nebula 的启示**:
- 采用 Python 包模块化(而非 40+ crates),保持域划分但降低管理成本
- 服务层 `AppServices` 模式值得借鉴 → Python 中用依赖注入容器
- 双主机模式 → PyWebView 嵌入式 + uvicorn 独立服务器

### 3.2 安全专家视角

**优势**:
- **本地优先**: 所有数据本地存储,无遥测,唯一出站是用户配置的 LLM 请求
- **多加密层**: JWT(jsonwebtoken) + bcrypt + AES-256-GCM + Ed25519
- **敏感信息脱敏**: `nomi-redact` crate 专门处理
- **密钥管理**: `nomifun-secret` crate 独立管理
- **WebUI 信任头**: 注入本地信任密钥到 webview,patch fetch/XHR
- **CORS 白名单**: 区分开发期和生产期

**风险**:
- **insecure-no-auth 标志**: `--insecure-no-auth` 禁用认证,危险但方便开发
- **LAN 远程访问**: WebUI LAN-IP 检测带来远程攻击面

**对 Pangu Nebula 的启示**:
- 本地优先原则完全采纳
- 加密栈: SQLite + AES-256-GCM + Ed25519(与 Pangu Nebula 的 E2EE 方案一致)
- 敏感信息脱敏模块值得借鉴

### 3.3 性能专家视角

**优势**:
- **Rust 原生性能**: 进程内 Rust 后端,零 IPC 开销
- **tokio 异步**: 全链路异步,高并发
- **rusqlite bundled**: 静态链接 SQLite,无系统依赖
- **LTO + strip**: release profile 启用 thin LTO + strip,二进制优化
- **psutil 内存监控**: 沙箱执行带内存监控

**风险**:
- **40+ crates 编译时间**: 开发迭代速度受影响
- **127KB engine.rs**: 大文件编译缓存效率低

**对 Pangu Nebula 的启示**:
- Python 性能不如 Rust,但开发速度快,适合 Phase 1-10
- 关键性能路径(如沙箱执行)可用 subprocess 异步隔离
- LTO 对应 Python 的 cython/nuitka 编译(Phase 11 打包时考虑)

### 3.4 AI 专家视角

**优势**:
- **26+ 模型提供商**: `nomi-providers` 覆盖主流 LLM
- **ACP 外部 Agent**: ~19 个 ACP(Agent Client Protocol)外部 Agent
- **DAG 编排**: 从普通对话扩展为 DAG 多Agent编排,节点级预检
- **上下文压缩**: `nomi-compact` (fold/json/level) + nomi-agent 的 compact/(auto/emergency/micro/prompt/state)
- **Computer Use**: 进程内 Rust 实现(无 Playwright),跨平台无障碍树
- **Browser Use**: 自托管 CDP 引擎(无 Node 依赖)
- **自进化技能**: skill_tool.rs 48KB,技能生成与赠予

**风险**:
- **engine.rs 127KB**: Agent 引擎过大,逻辑耦合
- **tool.rs 276KB**: 浏览器工具过大

**对 Pangu Nebula 的启示**:
- Provider 适配层已实现(Phase 2,7个Provider)
- DAG 编排 → 蜂群编排已实现(Phase 3),可扩展为 DAG
- 上下文压缩已实现(Phase 2, CompactEngine auto/emergency)
- Computer Use / Browser Use → Phase 7 多模态时借鉴
- 自进化技能蒸馏已实现(Phase 5, SkillDistiller)

### 3.5 前端专家视角

**优势**:
- **React 19**: 最新版本,并发特性
- **Vite 6.4**: 快速 HMR
- **UnoCSS**: 原子化 CSS,比 TailwindCSS 更灵活
- **Arco Design**: 企业级组件库
- **@xyflow/react**: DAG 画布可视化(编排画布)
- **xterm.js**: 终端组件(带 webgl 加速)
- **Monaco + CodeMirror**: 双代码编辑器
- **i18next**: 完整国际化
- **mermaid + katex**: 图表和数学公式渲染

**对 Pangu Nebula 的启示**:
- Pangu Nebula 用 Preact(轻量) + TailwindCSS,足够用
- DAG 画布(@xyflow/react)→ 记忆图谱可视化时考虑(Phase 11)
- xterm.js → 代码工作台终端(Phase 11)
- i18next → 国际化(Phase 11)

### 3.6 DevOps 专家视角

**优势**:
- **跨平台构建脚本**: build:mac / build:win / build:linux
- **Tauri 更新器**: tauri-plugin-updater + latest.json
- **Docker 支持**: Dockerfile + Caddyfile
- **GitHub CI**: ISSUE_TEMPLATE + PR_TEMPLATE
- **版本管理**: bump 脚本 + CHANGELOG
- **测试**: cargo test + cargo nextest + insta 快照测试

**对 Pangu Nebula 的启示**:
- PyInstaller 打包(Phase 11)
- 自动更新 → PyWebView 无原生更新器,需自建
- Docker → 可选,Phase 11 考虑

### 3.7 产品经理视角

**优势**:
- **本地优先 + 开源**: 数据主权 + 可审计,企业友好
- **Apache-2.0**: 商业友好许可证
- **12 IM 渠道**: 覆盖主流平台
- **桌面伴侣**: 自定义形象 + 共享记忆 + 技能赠予,差异化
- **无人值守**: 需求平台 + AutoWork + IDMM,企业场景

**风险**:
- **pre-1.0**: 功能未稳定
- **40+ crates**: 功能庞大,用户认知成本高

**对 Pangu Nebula 的启示**:
- 数据主权宣传语: "别把第二大脑租给别人"
- 桌面伴侣 → 迪士尼卡通助理(暖色调)
- 12 IM 渠道 → Phase 9 实现(微信+飞书优先)

---

## 4. 核心模块深度分析

### 4.1 Agent 引擎 (nomi-agent)

**核心文件**: `engine.rs` (127KB), `orchestration.rs` (49KB), `context.rs` (48KB)

**功能模块**:
- `agents_md.rs` — Agent 定义
- `bootstrap.rs` (42KB) — 启动初始化
- `compact/` — 上下文压缩(auto/emergency/estimate/micro/prompt/state)
- `context.rs` (48KB) — 上下文管理
- `context_contributor.rs` — 上下文贡献者
- `confirm.rs` — 确认机制
- `goal/` — 目标管理(runtime/state/templates/tool)
- `knowledge_tools.rs` (30KB) — 知识库工具
- `memory_tools.rs` — 记忆工具
- `orchestration.rs` (49KB) — 多Agent编排
- `output/` — 输出处理(null_sink/protocol_sink/terminal)
- `plan/` — 计划管理(file/prompt/state/tools)
- `requirement_tools.rs` — 需求工具
- `session.rs` (16KB) — 会话管理
- `skill_tool.rs` (48KB) — 技能工具
- `spawn_tool.rs` / `spawner.rs` (24KB) — 子Agent生成
- `taskboard.rs` — 任务看板
- `vcr.rs` — 录制回放
- `loop_guard.rs` — 循环守卫

**对 Pangu Nebula 的映射**:
| NomiFun 模块 | Pangu Nebula 对应 | 状态 |
|--------------|-------------------|------|
| engine.rs | ChatService + Orchestrator | ✅ Phase 2 |
| orchestration.rs | SwarmOrchestrator | ✅ Phase 3 |
| compact/ | CompactEngine | ✅ Phase 2 |
| context.rs | (待实现,记忆注入上下文) | Phase 6 |
| goal/ | (待实现) | Phase 6 |
| plan/ | (待实现,长任务计划) | Phase 10 |
| skill_tool.rs | SkillDistiller + SkillEngine | ✅ Phase 5 |
| spawn_tool.rs | WorkerEngine | ✅ Phase 3 |
| session.rs | Conversation/Message ORM | ✅ Phase 1 |
| memory_tools.rs | MemoryService + SpongeEngine | ✅ Phase 4 |
| knowledge_tools.rs | (待实现,Wiki+知识库) | Phase 6 |
| loop_guard.rs | (待实现,Loop循环) | Phase 6 |

### 4.2 Computer Use (nomi-computer + nomi-a11y)

**跨平台无障碍树**:
- **macOS**: AXUIElement + Vision OCR
- **Windows**: UI Automation + OCR + tree_map
- **Linux**: AT-SPI2

**核心能力**:
- `engine.rs` — 引擎
- `overlay.rs` — 覆盖层
- `selector.rs` — 选择器
- `tree.rs` — 树结构

**对 Pangu Nebula 的启示**: Phase 7 OS感知时,Python 可用 `pywinauto`(Windows)/ `pyobjc`(macOS) 实现类似功能,或调用系统命令。

### 4.3 Browser Use (nomi-browser + nomi-browser-engine)

**自托管 CDP 引擎**: 无 Playwright/Node 依赖
- `tool.rs` (276KB) — 浏览器工具
- `launch.rs` / `session.rs` — 启动/会话
- `input.rs` / `nav.rs` — 输入/导航
- `approval.rs` — 审批
- `extract.rs` — 提取
- `recording.rs` — 录制
- `site_memory.rs` — 站点记忆
- `takeover.rs` — 接管
- `visual_fallback.rs` — 视觉兜底
- `replay.rs` — 回放

**对 Pangu Nebula 的启示**: Phase 7 可用 Playwright Python 或 selenium 实现浏览器自动化。

### 4.4 IM 渠道 (nomifun-channel)

**12 个平台**(feature flag 控制):
| 平台 | Feature Flag | SDK |
|------|-------------|-----|
| Telegram | telegram | grammy |
| 飞书/Lark | lark | @larksuiteoapi/node-sdk |
| 钉钉/DingTalk | dingtalk | dingtalk-stream |
| 微信/WeChat | weixin | (自建) |
| 企业微信/WeCom | wecom | @wecom/aibot-node-sdk |
| Discord | discord | (自建) |
| Matrix | matrix | (自建) |
| Mattermost | mattermost | (自建) |
| Slack | slack | (自建) |
| Twitch | twitch | (自建) |
| Nostr | nostr | nostr 0.37 |
| QQ Bot | qqbot | (自建) |

**对 Pangu Nebula 的启示**: Phase 9 实现微信+飞书优先,Python 用 `wechaty` / `lark-oapi` SDK。

### 4.5 知识库 (nomifun-knowledge)

**功能**:
- 集中管理
- 安全写回(暂存审查,`similar` unified-diff)
- URL 快照
- 范围检索
- `htmd` 0.5 — HTML → Markdown 转换

**对 Pangu Nebula 的启示**: Phase 6 Wiki 编译借鉴,HTML → Markdown 转换用 Python `html2text` 或 `markdownify`。

### 4.6 编排器 (nomifun-orchestrator)

**DAG 多Agent编排**:
- 从普通对话扩展为 DAG
- 节点级预检控制
- @xyflow/react 画布可视化

**对 Pangu Nebula 的启示**: Phase 3 蜂群已实现线性编排,Phase 6 可扩展为 DAG(多依赖关系)。

---

## 5. 重构优先级矩阵

基于七专家分析,对 Pangu Nebula 的借鉴优先级:

| 优先级 | 模块 | NomiFun 来源 | Pangu Nebula 目标 | 实施阶段 |
|--------|------|-------------|-------------------|---------|
| P0 | Provider 适配 | nomi-providers (26+) | providers/ (7个,已实现) | ✅ Phase 2 |
| P0 | 上下文压缩 | nomi-compact | CompactEngine (已实现) | ✅ Phase 2 |
| P0 | Agent 编排 | orchestration.rs | SwarmOrchestrator (已实现) | ✅ Phase 3 |
| P0 | 记忆系统 | nomi-memory + memory_tools | MemoryService + Sponge/BlackHole | ✅ Phase 4 |
| P0 | 技能系统 | skill_tool.rs | SkillEngine + Distiller | ✅ Phase 5 |
| P1 | 知识库 | nomifun-knowledge | Wiki 编译 | Phase 6 |
| P1 | DAG 编排 | nomifun-orchestrator | 蜂群扩展为 DAG | Phase 6 |
| P1 | 进化引擎 | nomi-agent goal/plan | Evolution Engine | Phase 6 |
| P1 | Loop 循环 | loop_guard.rs | Loop 迭代 + 预算控制 | Phase 6 |
| P2 | Computer Use | nomi-computer + nomi-a11y | OS 感知(剪贴板/文件夹/托盘/屏幕) | Phase 7 |
| P2 | Browser Use | nomi-browser | 浏览器自动化 | Phase 7 |
| P2 | 多模态 | nomi-a11y OCR | 图片/语音/视频 | Phase 7 |
| P3 | 安全模块 | nomifun-auth + nomifun-secret + nomi-redact | ACL + 注入/SSRF防护 + E2EE | Phase 8 |
| P3 | IM 渠道 | nomifun-channel (12平台) | 微信+飞书 | Phase 9 |
| P4 | MCP 协议 | nomifun-mcp + rmcp 1.5 | MCP 客户端/服务端 | Phase 10 |
| P4 | 定时任务 | nomifun-cron | Scheduler | Phase 10 |

---

## 6. 代码结构映射表

| NomiFun (Rust) | Pangu Nebula (Python) | 迁移策略 |
|----------------|----------------------|---------|
| nomi-providers | server/providers/ | 直接重写为 Python httpx async |
| nomi-compact | server/services/compact.py | 直接重写为 Python |
| nomi-agent/engine.rs | server/services/chat_service.py | 拆分为 ChatService + Orchestrator |
| nomi-agent/orchestration.rs | server/services/swarm_orchestrator.py | 简化为线性编排,后续扩展 DAG |
| nomi-agent/compact/ | server/services/compact.py | auto/emergency 两级,省略 micro |
| nomi-agent/skill_tool.rs | server/services/skill_engine.py + distiller.py | 拆分为模板引擎 + 蒸馏引擎 |
| nomi-agent/memory_tools.rs | server/services/memory_service.py | 直接重写 |
| nomi-agent/spawn_tool.rs | server/services/worker_engine.py | 简化为 WorkerEngine |
| nomi-agent/session.rs | server/db/orm.py (Conversation/Message) | ORM 模型 |
| nomifun-db | server/db/engine.py + orm.py | SQLAlchemy 2.0 async |
| nomifun-knowledge | (待实现) | Phase 6 Wiki |
| nomifun-orchestrator | (待扩展) | Phase 6 DAG |
| nomifun-channel | (待实现) | Phase 9 IM |
| nomifun-mcp | (待实现) | Phase 10 MCP |
| nomifun-cron | (待实现) | Phase 10 Scheduler |
| nomifun-auth | (待实现) | Phase 8 安全 |
| nomifun-secret | (待实现) | Phase 8 密钥 |
| nomi-redact | (待实现) | Phase 8 脱敏 |
| nomi-computer | (待实现) | Phase 7 OS感知 |
| nomi-browser | (待实现) | Phase 7 浏览器 |
| nomi-a11y | (待实现) | Phase 7 屏幕感知 |

---

## 7. 结论与建议

### 7.1 核心借鉴(已实现)

NomiFun 的以下核心架构模式已被 Pangu Nebula 借鉴并实现:

1. **进程内嵌入式后端** → PyWebView + FastAPI(进程内 uvicorn)
2. **Provider 适配层** → 7个 Provider + Registry 装饰器模式
3. **上下文压缩** → CompactEngine(auto 80% + emergency 95%)
4. **Agent 编排** → SwarmOrchestrator(拆解+并行+互验+汇总)
5. **记忆系统** → 6层 + 双向链接 + 海绵引擎 + 黑洞引擎
6. **技能系统** → 模板引擎 + 沙箱 + 蒸馏 + 市场
7. **服务容器** → AppServices 模式 → Python 依赖注入

### 7.2 待借鉴(后续 Phase)

1. **DAG 编排** → Phase 6 扩展蜂群为 DAG(多依赖关系)
2. **知识库安全写回** → Phase 6 Wiki 编译(暂存审查 + diff)
3. **Computer Use** → Phase 7 OS感知(pywinauto/pyobjc)
4. **Browser Use** → Phase 7 浏览器自动化(Playwright Python)
5. **12 IM 渠道** → Phase 9(微信+飞书优先)
6. **MCP 协议** → Phase 10(rmcp → Python mcp SDK)
7. **敏感信息脱敏** → Phase 8(nomi-redact → Python regex)

### 7.3 不借鉴(不适合 Python)

1. **40+ Rust crates** → Python 用包模块化,降低管理成本
2. **进程内 Rust 性能** → Python 性能足够,关键路径用 subprocess
3. **自托管 CDP 引擎** → 用 Playwright Python,不自建
4. **Tauri 更新器** → PyWebView 无原生更新器,自建检查机制

### 7.4 风险提示

1. **NomiFun pre-1.0**: 功能未稳定,借鉴时需验证 API 可用性
2. **127KB/276KB 大文件**: NomiFun 存在超大文件问题,Pangu Nebula 应保持模块拆分
3. **12 IM 渠道维护成本**: 优先实现 2 个(微信+飞书),其余按需

---

## 附录: NomiFun 技术规格快速参考

- **仓库**: https://github.com/nomifun/nomifun-tauri
- **许可证**: Apache-2.0
- **版本**: workspace 0.2.10 / 前端 0.2.16
- **Rust edition**: 2024
- **Tauri**: 2.x
- **React**: 19.1
- **Vite**: 6.4
- **后端端口**: 默认 8787 (Web) / 随机 (桌面嵌入)
- **数据目录**: `NOMIFUN_DATA_DIR` 环境变量覆盖
- **IM 渠道**: Telegram / Lark / DingTalk / WeChat / WeCom / Discord / Matrix / Mattermost / Slack / Twitch / Nostr / QQBot
- **MCP**: rmcp 1.5 (server, transport-io, schemars)
- **ACP**: ~19 个外部 Agent
- **工具数**: ~20 域 150+ 工具
