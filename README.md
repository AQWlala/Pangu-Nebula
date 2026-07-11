<div align="center">

# 🌌 Pangu Nebula

### 你的第二大脑,不该租给别人

**本地优先 · 多模型自选 · 蜂群协作 · 数据主权**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Preact](https://img.shields.io/badge/Preact-10.19+-673AB8?logo=preact&logoColor=white)](https://preactjs.com)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-19%20passed-brightgreen)]()
[![Phases](https://img.shields.io/badge/Phases-11%2F11%20DONE-success)]()

</div>

---

> **别把第二大脑租给别人——你的思考,不该成为别人的养料。**

Pangu Nebula(盘古星云)是一个 100% 本地运行的 AI 智能体平台。你的记忆、你的角色、你的数据,全部存在你自己的机器上。不依赖云端,不被迫共享,不被算法投喂。

10 家大模型随你切换,3 个自定义 AI 角色懂你的风格,蜂群协作并行处理复杂任务,6 层记忆图谱让 AI 真正"记住"你的一切。

---

## ✨ 为什么选择 Pangu Nebula?

### 🔒 数据主权,天经地义

你的对话记录、记忆图谱、角色设定,全部存储在本地 SQLite 数据库。没有云端同步,没有数据上传,没有"我们改进服务"的借口。**你的思考,只属于你。**

- E2EE 端到端加密(X25519 + AES-256-GCM)
- DID 去中心化身份(did:key + Ed25519)
- ACL 权限控制 + 注入防护 + SSRF 防护
- 屏幕感知默认关闭,截图永不存储

### 🧠 6 层记忆,真正的第二大脑

不是简单的聊天记录,而是结构化的知识图谱:

| 层级 | 用途 |
|------|------|
| L0 工作记忆 | 当前对话上下文 |
| L1 事件记忆 | 近期交互记录 |
| L2 情节记忆 | 完整对话历史 |
| L3 语义记忆 | 提炼后的知识点 |
| L4 程序记忆 | 技能与模板 |
| L5 元认知 | 自我反思与进化 |

支持 Obsidian 式 `[[双向链接]]`、图谱可视化、海绵吸收引擎(自动摄入)、黑洞压缩引擎(智能精简)。

### 🎭 3 个自定义角色,AI 也有性格

创建属于你的 AI 角色:给它起名、设定性格、用 AI 辅助生成 SOUL.md 灵魂文件。切换角色,对话风格立刻变化。

- 编程助手:简洁高效,直击要害
- 写作伙伴:文采飞扬,引经据典
- 项目顾问:逻辑严密,步步为营

### 🐝 蜂群协作,复杂任务并行处理

一个任务,2-5 个 Worker 并行执行,结果互相验证,少数服从多数。

```
你的需求
  ↓
主智能体理解 → 拆解子任务
  ↓
Worker 1 ─┐
Worker 2 ─┼─→ 结果互验 → 汇总输出
Worker 3 ─┘
```

不是单线程等待,而是真正的多 Agent 协作。

### 🔌 10 家大模型,你选不我选

| 国内 | 国外 | 本地 | 云推理 |
|------|------|------|--------|
| 通义千问 | OpenAI | Ollama | NVIDIA NIM |
| 文心一言 | Anthropic | DeepSeek | |
| 智谱 GLM | | | |
| Kimi | | | |
| 豆包 | | | |
| 混元 | | | |

**无默认 Provider,无强制选择。** 你的模型,你做主。

### 🎨 暖色调迪士尼风格,治愈系桌面伴侣

三色系随心切换:温暖橙 / 柔柔粉 / 奶油米白。右下角常驻卡通云朵助理,会眨眼、会呼吸、任务完成会庆祝。不是冷冰冰的工具,而是有温度的伙伴。

macOS 风格窗口(红黄绿交通灯 + 毛玻璃模糊),原生桌面体验。

---

## 🚀 30 秒快速开始

### 方式一:开箱即用(打包版)

```bash
# 下载 dist/PanguNebula/PanguNebula.exe
# 双击运行,无需安装 Python
```

### 方式二:开发者模式

```bash
# 1. 克隆仓库
git clone git@github.com:AQWlala/Pangu-Nebula.git
cd Pangu-Nebula

# 2. 安装后端依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 3. 构建前端
cd frontend && npm install && npm run build && cd ..

# 4. 启动桌面应用
python launch.py

# 或开发模式(前后端热重载)
python scripts/dev.py
```

### CLI 参数

```bash
python launch.py --version              # 查看版本
python launch.py --port 8080            # 指定端口
python launch.py --no-window            # 仅后端模式
python scripts/dev.py --backend-port 9000   # 开发模式自定义端口
python scripts/build.py --skip-tests    # 构建跳过测试
```

---

## 📦 功能全景

### 核心引擎

| 模块 | 能力 | 端点数 |
|------|------|--------|
| 🧠 记忆系统 | 6 层存储 + 双向链接 + 图谱 + 海绵/黑洞双引擎 | 8 |
| 🐝 蜂群编排 | A-O-W 模式 + 多 Agent 互验 + SSE 实时流 | 7 |
| 🎭 角色管理 | CRUD + AI 辅助 SOUL.md + 热切换 | 6 |
| ⚡ 技能生态 | 市场 + 沙箱 + 自进化蒸馏 + 导入导出 | 14 |
| 📚 Wiki 编译 | 对话自动生成笔记 + 安全写回 + 手动编辑 | 7 |
| 🌱 进化引擎 | 4 阶段管道(反思→规划→执行→整合) | 5 |
| 🔄 Loop 循环 | 多轮迭代 + 预算控制 + 审计日志 | 7 |
| 💰 预算审计 | Token/时间/金额三维度 + 超限降级 | 10 |

### 感知与交互

| 模块 | 能力 |
|------|------|
| 🖼️ 多模态 | 图片理解 + 语音输入(ASR) + 语音输出(TTS) + 视频分析 |
| 🖥️ OS 感知 | 剪贴板监控 + 文件夹监控 + 系统托盘 + 屏幕感知(可开关) |
| 🌐 浏览器自动化 | Playwright Python 驱动 |
| 📡 IM 渠道 | 微信桥接 + 飞书 Webhook |

### 安全与身份

| 模块 | 能力 |
|------|------|
| 🔐 E2EE 加密 | X25519 密钥交换 + HKDF + AES-256-GCM |
| 🛡️ ACL 权限 | fnmatch 规则 + deny 优先 |
| 💉 注入防护 | 52 种模式检测 |
| 🌐 SSRF 防护 | ipaddress 白名单 |
| 🔑 密钥轮换 | 90 天自动提醒 |
| OAuth | Gmail / GitHub / Notion / Slack(PKCE) |
| DID | did:key + Ed25519 去中心化身份 |

### 同步与调度

| 模块 | 能力 |
|------|------|
| 🔄 多设备同步 | CRDT(LWW+ORSet+RGA) + E2EE + 配对码/QR |
| 🔧 MCP 协议 | JSON-RPC 2.0 over stdio,客户端+服务端 |
| ⏰ 定时任务 | APScheduler + 5-field cron + 4 种 action |
| 💓 健康检查 | Provider 监控 + 自动降级(3 失败→degraded) |

**总计:193+ API 端点,27 个路由模块**

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   Pangu Nebula                        │
├──────────────┬──────────────────────────────────────┤
│   前端 UI     │  Preact + TypeScript + TailwindCSS   │
│  (14 组件)    │  三色系 + macOS 风格 + 卡通助理       │
├──────────────┼──────────────────────────────────────┤
│   后端 API    │  FastAPI + uvicorn + SQLAlchemy 2.0  │
│ (193+ 端点)   │  27 路由模块 + Pydantic 模型         │
├──────────────┼──────────────────────────────────────┤
│   数据层      │  SQLite(aiosqlite) + FTS5 全文搜索   │
│              │  无 ChromaDB 依赖,纯 Python          │
├──────────────┼──────────────────────────────────────┤
│   桌面壳      │  PyWebView(原生窗口)                │
│              │  PyInstaller 打包(11.87MB exe)      │
└──────────────┴──────────────────────────────────────┘
```

### 三项目融合基因

| 来源 | 贡献 |
|------|------|
| **Nebula**(原项目) | 架构骨架:6 层记忆、蜂群、Wiki、进化、Loop、同步、安全 |
| **awesome-llm-apps** | 四大模式:A-O-W 编排、自进化蒸馏、多 Agent 互验、预算控制 |
| **NomiFun** | 架构借鉴:双主机模式、Computer Use、12 IM 渠道、MCP 协议 |

---

## 📊 性能基准

| 指标 | 数值 |
|------|------|
| 后端启动 | **1.51s** |
| 首响应 | **0.01s** |
| API 端点响应 | **< 0.03s** |
| 前端构建 | 24 模块 / 142KB JS / 982ms |
| 打包体积 | 11.87MB(exe) / 48.54MB(完整目录) |
| 测试通过 | 19/19(单元+冒烟+构建+性能) |

---

## 🛠️ 项目结构

```
Pangu-Nebula/
├── server/                 # 后端
│   ├── api/               # 27 个路由模块
│   ├── services/          # 40+ 服务
│   ├── providers/         # 7 个 LLM 适配器
│   ├── db/                # ORM + 连接池
│   └── main.py            # FastAPI 入口
├── frontend/              # 前端
│   └── src/
│       ├── components/    # 14 个 Preact 组件
│       ├── lib/           # API 客户端 + 类型
│       └── styles/        # 三色系 CSS 变量
├── tests/                 # 19 项测试
├── docs/                  # 规格书 + 任务追踪 + 融合报告
├── launch.py              # 桌面应用入口
├── scripts/
│   ├── dev.py             # 开发环境
│   └── build.py           # 一键构建
└── pangu-nebula.spec      # PyInstaller 配置
```

---

## 🎯 适合谁用?

- **开发者**:想要一个真正"记住"项目上下文的 AI 助手,而不是每次对话都从零开始
- **写作者**:需要 AI 理解你的文风、记住你的素材库、帮你管理知识图谱
- **隐私重视者**:不信任云端 AI 服务,想要 100% 本地运行的方案
- **多模型用户**:不想被绑定在单一厂商,想要随时切换最优模型
- **自动化爱好者**:想要定时任务、蜂群协作、浏览器自动化集成在一个应用里

---

## 📈 版本规划

| 版本 | 状态 | 内容 |
|------|------|------|
| v0.1.0 | ✅ 已发布 | 11 Phase 全量交付,193+ API,14 组件 |
| v0.2.0 | 🔄 规划中 | DAG 编排、更多 IM 渠道、图像生成 |
| v0.5.0 | 📋 计划中 | 插件系统、主题市场、跨平台(macOS/Linux) |
| v1.0.0 | 🎯 目标 | 自动更新、多语言 UI、移动端 companion |

---

## 🤝 贡献

欢迎 Issue 和 PR!

- 发现 bug? [提个 Issue](https://github.com/AQWlala/Pangu-Nebula/issues)
- 有想法? [发起讨论](https://github.com/AQWlala/Pangu-Nebula/discussions)
- 想贡献代码? Fork → Branch → PR

---

## 📄 License

MIT License — 随便用,别删版权声明就行。

---

<div align="center">

**你的思考,不该成为别人的养料。**

🌌 Pangu Nebula — 本地优先,数据主权,AI 伙伴

[⭐ Star](https://github.com/AQWlala/Pangu-Nebula) · [📦 Clone](https://github.com/AQWlala/Pangu-Nebula.git) · [🐛 Report](https://github.com/AQWlala/Pangu-Nebula/issues)

</div>
