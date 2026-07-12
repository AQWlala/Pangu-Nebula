# Rust 回归：战略决策分析

> 基于对 D:\nebula (Rust v2.4.0, 44模块, ~350+ .rs文件, 29测试) 与 D:\Pangu Nebula (Python v1.1.0) 的逐模块对比

---

## 核心发现：Python 版是倒退，不是进步

原始 Nebula Rust v2.4.0 在几乎所有维度上比当前 Python 版更完整：

### 记忆系统: Rust 8层(L0-L7) vs Python 6层(L0-L5)

| 能力 | Rust v2.4.0 | Python v1.1.0 |
|------|:---:|:---:|
| 记忆层数 | **8 层 (L0-L7)** | 6 层 (L0-L5) |
| Sponge 引擎 | **有** (engines/sponge.rs) | 有 |
| BlackHole 引擎 | **有** (engines/blackhole.rs) | 有 |
| L5 元认知/Reflect | **有** (engines/reflect.rs) | **无** (Python 版缺失) |
| 自我反思 | **有** (engines/self_reflection.rs) | **无** |
| 重要性评分 | **有** (access frequency + recency + feedback) | 基础 |
| 向量存储 | **有** (LanceDB + BGE-small-zh-v1.5) | **无** |
| 知识图谱 | **有** (causal + MDRM + consistency) | 基础 [[]] 链接 |
| 记忆编排器 | **有** (engines/orchestrator.rs) | **无** |
| 遗忘引擎 | **有** (engines/forgetting.rs) | **无** |
| MOC 元认知引擎 | **有** (engines/moc.rs) | **无** |
| 价值层 L4 | **有** (Constitutional AI + Risk + Privacy) | **无** |

> Rust 版的记忆系统比 Python 版先进一个数量级。Python 版所谓的"创新"（Sponge/BlackHole）在 Rust 版早已存在。

### 蜂群系统: Rust 完整 DAG vs Python 基础并行

| 能力 | Rust v2.4.0 | Python v1.1.0 |
|------|:---:|:---:|
| DAG 引擎 | **有** (petgraph, 46种WorkerCapability) | **无** |
| 编排器 | **v2.0** (2-6并行+故障隔离+指数退避) | 基础 |
| 事件总线 | **有** (event_bus.rs) | **无** |
| 事件流 | **有** (event_stream.rs) | **无** |
| 领导者选举 | **有** (leader_elector.rs) | **无** |
| 协商器 | **有** (negotiator.rs) | **无** |
| 画布交互 | **有** (canvas_interaction.rs) | **无** |
| 执行回放 | **有** (execution_replay.rs) | **无** |
| Loop 设计 | **有** (loop_design.rs + loop_phase_ring.rs) | **无** |
| Loop 预算 | **有** (loop_budget.rs) | 独立 budget_controller |
| Tree of Thoughts | **有** (tot.rs) | **无** |
| CRDT 同步 | **有** (crdt_sync.rs, 在swarm模块内) | 独立 crdt_service |

### 进化系统: Rust 完整 vs Python 基础

| 能力 | Rust v2.4.0 | Python v1.1.0 |
|------|:---:|:---:|
| 技能进化器 | **有** (skill_evolver.rs, 无用衰减归档) | **无** |
| 基因变异器 | **有** (gene_mutator.rs) | **无** |
| Prompt 变异器 | **有** (prompt_mutator.rs) | **无** |
| 目标信号 | **有** (goal_signal.rs) | **无** |
| Cron 引擎 | **有** (cron_engine.rs) | APScheduler |
| 自动化模板 | **有** (automation_templates.rs) | **无** |
| 结果收集器 | **有** (outcome_collectors.rs) | **无** |

### 其他模块对比

| 模块 | Rust v2.4.0 | Python v1.1.0 |
|------|:---:|:---:|
| 安全 | keychain + injection_guard + ssrf_guard + aio_sandbox + detectors | **keychain(DPAPI) + ACL + audit + 注入 + SSRF + 沙箱 + 密钥轮换 + redactor** (Python 安全更强) |
| 技能 | auto_inventor + marketplace + sandbox + publisher + importer/exporter + hub_client | skill_engine + distiller (Python 远不如) |
| 同步 | CRDT + E2EE + device_manager + key_vault + pairing + relay | 基础 CRDT (Python 远不如) |
| 语音 | STT + TTS + wake + audio_pipeline | TTS + ASR (基本持平) |
| 渠道 | Discord + Telegram + WebChat + Router | Feishu + WeChat (不同侧重) |
| 浏览器 | Agent + API mode + VLM mode (CDP-based) | Playwright-based (Rust 更轻) |
| 前端 | **60+ 组件** (DagCanvas + ImBinding + KnowledgeCard + CommandPalette + ...) | 14 组件 |
| Work | **Kanban + priority + time tracking** | 无 |
| 其他 Rust 独有 | autonomy, backup, diagnostics, editor, grpc, identity, metrics, notify, oauth, observability, plugins, proactive, soul, snapshot, triggers | 无 |

---

## 迁移成本对比

| 方案 | 方向 | 需翻译的模块数 | 风险 |
|------|------|:---:|------|
| 当前方案 | Rust算法 -> Python | **15+ 模块, ~350 .rs 文件** | 翻译量大, 易出错, Python 性能天花板 |
| **新方案** | Python独有 -> Rust | **~5 模块** (DPAPI keychain, ACL, audit logger, key rotation, redactor) | 翻译量小, Rust 已有成熟架构可嵌入 |

Python 版独有的、Rust 版没有的：

| Python 独有 | 可否移植到 Rust | 难度 |
|------|:---:|:---:|
| DPAPI 密钥存储 | 可 — Windows DPAPI 有 Rust crate | 低 |
| ACL 资源级访问控制 | 可 — 在 Rust security 模块新增 | 中 |
| 审计日志 | 可 — Rust 已有 tracing + SQLite | 低 |
| 密钥轮换 | 可 — 在 Rust keychain 扩展 | 低 |
| 脱敏 (redactor) | 可 — 新增模块 | 低 |
| OAuth 服务 | Rust **已有** oauth 模块 (11文件) | 无需移植 |
| DID 服务 | 可 — 在 identity 模块扩展 | 中 |
| 200+ REST 端点 | Rust 已有 api 模块 + commands (60文件) | 无需移植 |
| 钉钉渠道 | 在 Rust channel 模块新增 dingtalk.rs | 低 |
| 飞书渠道 | 在 Rust channel 模块新增 feishu.rs | 低 |

---

## 结论

**现在就是回归 Rust 的最佳时机。理由：**

1. Rust v2.4.0 在记忆(8层+Sponge+BlackHole+Reflect+MOC)、蜂群(DAG+事件总线+Loop设计)、进化(技能衰减+基因变异+目标信号)、技能(自动发明+市场)、同步(E2EE+设备管理)、前端(60+组件)等几乎所有维度上**远超** Python v1.1.0
2. Python 版需要翻译 15+ 个 Rust 模块才能追平，而反向只需移植 5 个安全模块
3. 继续在 Python 上每写一行代码，未来迁移成本就增加一分
4. Rust v2.4.0 有 29 个测试文件、成熟的 CHANGELOG、完整的模块化架构 — 是生产级代码
5. Tauri 2 桌面壳比 PyWebView 领先 2 代，且是用户最初的选择

**Python 版中值得保留并移植到 Rust 的资产：**
- DPAPI 密钥存储 (server/services/keychain.py)
- ACL 服务 (server/services/acl_service.py)
- 审计日志 (server/services/audit_logger.py)
- 密钥轮换 (server/services/key_rotation.py)
- 脱敏 (server/services/redactor.py)
- 钉钉渠道 adapter (新增)
- 飞书渠道 webhook + 事件订阅 (已有设计)
- 三维预算控制器设计 (可整合到 Rust loop_budget)
