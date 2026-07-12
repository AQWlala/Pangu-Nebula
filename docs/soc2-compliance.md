# SOC 2 Type II 合规文档

> 本文档描述 Pangu Nebula 项目为满足 AICPA SOC 2 Type II Trust Services Criteria
> （Security / Availability / Processing Integrity / Confidentiality / Privacy）
> 所建立的安全控制清单、审计日志规范、访问控制矩阵、数据加密方案以及漏洞管理流程。
>
> 适用范围: server/ 后端服务、前端 Web UI、本地运行时（Windows/Linux/macOS）以及
> 由此派生的桌面打包版本。

---

## 1. 安全控制清单

下表列出 Pangu Nebula 实施的 11 项安全控制，每项包含控制描述、实现方式与验证方法。
控制编号对应 SOC 2 Trust Services Criteria (CC = Common Criteria)。

| # | 控制项 | 控制描述 | 实现方式 | 验证方法 |
|---|--------|----------|----------|----------|
| CC1.1 | 访问控制 (ACL) | 基于角色的访问控制限制对资源（memory / skill / wiki / chat）的访问 | `server/services/acl_service.py` 实现 persona×resource×action×effect 四元组规则，存入 SQLite | `GET /security/acl/rules` 列出规则；`POST /security/acl/check` 校验权限；测试 `tests/test_acl_*` |
| CC1.2 | 注入防护 | 防止 Prompt Injection、SQL Injection、XSS 等注入攻击 | `server/services/injection_guard.py` 检测并清洗输入；`POST /security/injection/check` 与 `clean` 端点 | 单元测试覆盖正/负样本；端到端通过 `/security/injection/check` |
| CC1.3 | SSRF 防护 | 阻止对内网/元数据服务的请求 | `server/services/ssrf_guard.py` 解析 URL，拒绝 127.0.0.1 / 10.0.0.0/8 / 169.254.169.254 等 | 单元测试 `test_ssrf_blocked_*`；通过 `/security/ssrf/check` 验证 |
| CC2.1 | 密钥管理 | 主密钥 + 数据密钥双层加密，密钥与密文分离存储 | `server/services/keychain.py` 使用 AES-256-GCM；Windows 上由 DPAPI 保护主密钥，Linux 上由 0600 权限保护 | `keychain.is_available()` 返回状态；`/security/keychain` 端点列出/存储/获取/删除密钥 |
| CC2.2 | 密钥轮换 | 周期性轮换数据加密密钥，旧密钥归档可解密历史数据 | `server/services/key_rotation.py` 实现轮换与历史记录；`EncryptionKey.is_active` 标记当前密钥 | `/security/key-rotation/history` 查看历史；`POST /security/key-rotation` 触发轮换 |
| CC3.1 | 国密算法支持 | 适配信创市场，提供 SM2 / SM4 算法（无依赖时降级为 mock） | `server/services/national_crypto.py` 双模式实现；自动检测 gmssl 库 | `GET /security/national-crypto/status` 查看模式；`tests/test_security_extensions.py::test_sm*` |
| CC4.1 | DLP 数据防泄漏 | 自动识别敏感数据（身份证 / 手机 / 银行卡 / 邮箱 / IP / API Key / 密码）并按策略脱敏 | `server/services/dlp_engine.py` 提供扫描 / 脱敏 / 分级 / 审计；`server/services/redactor.py` 提供基础脱敏 | `POST /security/dlp/scan|mask|classify`；`GET /security/dlp/audit-log` |
| CC5.1 | DID 去中心化身份 | 通过 W3C did:key 方法实现 Ed25519 签名/验签，用于 Agent 身份认证 | `server/services/did_service.py` 生成密钥对、构建 did:key:z6Mk...、签名验证 | `/did` 系列端点；测试覆盖 create/sign/verify 流程 |
| CC6.1 | 审计日志 | 记录所有关键操作（API 调用、密钥访问、DLP 脱敏、密钥轮换） | `server/services/audit_logger.py` 持久化到 DB；DLP 引擎在内存中维护最近 100 条 | `GET /audit/logs`；`GET /security/dlp/audit-log` |
| CC7.1 | 传输加密 | 所有 API 通信在 localhost 回环；远程访问建议走 TLS 反向代理 | FastAPI 监听 127.0.0.1；CORS 配置 `server/main.py`；生产部署建议 nginx + TLS | `tests/test_main.py::test_cors_headers` 验证 CORS |
| CC8.1 | 漏洞管理 | 定期扫描依赖、修复 SLA、安全披露渠道 | GitHub Actions `security.yml` 工作流；`SECURITY.md` 披露政策；`requirements.txt` 锁定版本 | CI 通过；`SECURITY.md` 公开披露邮箱 |

---

## 2. 审计日志规范

### 2.1 日志格式

所有审计日志条目均为 JSON 对象，统一通过 `server/services/audit_logger.py` 写入
`AuditLog` 表（参见 `server/db/orm.py`）。

通用字段（适用于 `/audit/logs`）：

```json
{
  "id": 123,
  "persona_id": 1,
  "action": "keychain.get",
  "resource": "openai_api_key",
  "input_summary": "...",
  "output_summary": "...",
  "token_count": 0,
  "cost": 0.0,
  "duration_ms": 12,
  "success": true,
  "details": {},
  "created_at": "2026-07-12T08:30:00Z"
}
```

DLP 引擎专属字段（适用于 `/security/dlp/audit-log`，仅在内存中保留最近 100 条）：

```json
{
  "timestamp": "2026-07-12T08:30:00Z",
  "action": "mask",
  "input_length": 24,
  "output_length": 24,
  "total_redactions": 1,
  "affected_types": ["phone"]
}
```

### 2.2 保留期

| 日志类别 | 存储位置 | 保留期 | 备注 |
|----------|----------|--------|------|
| API 审计日志 | SQLite `audit_log` 表 | 365 天 | 由 ACL 控制访问；超期由清理任务归档 |
| DLP 脱敏审计 | 内存 | 进程生命周期 | 重启后清空；如需长期保留请订阅 `/security/dlp/audit-log` 转存到外部 SIEM |
| 密钥轮换历史 | SQLite `encryption_keys` 表 | 永久 | 包含历史密钥以便解密旧密文；停用密钥 `is_active=False` 但不删除 |
| 应用运行日志 | stdout / 文件 | 30 天 | 由部署环境的日志轮转策略管理 |

### 2.3 访问控制

- 所有审计日志端点受 ACL 限制，默认仅 `admin` 角色可读
- 日志中**绝不**记录密钥明文、密码原文、敏感数据原文；DLP 脱敏日志只记录长度与命中类型，不记录原文
- 调用 `keychain.get` 时，`input_summary` 与 `output_summary` 字段会被 `redactor` 自动脱敏

---

## 3. 访问控制矩阵

### 3.1 角色定义

| 角色 | 标识 | 说明 |
|------|------|------|
| Owner | `owner` | Persona 拥有者，对自有资源拥有全部权限 |
| Admin | `admin` | 系统管理员，可管理 ACL 规则、密钥、审计日志 |
| Agent | `agent` | AI 智能体，受 Persona 委托执行任务 |
| Viewer | `viewer` | 只读访客 |

### 3.2 资源权限矩阵

| 资源 | 动作 | Owner | Admin | Agent | Viewer |
|------|------|-------|-------|-------|--------|
| `memory/*` | read | ✅ | ✅ | ✅ (委派) | ❌ |
| `memory/*` | write | ✅ | ✅ | ✅ (委派) | ❌ |
| `skill/*` | read | ✅ | ✅ | ✅ | ✅ |
| `skill/*` | write | ✅ | ✅ | ❌ | ❌ |
| `skill/*` | execute | ✅ | ✅ | ✅ (委派) | ❌ |
| `wiki/*` | read | ✅ | ✅ | ✅ | ✅ |
| `wiki/*` | write | ✅ | ✅ | ✅ (经 review) | ❌ |
| `chat/*` | read | ✅ | ✅ | ✅ | ❌ |
| `chat/*` | write | ✅ | ✅ | ✅ | ❌ |
| `security/acl/*` | manage | ❌ | ✅ | ❌ | ❌ |
| `security/keychain/*` | manage | ❌ | ✅ | ❌ | ❌ |
| `security/dlp/*` | invoke | ✅ | ✅ | ✅ | ❌ |
| `audit/logs` | read | ❌ | ✅ | ❌ | ❌ |

### 3.3 实现说明

- ACL 规则通过 `POST /security/acl/rules` 创建，规则四元组为 `(persona_id, resource, action, effect)`
- `effect` 取值 `allow` 或 `deny`，`deny` 优先级高于 `allow`
- `resource` 支持通配符：`memory/*` 匹配 `memory/123`、`memory/456/notes` 等
- `action` 支持通配符 `*`，表示匹配所有动作
- 未匹配任何规则时默认 `deny`

---

## 4. 数据加密

### 4.1 传输加密

| 通道 | 加密方式 | 说明 |
|------|----------|------|
| 浏览器 ↔ 后端 (本地) | HTTP over localhost | 默认监听 127.0.0.1:7860，不出本机回环 |
| 浏览器 ↔ 后端 (远程) | TLS 1.2+ | 生产部署通过 nginx/Caddy 反向代理启用 HTTPS，强制 HSTS |
| 后端 ↔ LLM API | TLS 1.2+ | 调用 OpenAI / Anthropic 等均通过 HTTPS |
| 设备间同步 (P2P) | E2EE | `server/services/sync_crypto.py` 基于 X25519 + ChaCha20-Poly1305 端到端加密 |

### 4.2 存储加密

| 数据类型 | 加密算法 | 密钥来源 | 实现位置 |
|----------|----------|----------|----------|
| 密钥库 (keychain) | AES-256-GCM | 主密钥 → DPAPI / 文件 0600；数据密钥存 DB | `services/keychain.py` |
| 主密钥 (Windows) | DPAPI | 绑定用户账户 | `CryptProtectData` |
| 主密钥 (Linux/macOS) | 文件权限 0600 + base64 | `data/.master_key` | `os.chmod` |
| DID 私钥 | base64 编码存储 (简化) | Ed25519 私钥 | `services/did_service.py` |
| 数据库 | SQLite | 文件权限 | `data/nebula.db` |
| 国密 (信创可选) | SM2 / SM4 | gmssl 库；无依赖时 mock | `services/national_crypto.py` |

### 4.3 密钥管理

1. **主密钥生成**：首次启动时通过 `secrets.token_bytes(32)` 生成 256 位随机密钥
2. **主密钥存储**：
   - Windows: `CryptProtectData` 加密后写入 `data/.master_key`
   - Linux/macOS: base64 编码后写入 `data/.master_key`，权限 0600
   - 环境变量 `NEBULA_MASTER_KEY` 优先级最高（便于 CI/CD 注入）
3. **数据密钥**：每个加密值绑定一个 `key_id`，数据密钥本身用主密钥加密后存入 `EncryptionKey` 表
4. **密钥轮换**：`POST /security/key-rotation` 创建新数据密钥并标记为 active；旧密钥保留用于解密历史数据
5. **密钥访问**：所有 `keychain.get` 调用均写入审计日志

---

## 5. 漏洞管理

### 5.1 扫描频率

| 扫描类型 | 频率 | 工具 | 负责人 |
|----------|------|------|--------|
| 依赖漏洞扫描 | 每次 PR + 每日定时 | GitHub Dependabot + `pip-audit` | 维护团队 |
| 容器镜像扫描 | 每次发布 | Trivy (GitHub Actions `security.yml`) | 维护团队 |
| SAST 静态扫描 | 每次 PR | GitHub CodeQL | 维护团队 |
| 密钥泄漏扫描 | 每次 PR | GitLeaks | 维护团队 |
| 渗透测试 | 每年 1 次 | 第三方安全公司 | 安全负责人 |

### 5.2 修复 SLA

根据 CVSS v3.1 评分分级修复：

| 严重程度 | CVSS 评分 | 修复 SLA | 临时缓解 |
|----------|-----------|----------|----------|
| Critical | 9.0 - 10.0 | 24 小时内 | 立即停用受影响组件 |
| High | 7.0 - 8.9 | 7 天内 | 限制访问范围 |
| Medium | 4.0 - 6.9 | 30 天内 | 监控 + 审计 |
| Low | 0.1 - 3.9 | 下一次发布 | 记录跟踪 |

### 5.3 披露政策

- **披露渠道**: 见 `SECURITY.md`，通过私有邮箱披露，不通过公开 Issue
- **响应时间**: 收到报告后 48 小时内确认，5 个工作日内提供初步评估
- **修复通知**: 修复后在 `CHANGELOG.md` 与 GitHub Security Advisories 中公告
- **致谢**: 在征得报告人同意后在安全公告中致谢
- **赏金**: 目前无现金赏金计划，但会致谢并优先回应

### 5.4 应急响应流程

1. **发现**: 通过扫描、用户报告或审计日志异常发现漏洞
2. **评估**: 安全负责人评估严重程度与影响范围
3. **缓解**: 立即实施临时缓解措施（如禁用功能、限流、回滚）
4. **修复**: 开发修复补丁，按 SLA 发布
5. **通知**: 通过 GitHub Security Advisory 通知用户
6. **复盘**: 事后编写事件报告，更新控制清单

---

## 6. 合规映射

| SOC 2 Criteria | 本文档章节 | 关键控制 |
|----------------|------------|----------|
| CC1 (Control Environment) | §1 CC1.1, CC1.2, CC1.3 | ACL / 注入防护 / SSRF |
| CC2 (Communication) | §2 | 审计日志 |
| CC3 (Risk Assessment) | §5 | 漏洞管理 |
| CC4 (Monitoring) | §2, §5.1 | 审计日志 / 漏洞扫描 |
| CC5 (Control Activities) | §1 CC2.1, CC2.2, CC3.1 | 密钥管理 / 国密 |
| CC6 (Logical Access) | §3, §4 | 访问控制矩阵 / 加密 |
| CC7 (System Operations) | §4, §5.2 | 数据加密 / 修复 SLA |
| CC8 (Change Management) | §5.1 | CI/CD 安全扫描 |
| CC9 (Risk Mitigation) | §5.4 | 应急响应 |
| Confidentiality | §4 | 数据加密 |
| Privacy | §3 | ACL / DLP |

---

## 7. 文档维护

- **更新频率**: 每季度审查一次，重大架构变更后立即更新
- **负责人**: 安全负责人
- **审查记录**: 每次更新在 Git 提交信息中记录审查人、日期、变更摘要
- **保留期**: 历史版本永久保留在 Git 历史中

---

*最后更新: 2026-07-12*
