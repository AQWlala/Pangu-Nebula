# Changelog

All notable changes to Pangu Nebula will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No changes yet. Next version will be v0.2.0 — see [fix-iteration-plan.md](./docs/fix-iteration-plan.md)._

## [1.1.0] - 2026-07-12 — 修复迭代版本

修复迭代版本。在 v0.1.0 初始架构基础上完成打包、路径与兼容性修复,使桌面应用可在 Windows 上独立启动并稳定运行。

### Added

- **DPAPI keychain**: Windows DPAPI 保护的 master key + AES-256-GCM 加密的凭据存储 (`server/services/keychain.py`)
- **CORS 加固**: 默认仅允许本机回环地址,支持通过环境变量配置可信来源
- **core/ 公共 API 层**: 新增 `server/core/` 作为对外稳定 API 的统一再导出层,隔离内部实现变更
- **mypy 类型检查**: 接入 mypy 静态类型检查,覆盖 `server/services`、`server/db`、`server/api`、`server/providers`、`server/tools`,配置见 `pyproject.toml`

### Fixed

- **`console=False` 崩溃**: 修复 PyInstaller 打包后 GUI 子系统 (`console=False`) 启动时因 stdout/stderr 缓冲与 traceback 写入失败导致的崩溃
- **数据库路径绝对化**: 将 SQLite 数据库路径统一转换为绝对路径,修复 PyInstaller onedir 模式下相对路径导致的写入失败
- **前端资源路径**: 修复 PyWebView 在打包后无法定位 `frontend/dist` 静态资源的问题,通过 `sys._MEIPASS` 正确解析资源根目录
- **pywebview 6.x 兼容**: 适配 pywebview 6.x 的 API 变更,包括窗口创建参数与 JavaScript 桥接接口

### Removed

- 废弃的 `server/db/models.py` (已被 `server/db/orm.py` 替代)
- 废弃的 `server/db/connection.py` (已被 `server/db/engine.py` 替代)
- 废弃的 `server/alembic/` 目录 (迁移系统推迟至 v1.0.0,当前使用 SQLite 自动建表)

## [0.1.0] - 2026-07-11 — 初始发布

首个公开版本。完成全部 11 个 Phase,奠定 Pangu Nebula 的认知运行时架构基础。

### Added

- **6 层记忆图谱**: L0 工作记忆 → L5 元认知,含双向链接、FTS5 全文检索、海绵/黑洞双引擎
- **蜂群编排**: 任务分解、2-5 worker 并行推理、校验器多数共识、失败重试与异议保留
- **自进化闭环**: 反思 → 策略规划 → 执行 → 技能蒸馏,4 阶段迭代改进
- **技能市场**: Markdown frontmatter 技能定义、变量替换、沙箱执行、导入导出
- **统一 LLM 适配器**: OpenAI / Anthropic / Gemini 三大 provider 统一接口
- **多渠道接入**: 飞书、微信 IM 渠道适配器
- **CRDT 跨设备同步**: LWW-Register + OR-Set 冲突无关同步,E2EE 加密传输
- **11 项安全措施**: DPAPI、AES-256-GCM、ACL、注入防护、SSRF 防护、沙箱、审计日志、密钥轮换、OAuth 2.0、DID、数据脱敏、E2EE
- **193+ API 端点**: 覆盖记忆、蜂群、技能、Provider、调度、同步、多模态、审计等 24 个路由模块
- **14 前端组件**: Preact + TypeScript + Tailwind CSS 单页应用,含仪表盘、记忆图、蜂群进度、技能市场、知识库浏览器等
- **桌面应用**: PyWebView 原生窗口 + PyInstaller onedir 打包
- **CI/CD**: GitHub Actions (ci.yml / release.yml / pages.yml / security.yml)
- **16 单元测试**: 覆盖核心服务 (memory / sponge / blackhole / compact / main / performance)

[Unreleased]: https://github.com/AQWlala/Pangu-Nebula/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/AQWlala/Pangu-Nebula/releases/tag/v1.1.0
[0.1.0]: https://github.com/AQWlala/Pangu-Nebula/releases/tag/v0.1.0
