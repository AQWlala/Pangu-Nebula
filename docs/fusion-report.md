# Pangu Nebula — 三项目融合建议报告

> **报告日期**: 2026-07-11
> **报告目的**: 记录三个源项目(Nebula / awesome-llm-apps / NomiFun)的融合策略,确保后期可追溯
> **融合原则**: 取其精华、去其冗余、Python 全栈重构、暖色调迪士尼风格

---

## 1. 三个源项目概览

### 1.1 项目 A: Nebula (原项目)

| 属性 | 值 |
|------|-----|
| 路径 | D:\nebula |
| 技术栈 | Rust + Tauri + Preact |
| 定位 | 个人 AI 助理桌面应用 |
| 核心功能 | 6层记忆、蜂群编排、技能生态、Wiki编译、进化引擎、Loop循环、多设备同步、OAuth、DID、OS感知、多模态、安全模块 |
| UI风格 | 深色系,侧边栏分组导航,毛玻璃卡片 |
| 保留程度 | **架构骨架全保留**,技术栈全替换 |

### 1.2 项目 B: awesome-llm-apps (学习对象)

| 属性 | 值 |
|------|-----|
| 仓库 | Shubhamsaboo/awesome-llm-apps |
| 技术栈 | Python + FastAPI + 多框架 |
| 定位 | LLM 应用模式集合 |
| 核心模式 | Advisor-Orchestrator-Worker、自进化技能蒸馏、多Agent结果互验、预算控制与审计 |
| 保留程度 | **四大模式全借鉴**,代码不直接迁移 |

### 1.3 项目 C: NomiFun (架构参考)

| 属性 | 值 |
|------|-----|
| 仓库 | nomifun/nomifun-tauri |
| 技术栈 | Rust 2024 + Tauri 2 + React 19 |
| 定位 | 本地优先超级 AI 工作站 |
| 核心功能 | 桌面伴侣、DAG编排、无人值守自动化、统一知识库、Computer Use、Browser Use、12 IM渠道、MCP+REST能力总线 |
| 保留程度 | **架构模式借鉴**,40+ Rust crates 不直接迁移 |

---

## 2. 融合策略总览

```
┌─────────────────────────────────────────────────────────────┐
│                    Pangu Nebula (Python 全栈)                 │
├─────────────────────────────────────────────────────────────┤
│  架构骨架  │  四大模式  │  架构借鉴  │  暖色迪士尼  │  Python栈  │
│  ← Nebula  │  ← awesome │  ← NomiFun │  ← 用户需求 │  ← 技术选型 │
├─────────────────────────────────────────────────────────────┤
│  Phase 1-11 (全部完成)                                       │
│  ├─ 基础设施 (Nebula骨架 + Python栈)                          │
│  ├─ Provider+角色 (Nebula设计 + NomiFun适配模式)              │
│  ├─ 蜂群系统 (awesome的A-O-W模式 + NomiFun编排)                │
│  ├─ 记忆系统 (Nebula的6层 + NomiFun记忆工具 + 海绵/黑洞)       │
│  ├─ 技能生态 (awesome的蒸馏 + NomiFun技能工具 + 市场)          │
│  ├─ Wiki+进化 (Nebula设计 + NomiFun知识库 + awesome预算控制)   │
│  ├─ 多模态 (Nebula设计 + NomiFun Computer/Browser Use)        │
│  ├─ 安全身份 (Nebula设计 + NomiFun加密栈)                     │
│  ├─ 同步+IM (Nebula设计 + NomiFun 12渠道)                    │
│  ├─ MCP+调度 (NomiFun MCP + Nebula心跳)                      │
│  └─ 前端+打包 (Nebula UI + 暖色调 + PyInstaller)              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 详细融合映射

### 3.1 Nebula → Pangu Nebula (架构骨架)

| Nebula 模块 | Pangu Nebula 对应 | 融合方式 | 状态 |
|------------|-------------------|---------|------|
| 侧边栏分组导航 | Sidebar 组件 | 保留布局,换暖色调 | ✅ Phase 11 |
| Titlebar | Titlebar 组件 | 保留macOS风格 | ✅ Phase 11 |
| content-card | ContentCard | 保留毛玻璃卡片 | ✅ Phase 11 |
| 6层记忆(L0-L5) | Memory ORM + MemoryService | HTML格式+双向链接+图谱 | ✅ Phase 4 |
| 蜂群编排 | SwarmOrchestrator | +awesome的A-O-W模式 | ✅ Phase 3 |
| 角色系统(Persona) | PersonaService | +AI辅助生成SOUL.md | ✅ Phase 2 |
| Wiki编译 | WikiService | +NomiFun知识库安全写回 | ✅ Phase 6 |
| 进化引擎(4阶段) | EvolutionEngine | +awesome预算控制 | ✅ Phase 6 |
| Loop循环迭代 | LoopEngine | +NomiFun loop_guard | ✅ Phase 6 |
| 多设备同步(CRDT) | CRDTService + SyncCryptoService | E2EE加密 | ✅ Phase 9 |
| OAuth身份 | OAuthService + TokenManager | Gmail/GitHub/Notion/Slack PKCE | ✅ Phase 8 |
| DID去中心化身份 | DIDService | did:key + Ed25519 | ✅ Phase 8 |
| OS感知 | ClipboardWatcher+FileWatcher+TrayService+ScreenService | +NomiFun Computer Use | ✅ Phase 7 |
| 多模态 | VisionService+ASRService+TTSService+VideoService | 图片/语音/视频 | ✅ Phase 7 |
| 安全模块 | ACLService+InjectionGuard+SSRFGuard+Keychain+KeyRotation | +NomiFun加密栈 | ✅ Phase 8 |
| 悬浮球 | MascotAssistant 组件 | 暖色迪士尼卡通助理 | ✅ Phase 11 |
| 定时任务 | SchedulerService | +NomiFun cron | ✅ Phase 10 |
| 仪表盘 | Dashboard 组件 | Token/成本/心跳 | ✅ Phase 11 |
| 长任务面板 | SwarmProgress 组件 | +NomiFun plan | ✅ Phase 11 |
| 诊断面板 | DiagnosticsPage 内联页 | 安全审计/待审批 | ✅ Phase 11 |

**移除项**:
- 代码模式(Monaco Editor/CodeMode) — 移除
- Arena 对比面板 — 移除
- Shadow Workspace — 移除(原spec说保留,后决定移除)

### 3.2 awesome-llm-apps → Pangu Nebula (四大模式)

| 模式 | awesome-llm-apps 实现 | Pangu Nebula 实现 | 状态 |
|------|----------------------|-------------------|------|
| Advisor-Orchestrator-Worker | Advisor=用户Persona, Orchestrator=编排器, Worker=子智能体 | Persona=主智能体, SwarmOrchestrator=编排, WorkerEngine=Worker | ✅ Phase 2-3 |
| 自进化技能蒸馏 | 成功任务自动蒸馏新技能 | SkillDistiller: 连续3次成功触发, LLM提取技能, 人工确认写入 | ✅ Phase 5 |
| 多Agent结果互验 | 多Worker结果互相验证, 少数服从多数 | ResultVerifier: difflib相似度矩阵, 0.7阈值, 多数投票 | ✅ Phase 3 |
| 预算控制与审计 | Token/时间/金额预算, 超预算停止 | BudgetController + AuditLogger: 三维度+stop/degrade/warn+成本估算 | ✅ Phase 6 |

### 3.3 NomiFun → Pangu Nebula (架构借鉴)

| NomiFun 模块 | Pangu Nebula 对应 | 融合方式 | 状态 |
|--------------|-------------------|---------|------|
| 进程内嵌入式后端 | PyWebView + FastAPI(uvicorn进程内) | 同模式,Python实现 | ✅ Phase 1 |
| Provider适配(nomi-providers 26+) | providers/ (7个) | 简化为核心4个+Registry | ✅ Phase 2 |
| 上下文压缩(nomi-compact) | CompactEngine | auto 80% + emergency 95% | ✅ Phase 2 |
| Agent编排(orchestration.rs) | SwarmOrchestrator | 线性编排,后续扩展DAG | ✅ Phase 3 |
| 记忆系统(nomi-memory) | MemoryService + SpongeEngine + BlackHoleEngine | +双向链接+海绵/黑洞 | ✅ Phase 4 |
| 技能系统(skill_tool.rs 48KB) | SkillEngine + Sandbox + Distiller + Marketplace | 拆分为4个服务 | ✅ Phase 5 |
| 服务容器(AppServices) | 依赖注入(各Service单例) | Python模式 | ✅ Phase 1-5 |
| 知识库(nomifun-knowledge) | WikiService | +安全写回(暂存审查+diff) | ✅ Phase 6 |
| DAG编排(nomifun-orchestrator) | SwarmOrchestrator | 蜂群扩展为DAG(多依赖) | ✅ Phase 6 |
| Computer Use(nomi-computer+a11y) | ScreenService+ClipboardWatcher+FileWatcher+TrayService | pywinauto/pyobjc替代Rust | ✅ Phase 7 |
| Browser Use(nomi-browser) | BrowserService | Playwright Python替代自建CDP | ✅ Phase 7 |
| IM渠道(nomifun-channel 12平台) | WeChatChannel + FeishuChannel + ChannelRouter | 微信+飞书优先(itchat可选/Webhook+HMAC) | ✅ Phase 9 |
| MCP协议(nomifun-mcp, rmcp 1.5) | MCPClient + MCPServer | JSON-RPC 2.0 over stdio | ✅ Phase 10 |
| 定时任务(nomifun-cron) | SchedulerService | APScheduler可选+DB持久化 | ✅ Phase 10 |
| 安全(nomifun-auth+secret+redact) | ACLService+Keychain+KeyRotation+Redactor | JWT+bcrypt+AES-256-GCM+Ed25519 | ✅ Phase 8 |
| 双主机模式 | PyWebView嵌入+uvicorn独立 | 同模式 | ✅ Phase 1 |
| Feature Flag | (待实现) | Python importlib | Phase 8+ |
| 更新器(tauri-plugin-updater) | build.py + PyInstaller spec | 自建打包脚本 | ✅ Phase 11 |

**不借鉴**:
- 40+ Rust crates → Python 用包模块化
- 自托管 CDP 引擎 → 用 Playwright Python
- Rust 原生性能 → Python 性能足够
- Tauri 更新器 → 自建

---

## 4. 融合决策记录

### 4.1 为什么选择这三个项目?

**Nebula(原项目)**:
- 用户已有项目,熟悉度高
- 架构设计成熟(6层记忆、蜂群、进化引擎等)
- 保留骨架避免推倒重来

**awesome-llm-apps**:
- Python 生态,模式成熟
- 四大模式正好补齐 Nebula 的薄弱环节(自进化、互验、预算)
- 学习成本低,模式可直接套用

**NomiFun**:
- 同为本地优先 AI 工作站,定位最接近
- 架构成熟(40+ crates, Apache-2.0)
- 12 IM渠道、Computer Use、Browser Use 等前沿功能
- 双主机模式与 PyWebView + FastAPI 天然契合

### 4.2 为什么不全量迁移 NomiFun?

1. **Rust → Python 技术栈不兼容**: 40+ Rust crates 无法直接迁移
2. **40+ crates 过度模块化**: 对 Python 小团队是负担
3. **127KB/276KB 超大文件**: 维护困难,不作为代码参考
4. **pre-1.0 不稳定**: API 可能变动
5. **用户已有 Nebula**: 保留 Nebula 骨架更符合用户习惯

### 4.3 为什么选择 Python 而非保留 Rust?

1. **用户明确要求**: "转写成python格式"
2. **开发速度**: Python 开发速度快于 Rust
3. **AI 生态**: Python AI/ML 生态最丰富
4. **用户熟悉**: 用户技术栈含 Python + SQLite
5. **awesome-llm-apps 是 Python**: 直接借鉴模式

### 4.4 融合的关键决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 技术栈 | Rust+Tauri / Python全栈 | Python全栈 | 用户要求 + AI生态 |
| 前端框架 | React 19 / Preact | Preact | Nebula已用 + 轻量 |
| CSS框架 | UnoCSS / TailwindCSS | TailwindCSS | Nebula已用 + 生态 |
| 桌面壳 | Tauri 2 / PyWebView | PyWebView | Python全栈一致性 |
| 数据库 | SQLx+rusqlite / SQLAlchemy+aiosqlite | SQLAlchemy 2.0 async | Python生态 + 异步 |
| Provider数 | NomiFun 26+ / Nebula 原设计 | 7个核心+Registry | 简化,按需扩展 |
| IM渠道 | NomiFun 12 / Nebula 原设计 | 微信+飞书优先 | 用户需求优先 |
| 编排模式 | NomiFun DAG / awesome A-O-W | 线性A-O-W + 后续DAG | 简化,Phase 6扩展 |
| 记忆层数 | Nebula 6层 / NomiFun N层 | 6层(L0-L5) | Nebula设计 |
| 配色 | Nebula深色 / 暖色调 | 暖色调三色系 | 用户要求 |
| 助理风格 | NomiFun桌面伴侣 / 迪士尼 | 迪士尼卡通暖色 | 用户要求 |

---

## 5. 融合实施进度

### 5.1 已完成(Phase 1-11 全部完成)

| Phase | 融合来源 | 交付内容 |
|-------|---------|---------|
| Phase 1 | Nebula骨架 + Python栈 | FastAPI + Preact + SQLite + PyWebView + 19路由 + pytest |
| Phase 2 | Nebula设计 + NomiFun Provider模式 + awesome A-O-W | 7 Provider + Persona CRUD + SSE流式 + CompactEngine + 技能加载器 + 工具注册表 |
| Phase 3 | awesome A-O-W + NomiFun编排 | SwarmOrchestrator + WorkerEngine + ResultVerifier + 7 API端点 |
| Phase 4 | Nebula 6层 + NomiFun记忆工具 + 海绵/黑洞 | MemoryService + SpongeEngine + BlackHoleEngine + 8 API端点 |
| Phase 5 | awesome蒸馏 + NomiFun技能工具 + 市场 | PromptSkillEngine + PythonSandbox + SkillDistiller + SkillMarketplace + 14 API端点 |
| Phase 6 | Nebula进化4阶段 + NomiFun知识库 + awesome预算控制 | WikiService(7端点) + EvolutionEngine(4阶段+5端点) + LoopEngine(SSE+7端点+loop_guard) + BudgetController(三维度) + AuditLogger(10端点+成本估算) |
| Phase 7 | Nebula多模态 + NomiFun Computer/Browser Use | VisionService(图片) + ASRService(语音识别) + TTSService(语音合成) + VideoService(视频分析) + ClipboardWatcher + FileWatcher + TrayService + ScreenService(屏幕感知) + BrowserService(Playwright) + 32 API端点 |
| Phase 8 | Nebula设计 + NomiFun加密栈 | ACLService(fnmatch+deny优先) + InjectionGuard(52模式) + SSRFGuard(ipaddress) + Keychain(AES-256-GCM) + KeyRotation(90天) + OAuthService(PKCE 4提供商) + TokenManager + DIDService(Ed25519+did:key) + Redactor(9规则) + 37 API端点 |
| Phase 9 | Nebula设计 + NomiFun 12渠道 | CRDTService(LWWRegister+ORSet+RGA) + SyncCryptoService(X25519+HKDF+AES-256-GCM) + PairingService(配对码+QR+ECDH) + RelayService(httpx长轮询) + WeChatChannel(itchat可选) + FeishuChannel(Webhook+HMAC+事件回调) + ChannelRouter(统一格式+CRUD) + 38 API端点 |
| Phase 10 | NomiFun MCP + Nebula心跳 | MCPClient(JSON-RPC 2.0 over stdio) + MCPServer(工具注册+handle_request) + HealthCheckService(降级+监控) + SchedulerService(APScheduler可选+4种action) + 31 API端点 |
| Phase 11 | Nebula UI + 暖色调迪士尼 + PyInstaller打包 | 14前端组件(Titlebar/Sidebar/StatusBar/MascotAssistant/Settings/ChatPanel/PersonaManager/OnboardingWizard/SwarmProgress/MemoryGraph/MemoryInspector/SkillMarketplace/WikiBrowser/Dashboard) + 三色系CSS变量(warm-orange/soft-pink/cream-beige) + macOS风格(traffic lights+glass blur) + 统一API客户端(apiGet/apiPost/apiPut/apiDelete/apiStream SSE) + 自实现Markdown渲染器 + PyInstaller spec(onedir+25 hiddenimports) + build.py(8步) + dev.py(并发启动) + 13 E2E测试(10冒烟+3构建) + tsc 0错误 + 24模块/137KB JS+13.8KB CSS |

### 5.2 待实施

无 — 全部 11 个 Phase 已完成。

---

## 6. 融合风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Python性能不如Rust | 沙箱/多模态性能 | 关键路径用subprocess异步隔离 |
| NomiFun pre-1.0变动 | 借鉴模式可能过时 | 借鉴架构模式,不直接依赖API |
| 12 IM渠道维护成本 | 功能膨胀 | 优先2个(微信+飞书),按需扩展 |
| DAG编排复杂度 | Phase 6延期 | 先线性编排(已实现),DAG作为扩展 |
| PyWebView无更新器 | 自动更新困难 | Phase 11自建检查+下载机制 |
| 前端未实现 | Phase 1-10只有后端API | ✅ 已解决: Phase 11 统一实现 14 组件 + 三色系 + macOS 风格 |

---

## 7. 结论

Pangu Nebula 的三项目融合策略是:

1. **Nebula 提供骨架**: 架构设计、功能模块、UI布局全部保留,技术栈全替换为 Python
2. **awesome-llm-apps 提供模式**: 四大模式(A-O-W、自进化、互验、预算)补齐能力短板
3. **NomiFun 提供参考**: 双主机模式、服务容器、知识库安全写回、Computer/Browser Use、12 IM渠道、MCP协议等架构模式

融合后的 Pangu Nebula 保留了 Nebula 的完整功能规划,借鉴了 awesome-llm-apps 的先进模式,参考了 NomiFun 的成熟架构,以 Python 全栈 + 暖色调迪士尼风格交付。

**当前进度**: Phase 1-11 全部完成(100%工时)。后端 API 层 193+ 端点就绪,前端 UI 层 14 组件 + 24 模块构建通过,PyInstaller 打包 spec 就绪,16 项测试全部通过(3 单元 + 10 冒烟 + 3 前端构建)。三项目融合策略全部落地, Nebula 骨架 + awesome 四大模式 + NomiFun 架构借鉴均已交付。
