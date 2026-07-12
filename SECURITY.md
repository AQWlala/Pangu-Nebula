# Security Policy

Pangu Nebula 是一个全本地运行的多 Agent 认知运行时。安全是核心设计原则之一 — 用户的记忆、凭据与对话数据全部留在本地,不上传任何第三方服务。

本文档说明已实施的安全措施、漏洞披露流程与最佳实践建议。

---

## 一、已实施的安全措施

Pangu Nebula 实施了 11 项安全措施,覆盖凭据存储、访问控制、输入校验、执行隔离与审计追踪。

| # | 措施 | 模块 | 说明 |
|:---:|---|---|---|
| 1 | **DPAPI 凭据保护** | `server/services/keychain.py` | Windows DPAPI 保护 master key,防止离线提取 |
| 2 | **AES-256-GCM 加密存储** | `server/services/keychain.py` | 所有 API key / token 以 AES-256-GCM 加密落盘,带认证标签防篡改 |
| 3 | **ACL 访问控制** | `server/services/acl_service.py` | 资源级访问控制规则,限制 agent 对敏感资源的读写 |
| 4 | **注入防护** | `server/services/injection_guard.py` | Prompt 注入模式检测,拦截越权指令与提示词逃逸 |
| 5 | **SSRF 防护** | `server/services/ssrf_guard.py` | 出站 HTTP 请求校验,拦截内网地址 (127.0.0.1 / 10.x / 169.254.x / metadata endpoint) |
| 6 | **沙箱执行** | `server/services/sandbox_engine.py` | 隔离的 Python 代码执行,带超时与内存限制,防止恶意代码逃逸 |
| 7 | **审计日志** | `server/services/audit_logger.py` | 全操作审计追踪,记录关键资源访问与安全事件 |
| 8 | **密钥轮换** | `server/services/key_rotation.py` | 自动化加密密钥轮换,降低密钥泄露影响 |
| 9 | **OAuth 2.0** | `server/services/oauth_service.py` | 标准化第三方身份授权,支持授权码流程 |
| 10 | **DID 去中心化身份** | `server/services/did_service.py` | 基于 W3C DID 规范的去中心化身份标识,用于设备配对与跨实例认证 |
| 11 | **数据脱敏 + E2EE** | `server/services/redactor.py` `server/services/sync_crypto.py` | 敏感数据脱敏 (日志/审计前) + 跨设备同步端到端加密 (E2EE),服务器零知识 |

### 安全相关的 CI 自动扫描

`.github/workflows/security.yml` 配置了三层自动扫描:

| 扫描 | 工具 | 频率 |
|---|---|---|
| Python 依赖漏洞 | `pip-audit --strict` | 每次 push (requirements.txt 变更) + 每周一定时 |
| Node 依赖漏洞 | `npm audit --audit-level=high` | 每次 push (package.json 变更) + 每周一定时 |
| 代码安全分析 | GitHub CodeQL (Python + JavaScript) | 每次 push + PR |

---

## 二、支持版本范围

| 版本 | 状态 | 支持安全修复 |
|---|---|:---:|
| v1.1.x | ✅ 当前支持 | 是 |
| v0.1.0 | ⚠️ 初始版本 | 否 (请升级到 v1.1.0+) |
| < v0.1.0 | ❌ 不支持 | 否 |

> 仅对当前发布分支提供安全修复。新版本发布后,前一个版本仅在最严重漏洞 (CVSS ≥ 9.0) 情况下提供 30 天过渡期修复。

---

## 三、漏洞披露流程

### 3.1 报告渠道

| 场景 | 渠道 | 说明 |
|---|---|---|
| **私密披露 (推荐)** | [GitHub Security Advisory](https://github.com/AQWlala/Pangu-Nebula/security/advisories/new) | 私密协作修复,披露前不公开 |
| **公开问题** | [GitHub Issues](https://github.com/AQWlala/Pangu-Nebula/issues) | 仅用于非敏感的安全增强建议 |

> **请勿在公开 Issue、PR、社交媒体讨论疑似漏洞。** 私密披露让我们能在攻击者知晓前修复。

### 3.2 报告内容

为加快响应,请提供:

1. **漏洞描述**: 什么问题、影响范围
2. **复现步骤**: 最小可复现示例 (PoC)
3. **影响版本**: 受影响的版本号
4. **严重程度评估**: CVSS 评分或定性描述 (低/中/高/严重)
5. **建议修复方案**: 如有 (可选)

### 3.3 响应时间

| 阶段 | 目标时间 |
|---|---|
| 确认收到报告 | 48 小时内 |
| 初步评估与严重程度判定 | 7 天内 |
| 修复发布 (严重, CVSS ≥ 9.0) | 30 天内 |
| 修复发布 (高, CVSS 7.0-8.9) | 60 天内 |
| 修复发布 (中/低) | 下一个常规版本 |

### 3.4 披露政策

- 修复发布后,会发布 Security Advisory 公开披露漏洞详情
- 报告者会在发布前 7 天收到预览,可选择署名致谢
- 我们支持负责任的披露,不会对善意报告者采取法律行动

---

## 四、安全联系方式

| 用途 | 联系方式 |
|---|---|
| 私密漏洞披露 | [GitHub Security Advisory](https://github.com/AQWlala/Pangu-Nebula/security/advisories/new) |
| 公开安全讨论 | [GitHub Issues](https://github.com/AQWlala/Pangu-Nebula/issues) (标签 `security`) |
| 通用问题 | [GitHub Issues](https://github.com/AQWlala/Pangu-Nebula/issues) |

> 当前无独立安全邮箱,所有安全沟通通过 GitHub Security Advisory 进行,确保全程可审计。

---

## 五、最佳实践建议

### 5.1 部署配置

```bash
# 1. 配置环境变量 (勿硬编码到代码或提交到 git)
# 复制 .env.example 为 .env 并填写
cp .env.example .env

# 关键环境变量:
# - NEBULA_LLM_API_KEY: LLM provider API key (将被 DPAPI + AES-256-GCM 加密存储)
# - NEBULA_MASTER_KEY: (可选) 自定义 master key,未设置则运行时生成
# - NEBULA_CORS_ORIGINS: 可信来源,生产环境务必限定具体域名
```

### 5.2 密钥管理

- **定期轮换密钥**: 通过 `/security/rotate-key` API 定期轮换加密密钥 (建议每 90 天)
- **勿共享 API key**: 每个 agent 实例使用独立凭据
- **DPAPI 优先**: Windows 环境确保使用 DPAPI 保护 (默认开启)
- **备份 master key**: 若配置了自定义 `NEBULA_MASTER_KEY`,务必安全备份,丢失将导致所有加密凭据不可恢复

### 5.3 网络与同步

- **启用 E2EE 同步**: 跨设备同步务必启用 E2EE,确保同步服务器零知识
- **限制 CORS**: 生产环境通过 `NEBULA_CORS_ORIGINS` 限定可信来源,勿使用 `*`
- **SSRF 防护**: 保持 `ssrf_guard` 开启,agent 出站请求会自动拦截内网地址
- **审计日志**: 保持审计日志开启,定期检查异常访问

### 5.4 沙箱与代码执行

- **技能沙箱**: 用户自定义技能的 Python 代码在沙箱内执行,带超时与内存限制
- **勿禁用沙箱**: 除非完全信任技能来源,否则勿通过配置禁用沙箱
- **技能来源**: 仅从可信来源导入技能,未知技能先在隔离环境测试

### 5.5 数据保护

- **数据脱敏**: 审计日志与调试输出会自动脱敏,勿手动关闭
- **本地优先**: Pangu Nebula 设计为全本地运行,数据不离开你的设备
- **同步谨慎**: 仅在可信网络环境下启用跨设备同步

---

## 六、已知限制

- **Windows 优先**: 当前 DPAPI 保护仅在 Windows 完整支持,macOS/Linux 使用 0600 文件权限 (v1.0.0 将补齐跨平台)
- **无多用户隔离**: 当前为单用户桌面应用,不支持多租户场景
- **无网络层加密**: 本地 HTTP 服务监听 127.0.0.1,不提供 TLS (假设本机环境可信)

---

## 七、致谢

感谢以下安全研究员负责任地披露漏洞 (如有):

_暂无_

如你发现了安全问题并希望被致谢,请在 Security Advisory 中说明。
