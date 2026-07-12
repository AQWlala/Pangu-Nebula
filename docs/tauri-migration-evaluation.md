# Tauri 2 桌面壳迁移评估报告

> **评估任务**: T5.6 (阶段5 v2.0.0) — 评估用 Tauri 2 替换当前 PyWebView 桌面壳的可行性
> **评估时间**: 2026-07-13
> **评估人**: Pangu Nebula 团队
> **当前状态**: PyWebView + FastAPI (Python 后端)
> **候选方案**: Tauri 2 (Rust 后端 + 系统 WebView 前端)

---

## 1. 背景

Pangu Nebula 当前的桌面壳基于 PyWebView,它在 Python 进程内嵌入系统 WebView(Windows 上为 WebView2,macOS 为 WKWebView,Linux 为 WebKitGTK),配合 FastAPI 后端提供 REST API。

随着项目进入 v2.0.0 阶段5,Rust 重写已被提上日程(参见 `docs/rust-migration-analysis.md`),`rust/browser_use` 与 `rust/computer_use` 模块骨架已经创建。一旦 Rust 核心模块编译完成,Python 层将成为"轻量调度层",此时是否将桌面壳也迁移到 Rust 原生的 Tauri 2,需要一份完整的评估。

本评估覆盖以下维度:
- 技术对比
- 优势与劣势
- 迁移成本估算
- 风险分析
- 决策建议

---

## 2. 技术对比

### 2.1 架构对比

| 维度 | PyWebView | Tauri 2 |
|------|-----------|---------|
| 后端语言 | Python (FastAPI) | Rust (tauri::Builder) |
| 前端运行时 | 系统 WebView(嵌入式) | 系统 WebView(嵌入式) |
| 进程模型 | 单进程(Python 内嵌 WebView) | 双进程(主进程 Rust + WebView 进程) |
| IPC 机制 | HTTP / WebSocket(经 FastAPI) | Tauri Command(直接 IPC,零序列化开销) |
| 包体大小 | ~80-120 MB(PyInstaller 打包) | ~3-10 MB(Rust 编译 + 前端 dist) |
| 启动时间 | 1-3 秒(Python 解释器启动) | <500ms(Rust 原生启动) |
| 内存占用 | 150-300 MB(Python + WebView) | 50-120 MB(Rust + WebView) |
| 跨平台一致性 | 中(各平台 WebView 差异需处理) | 中(同上,但 Tauri 提供统一 polyfill) |
| 自动更新 | 需自建(electron-updater 等价物) | 内置 tauri-plugin-updater |

### 2.2 API 与功能对比

| 功能 | PyWebView | Tauri 2 |
|------|-----------|---------|
| 窗口管理 | `webview.create_window()` | `WebviewWindow::new()` / `Manager::get_webview_window()` |
| JS↔后端调用 | `window.evaluate_js()` + HTTP API | `#[tauri::command]` + `invoke()` |
| 文件系统 | Python `pathlib` + HTTP | `tauri-plugin-fs`(权限沙箱) |
| 系统通知 | `plyer` / `win10toast` | `tauri-plugin-notification` |
| 剪贴板 | `pyperclip` | `tauri-plugin-clipboard-manager` |
| 全局快捷键 | `keyboard` 库 | `tauri-plugin-global-shortcut` |
| 托盘图标 | `pystray` | `tauri::tray::TrayIconBuilder` |
| 原生对话框 | `tkinter.filedialog` | `tauri-plugin-dialog` |
| Shell 命令 | `subprocess` | `tauri-plugin-shell` |
| HTTP 客户端 | `httpx` / `requests` | `reqwest`(Rust)或 `fetch`(前端) |
| SQLite | `aiosqlite` / `sqlalchemy` | `tauri-plugin-sql` 或 `rusqlite` |

### 2.3 开发体验对比

| 维度 | PyWebView | Tauri 2 |
|------|-----------|---------|
| 学习曲线 | 低(Python 生态熟悉) | 中(需掌握 Rust + Tauri API) |
| 调试体验 | Python pdb + 浏览器 devtools | Rust debugger + 浏览器 devtools(分离) |
| 热重载 | Python 自动重启 + Vite HMR | `cargo tauri dev` 同时管理前后端 HMR |
| 类型安全 | 弱(Python 动态类型) | 强(Rust 编译期 + TS) |
| 错误处理 | 异常 + try/except | Result/Option + 显式处理 |
| 测试覆盖 | pytest(现有 286 测试) | cargo test + vitest(需重建) |

---

## 3. 优势分析

### 3.1 性能与资源占用

- **包体大小减少 90%+**: Tauri 2 不打包 Python 解释器与依赖,典型应用 3-10 MB vs PyInstaller 的 80-120 MB。对下载分发与磁盘占用有显著改善。
- **启动时间缩短 60-80%**: Rust 原生二进制的冷启动时间远低于 Python 解释器,用户感知更"轻快"。
- **内存占用降低 50%+**: 无 Python 运行时与 GIL 开销,后台常驻(系统托盘)场景下尤其重要。

### 3.2 安全性

- **编译期保证**: Rust 的所有权与借用检查在编译期消除内存安全漏洞(缓冲区溢出、use-after-free 等),与 PyWebView 的 Python 运行时形成鲜明对比。
- **权限沙箱**: Tauri 2 的 capabilities 系统显式声明前端可调用的命令与资源,默认拒绝(Deny-by-default),比 Python 后端全开放 REST API 更安全。
- **CSP 强制**: Tauri 2 默认启用严格的 Content Security Policy,降低 XSS 风险。

### 3.3 与 Rust 重写战略协同

- **统一技术栈**: 一旦 T5.1/T5.2 的 Rust 模块完成编译,Python 调度层将仅剩薄薄一层。迁移到 Tauri 2 后,可直接通过 `#[tauri::command]` 调用 Rust 函数,免去 PyO3 跨语言桥接的开销。
- **复用 Rust 生态**: Tauri 2 的插件系统(tauri-plugin-*)与现有 Rust crates(reqwest、tokio、serde)无缝集成。
- **与 docs/rust-migration-analysis.md 一致**: 该分析报告已指出"Tauri 2 桌面壳比 PyWebView 领先 2 代,且是用户最初的选择"。

### 3.4 分发与更新

- **跨平台打包**: `cargo tauri build` 一键生成 Windows MSI/EXE、macOS DMG/App、Linux AppImage/Deb。
- **内置自动更新**: `tauri-plugin-updater` 提供签名校验的增量更新,无需自建更新服务器(可对接 GitHub Releases)。
- **代码签名**: Tauri 2 集成 code-signing 工具链,Windows EV 证书与 macOS notarization 流程更顺畅。

### 3.5 现代化前端集成

- **任意前端框架**: Tauri 2 与 React/Vue/Svelte/Solid 完全解耦,只需提供静态资源目录。Pangu Nebula 现有的 React + Vite 前端可直接复用。
- **更好的 IPC 性能**: Tauri Command 通过 WebSocket-like 通道直传,无 HTTP 序列化开销,适合高频调用(如终端流、屏幕流)。

---

## 4. 劣势与挑战

### 4.1 迁移成本巨大

- **后端重写**: 当前 FastAPI 的 200+ 端点(server/api/*.py)需要全部转换为 `#[tauri::command]` 或保留为 Rust HTTP 服务。即使按 `docs/rust-migration-analysis.md` 的"反向移植"策略(仅 5 个安全模块),工作量仍是 4-6 人月。
- **数据库层迁移**: SQLAlchemy ORM 模型(server/db/orm.py)需要映射到 Rust 的 diesel / sea-orm,迁移脚本与 Alembic 历史需要重建。
- **测试重建**: 现有 286 个 pytest 测试需要部分改写为 cargo test(后端) + vitest(前端),覆盖率短期内会下降。
- **依赖替换**: Python 生态的 rich 库(playwright、cryptography、aiosqlite、httpx)需要逐个找 Rust 等价物并验证行为一致性。

### 4.2 团队与技能缺口

- **Rust 经验要求**: Tauri 2 后端必须用 Rust,要求团队具备生产级 Rust 经验。当前团队主要使用 Python,需要 1-2 个月的 Rust 培训期。
- **Tauri 学习曲线**: 即使有 Rust 经验,Tauri 2 的窗口管理、插件系统、capabilities 配置仍需学习。
- **招聘难度**: Rust 开发者供给相对 Python 稀缺,招聘成本高 30-50%。

### 4.3 兼容性风险

- **现有 Python 资产丢失**: pangu_memory_sdk、server/services/*.py 中的业务逻辑(Sponge/BlackHole 引擎、CRDT 同步、E2EE 配对)需要逐个移植,Rust 等价物在短期内难以达到同等成熟度。
- **平台 WebView 差异**: Tauri 2 仍依赖系统 WebView(Windows 7/8 上无 WebView2,需降级),与 PyWebView 面临相同问题。
- **Python 第三方集成断裂**: 飞书/钉钉/企业微信 SDK、PaddleOCR、playwright 等纯 Python 库在 Rust 端没有等价物,需要通过 subprocess 调用 Python 或重写。

### 4.4 开发体验下降(短期内)

- **编译时间**: Rust 的增量编译仍比 Python 解释执行慢 5-10 倍,大型项目冷编译可能 30-60 秒。
- **调试复杂度**: 前后端分离调试,Rust panic 与前端 JS 错误的关联排查更复杂。
- **生态成熟度**: Tauri 2 (2024 年底发布稳定版)的社区文档、Stack Overflow 答案数量仍远少于 Electron / PyWebView。

### 4.5 业务连续性风险

- **回归测试周期**: 全新后端意味着所有用户场景需要重新回归测试,无法复用现有 pytest 套件。
- **数据迁移**: 用户已有的 SQLite 数据库(server/data/*.db)、技能包(server/skills/*.skill)、配置文件需要数据迁移脚本。
- **回退成本**: 一旦迁移到 Tauri 2 后发现问题需要回退,代码与数据迁移的成本极高。

---

## 5. 迁移成本估算

### 5.1 工作量分解

| 工作项 | 估算人月 | 备注 |
|--------|----------|------|
| Rust 后端核心架构搭建(tauri::Builder、状态管理、错误处理) | 1.0 | 含 CI/CD 调整 |
| API 端点迁移(200+ 个,平均每个 0.5 天) | 4.0 | 含输入验证、错误响应格式对齐 |
| 数据库层迁移(SQLAlchemy → sea-orm,30+ 模型) | 1.5 | 含 Alembic 历史迁移 |
| 业务服务迁移(Sponge/BlackHole/CRDT/E2EE 等 50+ 服务) | 3.0 | 复杂算法需重写并验证 |
| 前端 IPC 适配(HTTP fetch → tauri invoke) | 1.0 | 含类型定义生成 |
| 插件集成(fs/dialog/notification/clipboard 等) | 0.5 | |
| 测试重建(cargo test + vitest,覆盖率 ≥70%) | 2.0 | |
| 打包与发布流程(MSI/DMG/AppImage + 自动更新) | 0.5 | 含代码签名 |
| 文档与开发指南更新 | 0.5 | |
| 用户数据迁移工具 | 0.5 | |
| **小计** | **14.5 人月** | 约 1.2 人年 |

### 5.2 时间线假设

- **并行 2 人投入**: 14.5 / 2 = 7.25 月日历时间
- **并行 3 人投入**: 14.5 / 3 ≈ 5 月日历时间(含沟通损耗)
- **乐观估计(仅迁移核心,余下渐进)**: 3 月 MVP + 6 月渐进迁移 = 9 月

### 5.3 与"保持 PyWebView + 渐进引入 Rust"对比

| 方案 | 工作量 | 风险 | 收益 |
|------|--------|------|------|
| **A: 全面迁移到 Tauri 2** | 14.5 人月 | 高(回归测试、数据迁移、技能缺口) | 高(性能、安全、统一栈) |
| **B: 保持 PyWebView,PyO3 调用 Rust** | 3-5 人月(仅 T5.1/T5.2) | 低(渐进、可回退) | 中(性能提升有限,仍受 Python 启动慢制约) |
| **C: 混合方案** — Tauri 2 作前端壳,Python 后端保留为 sidecar | 6-8 人月 | 中(双进程协调复杂,但保留 Python 资产) | 中高(包体减小、启动快,后端渐进迁移) |

---

## 6. 风险分析

### 6.1 高风险

- **R1: 业务连续性中断** — 迁移期间无法发布新功能,用户等待时间长。**缓解**: 采用方案 C(混合),保持 Python 后端 sidecar,Tauri 2 仅做壳,渐进迁移后端。
- **R2: 数据丢失或损坏** — 用户历史数据(记忆库、技能、对话历史)迁移失败。**缓解**: 编写双向迁移脚本,提供回退工具,迁移前强制备份。
- **R3: 平台兼容性回归** — Windows 7/8、旧版 macOS、特定 Linux 发行版可能因 WebView 版本不匹配出现兼容性问题。**缓解**: 提供 Chromium 兜底版本(打包时嵌入),明确支持的最低系统要求。

### 6.2 中风险

- **R4: 性能回退** — Rust 重写初版可能因不熟悉 Rust 异步模式(tokio、async/await)出现性能回退。**缓解**: 引入 Rust 性能基准测试,逐步优化。
- **R5: 团队技能瓶颈** — 单一 Rust 专家离职会导致项目停滞。**缓解**: 至少培养 2 名 Rust 维护者,关键模块结对编程。
- **R6: 第三方库断裂** — 飞书 SDK、PaddleOCR 等纯 Python 库无 Rust 等价物。**缓解**: 通过 PyO3 调用 Python(sidecar 模式),或寻找替代品。

### 6.3 低风险

- **R7: 前端兼容性** — React 前端基本可复用,仅需调整 IPC 调用层。**缓解**: 提供 `@tauri-apps/api` 的 fetch polyfill,前端代码改动 <5%。
- **R8: CI/CD 调整** — GitHub Actions 的 Rust 编译缓存已有成熟方案(swatinem/rust-cache)。**缓解**: 参考 Tauri 官方 CI 模板。

---

## 7. 原型验证说明

> 按任务要求,本评估**不实际进行原型开发**,仅列出验证清单,供未来启动迁移时参考。

### 7.1 必须验证的关键点

1. **窗口与托盘** — Tauri 2 的 `WebviewWindow` + `TrayIconBuilder` 能否覆盖现有的 `pystray` + PyWebView 全部场景(最小化到托盘、右键菜单、单实例锁)。
2. **IPC 性能** — Tauri Command 与现有 HTTP REST 在高频调用(终端流、屏幕流,>1000 msg/s)下的延迟与吞吐对比。
3. **Python sidecar 集成** — Tauri 2 的 `tauri::sidecar` 能否稳定启动 Python 子进程并保持 stdin/stdout 通信(混合方案 C 的关键)。
4. **WebView2 兼容性** — Windows 10 LTSC、Windows 11 SE 等受限系统上 WebView2 的可用性。
5. **打包大小实测** — 实际 `cargo tauri build` 产物的体积,验证 3-10 MB 区间。
6. **自动更新** — `tauri-plugin-updater` 与 GitHub Releases 的集成流程是否顺畅,签名校验是否健壮。

### 7.2 验证通过的标准

- 上述 6 项全部通过;
- 性能基准: 启动时间 <500ms、内存占用 <150MB、IPC 延迟 <2ms(p95);
- 兼容性: 在 Windows 10/11、macOS 12+、Ubuntu 22.04+ 上无回归。

---

## 8. 决策建议

### 8.1 推荐方案: **方案 C(混合)— 短期保留 Python 后端,Tauri 2 作壳渐进迁移**

**理由**:

1. **风险可控**: 保留现有 Python 后端作为 sidecar,所有 286 个 pytest 测试继续生效,业务连续性不受影响。
2. **性能收益立竿见影**: 仅前端壳迁移即可获得包体减小 70%+、启动时间缩短 50%+ 的收益(因为去掉了 PyInstaller 的 Python 解释器打包)。
3. **与阶段5战略协同**: T5.1/T5.2 的 Rust 模块编译完成后,可以直接通过 Tauri Command 调用,无需经过 Python PyO3 桥接。
4. **渐进迁移路径清晰**: 后端按服务优先级逐步从 Python 迁移到 Rust(优先迁移性能敏感的 browser_use、computer_use、memory 服务,最后迁移渠道适配器)。
5. **回退成本低**: 若 Rust 迁移受阻,可随时回到纯 Python + PyWebView 模式,前端 IPC 适配层是唯一需要回退的部分。

### 8.2 不推荐: 方案 A(全面迁移)

**理由**:

- 14.5 人月的工作量在当前团队规模下不现实;
- 业务连续性风险过高,期间无法响应用户需求;
- 测试覆盖率短期下降可能引入隐蔽 bug。

### 8.3 不推荐: 方案 B(纯 PyWebView + PyO3)

**理由**:

- 错过 Tauri 2 在包体、启动时间、自动更新上的显著优势;
- 仍受 PyInstaller 打包体积(80-120 MB)与 Python 启动慢的制约;
- 与 `docs/rust-migration-analysis.md` 中"现在就是回归 Rust 的最佳时机"的判断相悖。

### 8.4 实施路线图(方案 C)

| 阶段 | 时间 | 目标 |
|------|------|------|
| **Phase 0: 准备** | 1 个月 | 团队 Rust 培训、Tauri 2 项目脚手架搭建、CI/CD 调整 |
| **Phase 1: 前端壳迁移** | 2 个月 | Tauri 2 壳 + Python sidecar 启动、IPC 适配层、托盘/窗口管理、自动更新 |
| **Phase 2: 性能敏感模块迁移** | 3 个月 | browser_use、computer_use、memory 服务从 Python 迁移到 Rust |
| **Phase 3: 业务服务迁移** | 4 个月 | CRDT、E2EE、技能市场、对话服务、渠道适配器迁移 |
| **Phase 4: 收尾** | 1 个月 | Python sidecar 完全移除、测试覆盖率达到 80%+、文档更新 |

**总计**: 约 11 个月(1 人月 8 小时/天 × 2 人并行)

### 8.5 触发条件

启动 Phase 1 的触发条件:
- T5.1/T5.2 的 Rust 模块至少有一个完成编译并通过 cargo test;
- 团队中至少 2 名开发者完成 Rust 入门培训(《Rust Programming Language》前 15 章 + 《Async Rust》);
- 用户反馈显示包体大小或启动时间成为分发痛点(定量指标: 用户首次启动放弃率 >5%)。

---

## 9. 总结

### 9.1 关键发现

1. **Tauri 2 在性能、安全、分发上显著优于 PyWebView**,包体减小 90%、启动时间缩短 70%、内存占用降低 50%。
2. **全面迁移成本高昂** — 14.5 人月,业务连续性风险高,不推荐一次性迁移。
3. **混合方案(方案 C)是最优解** — Tauri 2 作前端壳 + Python 后端 sidecar,性能收益立竿见影,后端渐进迁移风险可控。
4. **与 Rust 重写战略协同** — 阶段5的 Rust 模块骨架(T5.1/T5.2)已经为 Tauri 迁移铺平道路。
5. **团队技能是最大瓶颈** — Rust 经验需要 1-2 个月培训期,招聘成本高 30-50%。

### 9.2 决策

**决策: 推荐方案 C(混合),但暂不启动**

- **不立即启动**: 当前 v2.0.0 阶段5的优先级是完成 Rust 模块骨架与技能联邦(T5.1-T5.8),桌面壳迁移应作为 v2.1.0 的候选议题。
- **启动时机**: 当 T5.1/T5.2 的 Rust 模块编译完成并通过测试,且团队完成 Rust 培训后,启动 Phase 1。
- **保留评估**: 每季度复审本报告,根据 Tauri 2 生态成熟度与团队 Rust 能力调整决策。

### 9.3 后续行动

- [ ] 将本评估报告纳入 v2.1.0 路线图讨论
- [ ] 安排团队 Rust 培训(2 名开发者,1-2 个月)
- [ ] 跟踪 T5.1/T5.2 Rust 模块编译进度,作为启动触发条件
- [ ] 收集用户对包体大小与启动时间的反馈,作为决策依据
- [ ] 复审 docs/rust-migration-analysis.md 中的"反向移植"策略,与本报告方案 C 对齐

---

## 附录 A: 参考资料

- Tauri 2 官方文档: https://v2.tauri.app/
- Tauri 2 GitHub: https://github.com/tauri-apps/tauri
- PyWebView 文档: https://pywebview.flowrl.com/
- Pangu Nebula Rust 迁移分析: `docs/rust-migration-analysis.md`
- Pangu Nebula 阶段5任务清单: `docs/tasks.md`

## 附录 B: 术语表

| 术语 | 含义 |
|------|------|
| **桌面壳** | 包装 Web 前端并提供原生窗口、托盘、文件系统访问等系统能力的容器 |
| **Sidecar** | 与主进程并行运行的辅助进程(此处指 Tauri 2 启动的 Python 子进程) |
| **IPC** | Inter-Process Communication,进程间通信 |
| **Capabilities** | Tauri 2 的权限声明系统,显式列出前端可调用的命令与资源 |
| **PyO3** | Python ↔ Rust 互操作库,让 Rust 代码可作为 Python 模块加载 |
| **MVP** | Minimum Viable Product,最小可行产品 |
