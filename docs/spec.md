# Pangu Nebula（PanGu Nebula / 盘古星云）— 项目规格书 v3.0

## 1. 项目定位

Pangu Nebula（盘古星云）是从原 Nebula（D:\nebula，Rust+Tauri）深度迭代的全量迁移项目。

核心机制：用户创建 3 个自定义 Persona 主智能体 → 与角色对话确认需求 → 后台并行派发 2~5 个通用子智能体蜂群 → 多 Agent 结果互验 → 汇总输出。
集成 awesome-llm-apps 四大模式：Advisor-Orchestrator-Worker、自进化技能蒸馏、多 Agent 结果互验、预算控制与审计。

原项目 Nebula 保留不动作为参考和备份。
全量迁移为 Python 全栈，保存在 D:\Pangu Nebula。不做最小版本，所有模块一次性完整迁移。

## 2. 核心需求

### 2.1 智能体架构（Advisor-Orchestrator-Worker 模式）
- 3 个可自定义 Persona 主智能体（AI 辅助生成：用户填基本信息 → AI 生成 system_prompt + SOUL.md → 用户确认或修改）
- 通用子智能体蜂群（2~5 个并行 Worker，无固定 persona）
- 多 Agent 结果互验：多个 Worker 结果互相验证，少数服从多数，提高输出可靠性
- 交互流程：主智能体对话确认需求 → 拆解为 subtask 列表 → 编排器并行派发 → Worker 互验 → 收集结果 → 主智能体汇总输出

### 2.2 LLM 提供商（用户自选，无默认优先级）

| 类别 | 提供商 | 适配方式 |
|------|--------|---------|
| 国内大厂 | 通义千问(Qwen/阿里)、文心一言(ERNIE/百度)、智谱GLM、Kimi(月之暗面)、豆包(字节)、混元(腾讯) | OpenAI 兼容 API 通用适配器 |
| 国外 | OpenAI、Anthropic | 原生 API 适配 |
| 本地/开源 | Ollama、DeepSeek | 本地 URL + API Key |
| 云推理 | NVIDIA NIM | NGC API 适配 |
| 视觉 | 以上所有支持多模态的模型 | chat_with_image 统一接口 |

### 2.3 UI 设计

配色：暖色调，三色系用户可选
- 温暖橙 #FF8C42 / #FFF3E0 / #FFE0B2
- 柔和粉 #FF7EB3 / #FFF0F5 / #FFD6E7
- 奶油米白 #FEF9EF / #FFF8E1 / #FFECB3

字体：Geist / PingFang SC / Microsoft YaHei / JetBrains Mono

布局：沿用原 Nebula 侧边栏分组导航设计（左侧 Sidebar 分组导航 + 右侧 content-card 毛玻璃卡片 + 顶部 Titlebar）

```
+----------+-------------------------------------------------------+
| Titlebar | [窗口标题]                            [最小化][悬浮球][关闭] |
+----------+-------------------------------------------------------+
| ★ 收藏   |                                                       |
|   对话   |                                                       |
|   蜂群   |                                                       |
| -------- |                                                       |
| 📁 工作  |                  content-card                          |
|   记忆   |                 （毛玻璃卡片）                           |
|   代码   |                                                       |
|   技能   |                                                       |
| -------- |                                                       |
| 📊 监控  |                                                       |
|   仪表盘 |                                                       |
|   积分   |                                                       |
|   诊断   |                                                   +---+ |
| -------- |                                                   |助理| |
| ⚡ 高级  |                                                   +---+ |
|   影子   |                                                       |
|   长任务 |                                                       |
| -------- |                                                       |
| ⚙ 系统  |                                                       |
|   设置   |                                                       |
+----------+-------------------------------------------------------+
```

### 2.4 侧边栏分组导航结构

| 分组 | 导航项 | 内容 |
|------|--------|------|
| ★ 收藏 | 对话 | 主聊天界面 |
| | 蜂群 | 蜂群协作面板 |
| 📁 工作 | 记忆 | 记忆浏览（6 层记忆管理） |
| | 代码 | 代码工作台 |
| | 技能 | 技能市场 + MCP 工具 |
| 📊 监控 | 仪表盘 | Dashboard 总览（Token 用量、成本报告、心跳状态） |
| | 积分 | 积分与用量统计 |
| | 诊断 | 安全审计、待审批、运行诊断 |
| ⚡ 高级 | 影子 | Shadow Workspace |
| | 长任务 | Long Task 面板、计划管理、定时任务 |
| ⚙ 系统 | 设置 | LLM 配置、工具配置、灵魂与意志、身份配置、角色管理(persona切换)、高级配置、系统信息、版本日志 |

### 2.5 迪士尼卡通虚拟助理

- 位置：窗口右下角常驻
- 行为：对话时微笑/倾听表情，蜂群工作时思考状，任务完成时祝贺表情 + 弹窗提醒
- 微动效：呼吸动画、眨眼、点头（CSS animation / Lottie）
- 配色：暖色风格卡通助理，配色严格跟随三色系（温暖橙/柔和粉/奶油米白），3 个色系对应 3 套助理配色

### 2.6 首次引导流程

用户打开应用 → 暖色调欢迎界面，卡通助理问好 → 四步选择：
1. 工作内容（编程/写作/自媒体/数据处理/项目管理/其他）
2. 日常任务偏好（多选）
3. 沟通风格（简洁/详细/幽默/专业）
4. AI 根据以上选择自动生成 SOUL.md → 展示 → 用户确认或修改 → 写入

### 2.7 保留与移除

保留：6 层记忆（Obsidian 式双向链接 + 图谱可视化 + 智能自动推荐）、Wiki 编译（自动编译 + 手动编辑）、技能生态(市场+沙箱+自进化技能蒸馏)、蜂群编排(多Agent互验)、进化引擎(4阶段全量)、Dashboard 仪表盘、Long Task 面板、Diagnostics 诊断、IM 绑定(微信+飞书)、事件流、定时任务、计划管理、MCP 协议、悬浮球(Floating Ball)、Loop 循环迭代(预算控制+审计日志)、多设备同步(sync)、OAuth身份(identity)、去中心化身份(DID)、OS感知(剪贴板监控+文件夹监控+系统托盘+屏幕实时感知(可开关))、全量多模态(图片+语音输入+语音输出+视频分析)、安全模块(E2EE加密+密钥轮换+ACL权限+注入防护+SSRF防护)

移除：代码模式(Monaco Editor/CodeMode)、Arena 对比面板、Shadow Workspace 影子工作区

v2 迭代：图像生成

### 2.8 记忆系统

- 6 层记忆（L0~L5），数据结构沿用 Nebula 设计
- 记忆内容存储为 HTML 格式（含 CSS 样式、<details>折叠、表格、关联链接）
- plain_text 字段从 HTML innerText 提取，用于 FTS5 搜索
- 向量存储：ChromaDB + bge-small-zh-v1.5 embedding
- Obsidian 式双向链接：记忆内容中用 [[标题]] 互相引用，点击跳转，自动发现反向链接
- 图谱可视化：记忆关联关系的节点+连线图，支持按层级/标签/时间过滤
- 智能自动推荐：基于语义相似度自动推荐相关记忆，写入时自动建议可链接的已有记忆

## 3. 技术方案

### 3.1 技术栈

| 层 | 技术 | 原因 |
|----|------|------|
| 后端 | Python 3.11 + FastAPI + uvicorn | 异步原生、自动 API 文档、生态最广 |
| 数据库 | SQLite(aiosqlite) + ChromaDB | 零配置、纯 Python、本地优先 |
| LLM | 统一 Provider Adapter + SSE 流式 | 一套接口、多厂商切换，用户自选无默认 |
| 前端 | Preact + TailwindCSS(Vite) | 复用现有组件 |
| 桌面 | PyWebView（原生窗口） | 和 jiuwenswarm 一样体验 |
| 打包 | PyInstaller | Windows .exe |
| 包管理 | pip + 阿里云镜像 | 国内加速 |
| 测试 | pytest（边开发边测试） | 保证质量 |

### 3.2 Provider Adapter 设计

国产大厂统一用 OpenAICompatibleProvider（一个类覆盖通义千问/文心/GLM/Kimi/豆包/混元），仅 endpoint 和 model_name 不同。

### 3.3 项目目录

```
D:\Pangu Nebula/
├── server/
│   ├── main.py, config.py
│   ├── api/          (chat, persona, swarm, memory, skills, wiki, sync, identity, security, os, multimodal, channel, evolution, loop)
│   ├── core/
│   │   ├── persona/  (manager, agent, soul_compiler)
│   │   ├── swarm/    (orchestrator, worker, composer, verifier)  # verifier: 多Agent结果互验
│   │   ├── memory/   (store, vector, sponge, blackhole, layers, linker, graph)  # linker: 双向链接, graph: 图谱可视化
│   │   ├── skills/   (engine, sandbox, marketplace, distiller)  # distiller: 自进化技能蒸馏
│   │   ├── wiki/     (compiler, editor)
│   │   ├── evolution/ (engine, pipeline, reflect, soul)
│   │   ├── loop/     (budget, audit, phase_ring)  # Loop循环迭代
│   │   ├── providers/ (base, openai, anthropic, openai_compat, deepseek, ollama, nim, registry)
│   │   ├── sync/      (crdt, e2ee, key_vault, relay, pairing, device)
│   │   ├── identity/  (did_key, document, oauth, oauth_manager)
│   │   ├── security/  (acl, injection_guard, ssrf_guard, keychain, key_rotation)
│   │   ├── os/        (clipboard_watcher, file_watcher, tray, shortcut, screen_capture)
│   │   ├── multimodal/ (vision, asr, tts, video)
│   │   ├── channel/   (wechat, feishu, router)
│   │   └── proactive/ (heartbeat, scheduler, triggers)
│   └── db/           (connection, models, migrations)
├── frontend/         (Preact + TailwindCSS)
│   └── src/
│       ├── components/
│       │   ├── Sidebar.tsx           [新] 侧边栏分组导航
│       │   ├── Titlebar.tsx          [新] macOS风格标题栏
│       │   ├── MascotAssistant.tsx   [新] 暖色迪士尼卡通助理
│       │   ├── OnboardingWizard.tsx  [改] AI辅助生成角色
│       │   ├── ChatPanel.tsx         [改]
│       │   ├── PersonaManager.tsx    [新]
│       │   ├── SwarmProgress.tsx     [改]
│       │   ├── MemoryGraph.tsx       [新] 记忆图谱可视化
│       │   ├── FloatingBall.tsx      [迁] 悬浮球
│       │   └── ...（其它保留组件）
│       └── theme/index.ts           [改] 暖色三色系
├── data/    (personas, skills, wiki, nebula.db)
├── launch.py, requirements.txt, pyproject.toml
└── README.md
```

## 4. 验收标准

> 更新于 2026-07-11 | Phase 1-8 已完成,后端 API 层验收通过

### 功能
- [x] 3 个预置角色可创建/切换/删除，AI 辅助生成 system_prompt + SOUL.md，切换后对话风格明显变化 *(Phase 2)*
- [x] 蜂群全链路：确认需求 -> 拆解 -> 并行执行 -> 多Agent互验 -> 汇总，无报错 *(Phase 3)*
- [x] 自进化技能蒸馏：成功任务自动蒸馏新技能，失败任务记录教训 *(Phase 5)*
- [x] 预算控制：Token/时间/金额预算，超预算自动停止或降级 *(Phase 6)*
- [x] SSE 流式响应正常（打字机效果） *(Phase 2)*
- [x] 图片粘贴后 AI 正确描述内容 *(Phase 7)*
- [x] 语音输入输出正常（ASR/TTS） *(Phase 7)*
- [x] 视频分析正常（帧抽取+图像理解） *(Phase 7)*
- [x] 6 层记忆写入/查询正常（HTML 格式 + Obsidian 式双向链接 + 图谱可视化 + 智能推荐） *(Phase 4)*
- [x] 记忆双向链接：[[标题]] 互引、反向链接发现、图谱可视化 *(Phase 4)*
- [x] 技能创建/执行/导入导出正常 *(Phase 5)*
- [x] Wiki 编译：对话后自动生成 HTML 笔记，支持手动编辑 *(Phase 6,从 Phase 5 推迟)*
- [x] 进化引擎 4 阶段管道完整执行 *(Phase 6)*
- [x] Loop 循环迭代：多轮自动迭代优化 + 预算控制 + 审计日志 *(Phase 6)*
- [x] 多设备同步：CRDT + E2EE 加密 *(Phase 9)*
- [x] OAuth 身份：Gmail/GitHub/Notion/Slack *(Phase 8)*
- [x] DID 去中心化身份 *(Phase 8)*
- [x] IM 渠道：微信 + 飞书消息桥接 *(Phase 9)*
- [x] OS 感知：剪贴板监控、文件夹监控、系统托盘、屏幕实时感知（可开关） *(Phase 7)*
- [x] 安全：E2EE 加密、密钥轮换、ACL 权限、注入防护、SSRF 防护 *(Phase 8)*
- [x] MCP 协议正常工作 *(Phase 10)*

### UI
- [x] 三色系可切换，色值正确 *(Phase 11)*
- [x] 侧边栏分组导航 5 组 12 项，展开/收起流畅 *(Phase 11)*
- [x] 卡通助理右下角常驻，表情变化正常，配色跟随三色系 *(Phase 11)*
- [x] 首次引导流程完整，AI 辅助生成 SOUL.md *(Phase 11)*
- [x] 最小窗口 800x600 不溢出 *(Phase 11)*
- [x] 记忆图谱可视化：节点+连线、按层级/标签/时间过滤 *(Phase 11 前端, Phase 4 后端API已就绪)*
- [x] 悬浮球功能正常 *(Phase 11)*

### 桌面
- [x] PyWebView 原生窗口启动，和 jiuwenswarm 体验一致 *(Phase 11)*
- [x] PyInstaller .exe 在无 Python Windows 上运行 *(Phase 11 spec 就绪)*

### LLM
- [x] 每个 Provider 独立调用成功 *(Phase 2)*
- [x] 国产大厂通过 OpenAI 兼容 API 正常调用 *(Phase 2)*
- [x] 用户自选 Provider，无强制默认 *(Phase 2)*

### 当前进度
- **后端 API 层**: Phase 1-10 完成,88 个任务,27 个路由模块,193+ API 端点
- **前端 UI 层**: Phase 11 完成,14 个组件,24 模块,137KB JS + 13.8KB CSS
- **打包**: PyInstaller spec + build.py + dev.py 就绪
- **测试**: 16 passed(3单元 + 10冒烟 + 3前端构建)
- **通过率**: 30/30 全部验收项已通过 (100%)
