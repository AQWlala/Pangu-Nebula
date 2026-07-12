# Pangu Nebula vs NomiFun vs OpenOcta — 全维度对比分析报告

> **分析日期**: 2026-07-12 (v1.1.0 核实版)
> **分析对象**: Pangu Nebula (v1.1.0) / NomiFun (nomifun-tauri, v0.2.17) / OpenOcta (v1.0.5)
> **数据来源**: GitHub README + 源码审查 + CI 日志 + 飞书智能体交叉验证
> **核实状态**: 所有 Pangu Nebula 数据已通过源码 + CI 日志核实

---

## 一、三方定位速览

| 属性 | Pangu Nebula | NomiFun | OpenOcta |
|------|:-----------:|:-------:|:--------:|
| 一句话定位 | 具备元认知的多 Agent 认知运行时 | 本地优先的超级 AI 工作站 | 开箱即用的企业级 Agent 平台 |
| 技术栈 | Python 3.11 + FastAPI + Preact + PyWebView | Rust 2024 + Tauri 2 + React 19 | Go 1.24 + 嵌入式 SPA (Lit) |
| 分发形态 | PyInstaller onedir (~54MB, 206 文件) | Tauri 原生安装包 (~50-80MB) | 单一二进制 (~30MB) |
| 许可协议 | MIT | Apache-2.0 | Apache-2.0 (商业授权) |
| 成熟度 | v1.1.0, 10 commits, 0 stars | v0.2.17, 877 commits, 115 stars | v1.0.5, 2981 stars |
| 跨平台 | 仅 Windows (PyInstaller) | Win / Mac / Linux + 自动更新 | Win / Mac / Linux |
| 数据主权 | 完全本地 | 完全本地 (强宣传) | 单二进制, 配置本地 |
| 代码规模 | ~32,000 行 Python + 14 前端组件 | ~50,000+ 行 Rust + React | ~20,000+ 行 Go |

---

## 二、12 维度详细对比

### 1. 记忆系统 (Pangu Nebula 核心优势 — 待验证)

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|-------------|---------|----------|
| 架构 | **6 层认知图谱** (L0工作/L1情景/L2叙事/L3语义/L4程序/L5元认知) | 后台学习器 + 可见可编辑记忆 | 4 层 + Knowledge Vault |
| 压缩 | **海绵体 + 黑洞体双引擎** (吸收/压缩分离) | 单一 distill | 无 |
| 元认知 | **L5 层独立** (策略日志/错误模式/自评) — 系统自动生成 | 无独立元认知层 | 无 |
| 反思 | **LoopEngine 闭环反思** | 无 | 无 |
| 双向链接 | backlinks 自动同步 | 无 | 无 |
| 图谱可视化 | MemoryGraph 组件 | 无 | 无 |
| 跨设备同步 | **CRDT (LWW + OR-Set)** | 无 | 无 |
| **真实场景验证** | ⚠️ **架构设计完成, 缺长对话压测** | ✅ companion 成长已用户验证 | ✅ Knowledge Vault 已落地 |

> **判定**: 记忆系统架构设计领先, 但属"未经验证的架构优势"。6 层 + 双引擎 + 元认知是最难复制的技术壁垒, 但缺少真实 100+ 轮对话场景的压测数据 (L3 语义提取准确率? L5 元认知是否真有反思价值? 压缩后信息损失率?)。NomiFun 的 companion 成长虽浅, 但已有用户验证。**建议优先补验证, 而非继续扩功能。**

### 2. Agent 推理与编排

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|-------------|---------|----------|
| 模型 | **双主控 (Advisor+Orchestrator) + 蜂群 Worker + Verifier** | 单 lead agent + Worker + DAG canvas | 单 Agent + 工具调用 |
| 共识 | **多数投票交叉验证, 保留反对意见** | DAG 节点间互验 | 无 |
| 可视化 | SwarmProgress 组件 (进度条) | **react-flow DAG 画布** (节点可重跑/预配) | 无 |
| 审批 | 无执行前审批 | **计划就绪时对话内审批横幅** | 无 |
| DAG 依赖图 | 规划中 (v0.3.0) | **已实现 — 节点级预检控制** | 无 |
| 预算控制 | **Token/时间/费用 三维预算** | 无显式 | 无 |
| **蜂群多样性** | ⚠️ **依赖 provider 多样性, 仅 3 provider 时蜂群退化为同源** | N/A (单 agent) | N/A |

> **判定**: 蜂群共识在推理可靠性上优于单 Agent, 但壁垒强度为"中"而非"强" — 当前仅 3 个 provider, worker 多样性不足, 共识价值受限。NomiFun 的 DAG 画布 + 执行前审批是生产力级的, 我们的 Swarm 更像并行计算, 缺人机协作节点。**蜂群价值随 provider 扩展才能释放, G4 (provider 3→26) 是 A5 (蜂群) 的前置条件。**

### 3. Computer / Browser Use

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|-------------|---------|----------|
| Computer Use | screen_service + clipboard/file watcher (Python) | **自建 Rust in-process** (无障碍树 + SoM + OCR) | 无 |
| Browser Use | browser_service.py (依赖 Playwright, try/except 容错) | **进程内 CDP 引擎** — ARIA 监听 + 出口防火墙 | 无 |
| 屏幕感知 | PIL / PyTesseract (stub, 未接真实模型) | **无障碍树 + Vision OCR** (可用) | 无 |
| 剪贴板/文件 | pyperclip / watchdog | 内置 | 无 |

> **判定**: 质的差距。NomiFun 的进程内 Rust 实现无第三方依赖、token 成本低、细粒度控制。我们的 browser_service 依赖 Playwright (重量级, 需额外安装浏览器), 且 screen_service/vision_service 等多模态服务当前为 stub (try/except import 防崩溃, 未接真实模型)。这是需要战略级投入才能追平的维度。

### 4. 无人值守自动化

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| 框架 | scheduler_service (cron 定时触发) | **AutoWork + IDMM** | Cron 模块 |
| 故障保活 | — | **IDMM 三层** (规则→backup model→sidecar) | — |
| 需求平台 | — | **CRUD + 看板 + 轮转认领 + claim** | — |
| 完成通知 | — | Lark / Slack / Webhook | — |

> **判定**: NomiFun 的生产力护城河。我们的 scheduler 只是定时触发, IDMM 是"agent 永不放弃"的工程实现。**这是最值得抄的功能** — 记忆+反思+无人值守 = 真正的自进化闭环。当前我们的 LoopEngine 有反思但无保活, agent 一遇 provider 故障即停。

### 5. IM 渠道覆盖

| 渠道 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| IM 渠道总数 | 2 (wechat + feishu) + 1 路由器 | **11** | 4+ |
| 飞书 | ✅ | ✅ | ✅ |
| 微信 | ✅ | ✅ | ✅ |
| Telegram | — | ✅ | — |
| Discord | — | ✅ | — |
| Slack | — | ✅ | — |
| DingTalk | — | ✅ | ✅ |
| WeCom | — | ✅ | ✅ |

> **判定**: NomiFun 绝对领先。我们缺国内 DingTalk/WeCom (OpenOcta 强项) 和海外 Telegram/Discord。优先补 Telegram (Bot API 最成熟) + DingTalk (CN 企业必须)。

### 6. LLM 提供商生态

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| 提供商数 | 3 (OpenAI/Anthropic/Gemini) | **26+** | 10+ (CN 偏重) |
| 协议 | OpenAI/Anthropic/Gemini | **4 种协议统一适配** | 多协议 |
| DeepSeek | — | ✅ | ✅ |
| Qwen | — | ✅ | ✅ |
| Kimi/Moonshot | — | ✅ | ✅ |
| OpenRouter | — | ✅ | — |
| 多模态 fallback | — | ✅ (图片自动剥离重试) | — |

> **判定**: Provider 生态是最薄弱环节, 且是蜂群价值释放的前置条件 (见维度 2)。3 个 provider 远不足覆盖需求, 优先补 DeepSeek (高性价比) + OpenRouter (聚合网关, 一次接入 200+ 模型)。

### 7. 协议与集成

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|-------------|---------|----------|
| MCP Server | ✅ (JSON-RPC 2.0) | ✅ | ✅ |
| MCP Client | ✅ (mcp_client.py) | ✅ | ✅ |
| ACP | — | **✅ (19+ 外部 Agent)** | — |
| REST API | **220 端点** (25 个 API 文件) | ~20 域 / 150+ 工具 | 标准 REST |
| OpenAPI | — | ✅ (自动生成) | — |
| WebSocket | 有限 | ✅ (实时) | — |

> **判定**: REST API 端点数领先 (220), 但广而不深 — 多数端点是 CRUD 骨架, 缺业务逻辑。缺 ACP 协议 (无法接入外部 Agent) 和 OpenAPI 自动文档。

### 8. 知识库

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| 知识管理 | Wiki (基础浏览) | **统一 KB — 安全写回 + URL 快照** | Knowledge Vault (Obsidian) |
| 写回策略 | — (直接写) | **review inbox + unified-diff 预览 + merge/discard** | — |
| URL 快照 | — | snapshot/live 双模式 (SSRF 防护) | — |
| 作用域检索 | — | 服务端强约束 scope | 语义搜索 |
| RAG 索引 | — | — | ✅ |

> **判定**: 知识库是严重短板。我们的 Wiki 只是浏览, 缺 RAG、索引和写回保护。NomiFun 的安全写回 (review inbox + diff) 是工程典范。**知识库薄弱直接影响记忆系统的 L3 语义层质量 — 没有 RAG, L3 提取无检索验证。**

### 9. 安全 (Pangu Nebula 优势 — 已落地)

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|-------------|---------|----------|
| 主密钥 | **DPAPI + AES-256-GCM (Win) / 0600 (Unix)** ✅ v1.1.0 | 本地信任令牌 | 配置文件 |
| ACL | ✅ (资源级) | — | — |
| 注入防护 | ✅ (模式检测) | 内置 | — |
| SSRF 防护 | ✅ | ✅ | — |
| 沙箱执行 | ✅ (Python 子进程隔离) | 内置 | 审计日志+沙箱 |
| 审计日志 | ✅ (完整追踪) | 内置 | ✅ |
| 密钥轮换 | ✅ (自动轮换) | — | — |
| OAuth / Token | ✅ (完整) | — | — |
| DID | ✅ (did_service) | — | — |
| 脱敏 | ✅ (redactor) | — | — |
| E2EE 同步 | ✅ (X25519 + AES-256-GCM) | — | — |
| CORS 加固 | ✅ v1.1.0 (生产模式限制 origins) | — | — |

> **判定**: 安全栈全面领先 — 11 项覆盖 vs NomiFun 3 项 vs OpenOcta 2 项。这是企业落地的硬需求, NomiFun 偏个人/轻企业场景。v1.1.0 已完成 DPAPI keychain + CORS 加固, 安全栈从"设计完成"升级为"已落地"。

### 10. 多模态

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| Vision | ⚠️ stub (vision_service, 未接真实模型) | ✅ OCR (嵌入 computer use, 可用) | — |
| ASR | ⚠️ stub (asr_service, 未接真实模型) | — | — |
| TTS | ⚠️ stub (tts_service, 未接真实模型) | — (通过工具) | — |
| Video | ⚠️ stub (video_service, 未接真实模型) | — | — |
| Screen | ⚠️ stub (screen_service) | ✅ accessibility tree (可用) | — |

> **判定**: 多模态广度领先, 但**深度为零** — vision/asr/tts/video/screen 服务文件存在, 但都是 try/except import 防崩溃的 stub, 未接真实模型。NomiFun 的 OCR 虽然只覆盖一个模态, 但是真能用的。**不应将 stub 计入"领先"维度。**

### 11. 部署与分发

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| 体积 | ~54MB (onedir, 206 文件) | ~50-80MB (Tauri 原生) | **~30MB (单二进制)** |
| 启动 | ~2s | ~1s | **<1s** |
| 跨平台 | 仅 Win (PyInstaller) | **Win/Mac/Linux + updater** | Win/Mac/Linux |
| 自动更新 | — | **Tauri updater + latest.json** | — |
| Docker | — | Dockerfile + compose | — |
| Linux 包 | — | AppImage/deb | deb/rpm/tar.gz |
| console 模式 | ✅ v1.1.0 console=False (stdout 重定向) | N/A (Tauri 原生) | N/A |

> **判定**: 分发是最大工程差距。v1.1.0 修复了 console=False 崩溃, 但仍只有 Win onedir。NomiFun 已有三平台 + 自动更新 + Docker。OpenOcta 的单二进制模式是体积标杆。

### 12. 工程化成熟度

| 项 | Pangu Nebula | NomiFun | OpenOcta |
|------|:---:|:---:|:---:|
| CI/CD | ✅ 4 workflow (ci/release/pages/security) | **成熟 + 跨平台可靠性** | ✅ |
| 测试 | **62 tests** (59 passed + 3 skipped, CI 绿) | design-qa + UI 测试 | 有限 |
| 文档 | README + spec + tasks | **docs/ + guides + 中英双语 + CONTRIBUTING + RELEASING + SECURITY** | ✅ |
| CHANGELOG | — | v0.1.13 → v0.2.17 | ✅ |
| Code of Conduct | — | ✅ | — |
| 贡献者手册 | — | 中英双语 | ✅ |
| Skills 市场 | 自动蒸馏 + 3 个预置 | companion 间 gift 技能 | **766+ Skills** |
| mypy 类型检查 | ✅ v1.1.0 (pyproject.toml) | — | — |

> **判定**: CI + 测试已起步 (62 tests, CI 绿), 但工程文档体系严重落后 NomiFun。缺 CONTRIBUTING/CHANGELOG/RELEASING/SECURITY。Skills 市场内容极少 (3 个预置 vs OpenOcta 766+)。

---

## 三、优势与差距总表

### 领先维度 (5 项硬领先 + 2 项待验证)

| 编号 | 优势 | 壁垒强度 | 验证状态 | 说明 |
|------|------|:---:|:---:|------|
| A1 | **6 层记忆 + 元认知 L5** | 强 | ⚠️ 待压测 | 架构设计完成, 缺真实长对话验证 |
| A2 | **海绵/黑洞双引擎** | 强 | ⚠️ 待压测 | 压缩算法 + 工程分离, 缺信息损失率数据 |
| A3 | **LoopEngine 反思闭环** | 中 | ⚠️ 待验证 | 理念新, 缺大规模验证, soul 阶段为占位 |
| A4 | **安全栈 11 项** | 强 | ✅ 已落地 | DID/脱敏/E2EE/ACL/DPAPI, v1.1.0 已验证 |
| A5 | **CRDT 跨设备同步** | 中 | ✅ 已落地 | 唯一支持多设备无冲突同步 |
| A6 | **蜂群共识验证** | 中 | ⚠️ 受限 | 依赖 provider 多样性, 3 provider 时退化 |
| A7 | **三维预算控制** | 中 | ✅ 已落地 | Token/时间/费用联动审计 |

> **注意**: API 端点数 (220)、测试数 (62)、多模态服务 (5 个 stub) 是"量"的领先而非"质"的领先, 不计入硬领先维度。

### 落后维度 (16 项, 按严重度排序)

| 编号 | 差距 | 严重度 | 竞争者 | 说明 |
|------|------|:---:|------|------|
| G1 | **LLM 提供商 3 vs 26+** | 🔴 高 | NomiFun | 最紧急, 且是蜂群价值释放的前置条件 |
| G2 | **AutoWork + IDMM 无人值守** | 🔴 高 | NomiFun | 记忆+反思+无人值守=自进化, 缺这环不闭环 |
| G3 | **跨平台分发 + 自动更新** | 🔴 高 | NomiFun/OpenOcta | 仅 Win, 阻碍用户增长 |
| G4 | **原生 Computer Use** — 无 Playwright 依赖 | 🔴 高 | NomiFun | 战略级差距, 需 Rust 重写 |
| G5 | **DAG 画布 + 执行前审批** | 🟡 中 | NomiFun | 体验关键, react-flow 实现 |
| G6 | **知识库安全写回** — review inbox + diff | 🟡 中 | NomiFun | 影响 L3 语义层质量 |
| G7 | **多模态 stub → 真实模型接入** | 🟡 中 | 自身 | 5 个服务文件都是 stub |
| G8 | **记忆系统压测验证** | 🟡 中 | 自身 | L3/L5 真实效果未验证 |
| G9 | **IM 渠道 2 vs 11** | 🟡 中 | NomiFun | 缺 Telegram/Discord/DingTalk |
| G10 | **缺少 ACP 协议** — 无法接入外部 Agent | 🟡 中 | NomiFun | 19+ 外部 Agent |
| G11 | **工程文档体系** — CONTRIBUTING/CHANGELOG/RELEASING | 🟡 中 | NomiFun | 中英双语体系 |
| G12 | **桌面壳落后 2 代** — PyWebView vs Tauri 2 | 🟡 中 | NomiFun | 影响 G3 |
| G13 | **Docker 部署** | 🟢 低 | NomiFun/OpenOcta | 1 小时可完成 |
| G14 | **终端模式** — 无 PTY/CLI | 🟢 低 | NomiFun | 已实现 |
| G15 | **远程访问** — 无 QR 配对 | 🟢 低 | NomiFun | QR+WebSocket |
| G16 | **技能市场内容** — 3 vs 766+ | 🟢 低 | OpenOcta | 需社区共建 |

---

## 四、优化建议 (短期 v0.2 — 补 G1/G9/G11/G13)

### O1: 扩展 LLM 提供商 (G1, 最高优先级)

当前仅 3 个 provider, 严重限制用户群和蜂群多样性:
- **DeepSeek** — OpenAI 兼容协议, 几乎零成本接入, CN 用户首选
- **OpenRouter** — 聚合网关, 一次接入覆盖 200+ 模型
- **Qwen / Kimi / Zhipu** — CN 生态必备
- 协议抽象层 — 参照 NomiFun 的 4 协议方案, 减少新增 provider 的代码量

### O2: 扩展 IM 渠道 (G9)

复用现有 channel_router 模式, 最少补充:
- **Telegram** — Bot API 最成熟, 全球用户量最大
- **Discord** — 社区驱动项目标配
- **DingTalk** — CN 企业必须 (OpenOcta 已支持)

### O3: 补工程文档 (G11)

直接套 NomiFun 模板, 内容已有, 只需整理:
- CHANGELOG.md — 从 Git log 提取
- CONTRIBUTING.md — 开发环境 + PR 流程 + 代码风格
- SECURITY.md — 已有 11 项安全措施, 整理为披露政策
- RELEASING.md — PyInstaller 打包 + GitHub Release 流程

### O4: Docker 部署 (G13)

单文件 Dockerfile, 1 小时可完成:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server/ ./server/
COPY frontend/dist/ ./frontend/dist/
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

### O5: 多模态 stub → 真实接入 (G7, 最小化)

当前 5 个多模态服务都是 stub。最小化方案:
- **TTS** — 接 edge-tts (免费, 无需 API key)
- **ASR** — 接 Whisper API (OpenAI 兼容)
- **Vision** — 接已注册的 provider 多模态能力
- Video/Screen 暂保留 stub, 标注"实验性"

---

## 五、迭代建议 (中期 v0.3-v0.6)

### I1: AutoWork + IDMM 无人值守框架 (v0.3, 补 G2)

最值得抄 NomiFun 的功能。已有 scheduler_service, 在其上加三层保活:
- **L1 规则层** — 无 LLM, 超时/异常 → 规则重试
- **L2 backup model 层** — 主 provider 失败 → 自动切换 backup model (依赖 O1 provider 扩展)
- **L3 sidecar 层** — agent 决策停滞 → sidecar 注入提示恢复

新增 `server/services/autowork.py` + `server/services/idmm.py`, 复用现有 scheduler API。**记忆+反思+无人值守 = 真正的自进化闭环。**

### I2: 记忆系统压测验证 (v0.3, 补 G8)

在补功能之前, 先验证已有架构的真实效果:
- 100 轮对话后 L3 语义提取准确率
- L5 元认知是否真有反思价值 (对比有/无 L5 的任务完成率)
- 黑洞体压缩后信息损失率
- 海绵体吸收的噪声过滤率
- 产出: `docs/memory-benchmark.md` 压测报告

### I3: DAG 编排画布 (v0.4, 补 G5)

引入 react-flow (NomiFun 同款), 前端新增 DAGCanvas.tsx:
- Orchestrator 分解结果 → DAG 节点
- 节点状态: pending / running / completed / failed
- 点击节点 → 主区显示该 worker 实时对话
- 计划就绪 → 对话内审批横幅 (参照 NomiFun)
- 节点级预检: per-node model/brief override

### I4: 知识库安全写回 (v0.4, 补 G6)

Wiki 模块加 `review_queue` 表:
- agent 写 wiki → 进 review inbox, 不直接落库
- unified-diff 预览 → 用户 merge/discard
- 服务端强约束 scope (agent 不能越权写其他域)
- 补 RAG 索引 (L3 语义层质量保障)

### I5: 强化蜂群引擎 (v0.5)

- Worker 动态扩缩容 (2-8 workers)
- 反对意见自动升级为对话提示
- 失败 worker 重试策略优化
- **蜂群多样性指标** — 监控不同 provider 的 worker 分布

### I6: ACP 协议 + IM 扩展 (v0.5, 补 G10)

ACP 让外部 Agent (Claude Code、Codex、Gemini CLI) 借用 Pangu Nebula 的记忆和蜂群能力。DingTalk/WeCom 适配复用现有 channel_router 模式。

---

## 六、扩展建议 (长期 v1.0+ — 建护城河)

### E1: 记忆系统产品化 — pangu-memory-sdk (放大 A1)

把 6 层记忆 + 元认知单独打包为 SDK:
- 独立 PyPI 包, 任何 agent 框架可接入
- 海绵/黑洞引擎作为可插拔策略
- CRDT 同步作为独立模块
- **这是 NomiFun 和 OpenOcta 都给不了的 IP, 可单独授权**

### E2: 原生 Computer Use (补 G4, 战略级)

推荐路线 A — 局部 Rust 加速:
- 用 Rust 重写 computer_use 核心模块 (无障碍树 + CDP 引擎)
- Python 通过 PyO3 调用, 保留现有架构
- 渐进式迁移: 先替换 Browser Use, 再替换 Computer Use
- **不推荐整体迁 Tauri** (成本极高, 且 Python AI 生态优势不可放弃)

### E3: 企业安全合规认证 (放大 A4)

已有 DID/脱敏/E2EE/ACL 基础, 扩展:
- SOC 2 Type II 审计文档
- 国密算法支持 (SM2/SM4) 适配信创市场
- 数据分类标签 (redactor 扩展为 DLP 引擎)
- **这是 OpenOcta 的软肋, 我们的差异化战场**

### E4: 跨实例技能联邦 (补 G16)

Distiller 已能固化技能, 扩展:
- 技能导出为 `.skill` 包 (JSON + 依赖声明)
- P2P 技能市场 (非中心化)
- 多实例间技能 gift (基于现有 E2EE 同步通道)

### E5: 跨平台支持 (补 G3)

- macOS/Linux: PyWebView 理论跨平台, DPAPI fallback 已就绪 (0600), 需适配测试
- 远期桌面壳可考虑 Tauri 2 替换 PyWebView, 核心引擎保留 Python

---

## 七、优先级路线图

| 版本 | 时间 | 内容 | 补的差距 | 验证状态 |
|------|------|------|------|------|
| **v0.2.0** | 1 月内 | Provider 扩展 (DeepSeek/OpenRouter) + Telegram/Discord/DingTalk + 工程文档 + Docker + TTS/ASR 真实接入 | G1/G9/G11/G13/G7 | 基础功能补全 |
| **v0.3.0** | 2 月 | AutoWork+IDMM 无人值守 + **记忆系统压测验证** | G2/G8 | 自进化闭环验证 |
| **v0.4.0** | 3 月 | DAG 画布 (react-flow) + 知识库安全写回 + RAG 索引 | G5/G6 | 体验关键 |
| **v0.5.0** | 4 月 | 强化蜂群引擎 + ACP 协议 + DingTalk/WeCom 渠道 | G10 | 蜂群价值释放 |
| **v1.0.0** | 6 月 | 记忆 SDK 独立 + 企业安全合规 + 跨平台适配 | A1/A4/G3 | 护城河建立 |
| **v2.0.0** | 12 月 | Rust Computer Use 局部重写 + 技能联邦 + 桌面壳 Tauri 迁移 | G4/G12/G16 | 战略级追平 |

---

## 八、差异化定位

三者各有赛道, 不应全面竞争:

- **OpenOcta**: "30 秒安装的 AI 员工" — 轻量、简单、CN 生态。适合个人办公自动化。
- **NomiFun**: "超级 AI 工作站" — 全功能、原生、开放。适合技术用户和开发者。
- **Pangu Nebula**: **"有元认知的 Agent 运行时"** — 深度认知、自我进化、蜂群共识。适合对 Agent 可靠性和智能深度有高要求的严肃场景。

**核心策略**:
- 不在 IM 渠道数量、Provider 数量、安装包体积上与两者比拼
- 聚焦 L5 元认知、蜂群共识、双引擎记忆、进化闭环 — 最难复制的技术壁垒
- **但必须先验证 (v0.3 压测) 再扩功能** — 架构领先 ≠ 效果领先
- 适合场景: 代码审查、安全审计、知识管理、战略分析 — 需要 Agent 真正理解自己做了什么的场景

---

## 九、总结一览

| 维度 | 领先者 | Pangu Nebula 排名 | 差距性质 | 验证状态 |
|------|--------|:---:|------|------|
| 记忆深度 | **Pangu Nebula** | 1 | 核心护城河 | ⚠️ 待压测 |
| Agent 可靠性 | **Pangu Nebula** | 1 | 蜂群共识 (受 provider 限制) | ⚠️ 受限 |
| 自我进化 | **Pangu Nebula** | 1 | 4 阶段闭环 (soul 占位) | ⚠️ 待验证 |
| 安全体系 | **Pangu Nebula** | 1 | 11 项 vs 竞争 2-3 项 | ✅ 已落地 |
| CRDT 同步 | **Pangu Nebula** | 1 | 独有 | ✅ 已落地 |
| 预算控制 | **Pangu Nebula** | 1 | 三维预算独有 | ✅ 已落地 |
| 多模态 | NomiFun | 2 | 我们 stub vs 他们 OCR 可用 | ❌ 需接入 |
| 桌面原生 | NomiFun | 3 | 战略级差距 | ❌ |
| 无人值守 | NomiFun | 3 | 急需补齐 | ❌ |
| DAG 编排 | NomiFun | 3 | 体验关键 | ❌ |
| IM 渠道 | NomiFun | 3 | 覆盖面差距 | ❌ |
| Provider 生态 | NomiFun | 3 | 最薄弱环节 | ❌ |
| 协议集成 | NomiFun | 3 | 缺 ACP | ❌ |
| 知识库 | NomiFun | 3 | 缺安全写回+RAG | ❌ |
| 工程文档 | NomiFun | 3 | 缺中英双语体系 | ❌ |
| 分发效率 | OpenOcta | 3 | 体积 2x, 仅 Win | ❌ |
| 社区规模 | OpenOcta | 3 | 2981 vs 新项目 | ❌ |
| 技能市场 | OpenOcta | 3 | 766+ vs 3 | ❌ |

---

**核心结论**: Pangu Nebula 的记忆/元认知/安全栈是三方中最深的 (6 项领先, 其中 4 项已落地、2 项待验证), 但工程成熟度和生产力场景广度落后 NomiFun 一个版本周期 (12 项落后)。

**建议策略**: 
1. **短期 (v0.2)**: 补 Provider + IM + 文档 + Docker — 打基础
2. **中期 (v0.3)**: **先验证记忆系统** (压测) 再补 AutoWork — 避免在未验证的架构上继续叠加
3. **长期 (v1.0+)**: 把记忆系统拆成 SDK 单独授权 — NomiFun 和 OpenOcta 都给不了的 IP

> **数据来源**: GitHub README 全文解读 + 源码审查 (220 API 端点 / 52 服务文件 / 14 前端组件 / 62 测试用例) + CI 日志 (59 passed + 3 skipped) + 飞书智能体交叉验证。NomiFun: nomifun/nomifun-tauri (v0.2.17, 877 commits, 115 stars)。OpenOcta: openocta/openocta (v1.0.5, 2981 stars)。Pangu Nebula: 源码审查 (v1.1.0, commit 50d1178)。
