<div align="center">

# 🌌 Pangu Nebula

### 本地优先的多 Agent 编排平台与认知架构

**蜂群协作 · 6 层记忆 · 自进化引擎 · MCP 协议原生**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)]()
[![Preact](https://img.shields.io/badge/Preact-10.19+-673AB8?logo=preact&logoColor=white)]()
[![Tests](https://img.shields.io/badge/Tests-19%20passed-brightgreen)]()
[![API](https://img.shields.io/badge/API-193+%20endpoints-blue)]()
[![Phases](https://img.shields.io/badge/Phases-11%2F11%20DONE-success)]()

</div>

---

## 这是什么

Pangu Nebula 是一个**本地运行的多 Agent 编排平台**,核心解决一个问题:

> 单个 LLM 调用解决不了复杂任务,而云上 Agent 平台又会拿走你的数据。

它把"理解需求 → 拆解任务 → 并行执行 → 结果互验 → 汇总输出"这个链条完整工程化,并配以 6 层记忆图谱让 Agent 具备跨会话的上下文保持能力。全部数据留在本地 SQLite,无云端依赖。

**不是聊天框,是 Agent 运行时。**

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                        用户交互层                              │
│         PyWebView 原生窗口 · Preact UI · SSE 流式              │
├──────────────────────────────────────────────────────────────┤
│                       编排调度层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Persona 主控  │→│ Orchestrator │→│  Swarm Pool  │        │
│  │ (3 个自定义)  │  │  (任务拆解)   │  │ (2-5 Worker) │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│         ↑                ↓                  ↓                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Verifier    │←│  Composer    │←│  Workers     │        │
│  │ (多Agent互验) │  │  (结果汇总)   │  │ (并行执行)    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
├──────────────────────────────────────────────────────────────┤
│                        能力引擎层                              │
│  Memory    Swarm    Skills   Wiki    Evolution   Loop        │
│  (6层)    (A-O-W)   (蒸馏)   (编译)  (4阶段)    (迭代)       │
├──────────────────────────────────────────────────────────────┤
│                       协议与适配层                             │
│  LLM Provider Adapter · MCP Client/Server · IM Bridge        │
│  Scheduler (cron) · Sync (CRDT) · OS Sense · Multimodal      │
├──────────────────────────────────────────────────────────────┤
│                        安全与身份层                            │
│  E2EE · ACL · Injection Guard · SSRF Guard · OAuth · DID     │
├──────────────────────────────────────────────────────────────┤
│                        数据与存储层                            │
│  SQLite (aiosqlite) · FTS5 全文搜索 · 文件系统 · 内存状态     │
└──────────────────────────────────────────────────────────────┘
```

**6 层分层,职责清晰,每层可独立替换。**

---

## 核心架构设计

### 1. A-O-W 编排模式(Advisor-Orchestrator-Worker)

这是系统的**核心调度逻辑**,不是简单的多轮对话:

```
用户输入
  │
  ▼
┌─────────────┐     理解需求,确认范围
│  Advisor     │     (Persona 主智能体,有角色设定)
│  (主控)      │     可与用户多轮对话澄清
└─────┬───────┘
      │ 确认后下发
      ▼
┌─────────────┐     将需求拆解为 subtask 列表
│Orchestrator │     分配给 Worker,控制并行度
│  (编排器)    │     监控执行状态,处理失败重试
└─────┬───────┘
      │ 并行派发
      ▼
┌─────────────┐
│  Worker 1   │────┐
│  Worker 2   │────┤  独立执行,各自调用 LLM/工具
│  Worker 3   │────┘  结果可能不同
└─────────────┘
      │
      ▼
┌─────────────┐     多 Agent 结果互验
│  Verifier   │     少数服从多数,标记分歧
│  (验证器)    │     不一致时触发重试或人工介入
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Composer   │     汇总验证通过的结果
│  (汇总器)    │     生成最终输出
└─────────────┘
```

**为什么这样设计?**
- 单次 LLM 调用可靠性不足,多 Agent 互验提高准确率
- 复杂任务可并行拆解,而不是串行等待
- Advisor 有 Persona,输出风格一致;Worker 无 Persona,专注执行

### 2. 6 层记忆架构

不是把所有聊天记录塞进一个向量库,而是**按认知科学分层**:

```
L5  元认知      Agent 自我反思、策略调整记录
    ─────────────────────────────────────
L4  程序记忆     技能、模板、可复用的工作流
    ─────────────────────────────────────
L3  语义记忆     从对话中提炼的知识点、事实
    ─────────────────────────────────────
L2  情节记忆     完整对话历史,带时间线
    ─────────────────────────────────────
L1  事件记忆     近期交互,短期上下文窗口
    ─────────────────────────────────────
L0  工作记忆     当前对话的活跃上下文
```

**两个引擎维持记忆健康:**

- **海绵引擎(Sponge Engine)**:自动从对话中吸收有价值信息,写入对应层级
- **黑洞引擎(Black Hole Engine)**:压缩冗余记忆,L1→L2 归档,L2→L3 提炼,防止膨胀

**双向链接**:记忆内容用 `[[标题]]` 互引,自动发现反向链接,构建知识图谱(非简单标签)。

### 3. 自进化闭环

系统不只是执行任务,还会**从执行中学习**:

```
任务执行
  │
  ├─ 成功 ──→ 技能蒸馏器(Distiller)
  │           提取可复用模式 → 生成新技能 → 存入 L4
  │           下次类似任务可直接调用,不再从零推理
  │
  └─ 失败 ──→ 教训记录
              写入 L5 元认知
              下次遇到类似情况自动回避
```

**4 阶段进化管道:**

1. **Reflect(反思)**:分析本次执行,识别成功/失败模式
2. **Plan(规划)**:调整策略,更新技能优先级
3. **Execute(执行)**:在下次任务中应用新策略
4. **Integrate(整合)**:将验证有效的新策略固化为技能

### 4. Loop 循环迭代

不是一次性输出,而是**带预算控制的多轮优化**:

```
初始输出 → 自评 → 不满意? → 迭代优化 → 满意? → 最终输出
                       ↑              │
                       └──────────────┘
                       
预算控制:
  - Token 预算:超限则停止迭代
  - 时间预算:超时则降级输出
  - 金额预算:超成本则中断
  - 迭代次数:硬上限防死循环
  
全程审计日志,每次迭代可追溯。
```

### 5. MCP 协议(模型上下文协议)

原生实现 MCP 客户端 + 服务端,不是简单 HTTP 调用:

```
Pangu Nebula
  │
  ├─ 作为 MCP Client
  │   连接外部 MCP Server(stdio/json-rpc)
  │   自动发现工具 → 调用 → 获取结果
  │
  └─ 作为 MCP Server
      对外暴露内部能力(记忆查询、技能调用等)
      其他 Agent 平台可接入
```

**意义**:不锁定在特定工具生态,任何 MCP 兼容工具都能接入,任何 MCP 兼容平台都能调用 Pangu Nebula 的能力。

---

## 工程化能力

### 模块化设计

27 个路由模块,**每个模块自包含**:API 层 + Service 层 + 数据模型。

```
server/
├── api/           # 路由层(薄,仅参数校验+转发)
│   ├── chat.py
│   ├── persona.py
│   ├── swarm.py
│   ├── memory.py
│   ├── skills.py
│   ├── wiki.py
│   ├── sync.py
│   ├── mcp.py
│   ├── scheduler.py
│   ├── health.py
│   └── ... (27 个模块)
├── services/      # 业务层(厚,核心逻辑)
│   ├── memory_service.py
│   ├── swarm_orchestrator.py
│   ├── sponge_engine.py
│   ├── blackhole_engine.py
│   ├── skill_distiller.py
│   ├── evolution_engine.py
│   └── ... (40+ 个服务)
├── providers/     # LLM 适配层
│   ├── base.py          # 抽象接口
│   ├── openai_compat.py # 一个类覆盖所有 OpenAI 兼容 API
│   └── ... (7 个适配器)
└── db/            # 数据层
    ├── connection.py
    └── models.py
```

### Provider 适配架构

**一套接口,多厂商切换**,不是 if-else 堆砌:

```python
# providers/base.py 定义抽象接口
class BaseProvider:
    async def chat(messages, **kwargs) -> str
    async def chat_stream(messages, **kwargs) -> AsyncIterator[str]
    async def chat_with_image(messages, image, **kwargs) -> str

# providers/openai_compat.py 一个类覆盖 6 家国产大厂
class OpenAICompatibleProvider(BaseProvider):
    # 通义/文心/GLM/Kimi/豆包/混元 仅 endpoint+model 不同
    # 统一走 OpenAI 兼容协议
```

无默认 Provider,无优先级排序。用户在设置中选择,切换即生效。

### CRDT 多设备同步

不用中心化冲突解决,而是 **CRDT(无冲突复制数据类型)**:

| 类型 | 用途 |
|------|------|
| LWW Register | Last-Write-Wins,适合标量(设置项) |
| OR-Set | Observed-Remove Set,适合集合(记忆列表) |
| RGA | Replicated Growable Array,适合有序文本 |

同步层全部 E2EE 加密(X25519 + AES-256-GCM),中继服务器看不到明文。

### 可选依赖模式

核心功能不依赖重型第三方库,**全部 try/except 导入**:

```python
# 示例:APcheduler 是可选的
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
```

这意味着:
- 裸安装能跑核心功能
- 需要某模块时再装对应依赖
- 不会因为某个可选依赖缺失而整体崩溃

### 统一响应格式

所有 API 遵循同一格式,前端处理逻辑统一:

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

---

## 数据流

### 一次完整任务的数据流

```
1. 用户输入
   └→ POST /chat/stream (SSE)

2. Persona 主控理解需求
   └→ 加载 L0/L1 记忆作为上下文
   └→ 调用 LLM 生成理解 + 拆解方案

3. Orchestrator 分发子任务
   └→ 创建 SwarmTask 记录
   └→ 并行派发 N 个 Worker

4. Worker 执行
   └→ 每个 Worker 独立调用 LLM
   └→ 可调用 Skills / MCP 工具
   └→ 可查询 L2/L3 记忆补充上下文

5. Verifier 互验
   └→ 比对 Worker 结果
   └→ 一致 → 通过
   └→ 不一致 → 标记分歧,可选重试

6. Composer 汇总
   └→ 调用 LLM 生成最终输出
   └→ SSE 流式返回前端

7. 后台异步
   └→ Sponge Engine 从对话中吸收新记忆
   └→ Skill Distiller 尝试蒸馏新技能
   └→ Wiki Compiler 生成知识笔记
   └→ Evolution Engine 记录执行日志
```

**步骤 1-6 对用户是实时的,步骤 7 在后台异步执行,不阻塞响应。**

---

## 扩展点

系统设计时预留了清晰的扩展点:

| 扩展点 | 方式 | 示例 |
|--------|------|------|
| 新增 LLM 厂商 | 继承 BaseProvider | 实现 chat/chat_stream 即可 |
| 新增工具 | MCP Server 注册 | tools/call 协议自动发现 |
| 新增技能 | Skill 模块 + 沙箱执行 | Python 沙箱隔离运行 |
| 新增 IM 渠道 | 实现 Channel 接口 | wechat/feishu 已实现 |
| 新增定时任务 | Scheduler add_job | 4 种 action 类型 |
| 新增记忆层级 | 扩展 Memory model | L0-L5 已定义 |
| 新增进化阶段 | 扩展 Evolution pipeline | 4 阶段已实现 |

---

## 快速开始

```bash
# 克隆
git clone git@github.com:AQWlala/Pangu-Nebula.git
cd Pangu-Nebula

# 后端
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# 前端
cd frontend && npm install && npm run build && cd ..

# 启动
python launch.py              # 桌面应用
python scripts/dev.py         # 开发模式(热重载)
python scripts/build.py       # 一键打包
```

---

## 项目状态

| 维度 | 数据 |
|------|------|
| 架构层级 | 6 层(交互/编排/引擎/协议/安全/数据) |
| API 端点 | 193+ |
| 路由模块 | 27 |
| 服务模块 | 40+ |
| LLM 适配器 | 7 |
| 前端组件 | 14 |
| 测试 | 19 passed(单元+冒烟+构建+性能) |
| 启动耗时 | 1.51s |
| 打包体积 | 11.87MB(exe) |
| Phase 完成度 | 11/11 (100%) |

---

## 技术栈选型理由

| 层 | 选型 | 理由 |
|----|------|------|
| 后端 | Python 3.11 + FastAPI | 异步原生,AI 生态最广,自动 API 文档 |
| 数据库 | SQLite (aiosqlite) | 零配置,纯本地,无服务端依赖 |
| 全文搜索 | SQLite FTS5 | 不引入 ChromaDB,减少依赖 |
| 前端 | Preact + TypeScript | 轻量(3KB),类型安全,Vite 构建 |
| 桌面 | PyWebView | 原生窗口,非 Electron 资源黑洞 |
| 打包 | PyInstaller | onedir 模式,生成独立 .exe |
| LLM | 统一 Adapter | 一套接口覆盖所有厂商,无锁定 |

**核心原则:能不依赖就不依赖,能本地就不上云。**

---

## License

MIT

---

<div align="center">

**Pangu Nebula — Agent 运行时,不是聊天框。**

[GitHub](https://github.com/AQWlala/Pangu-Nebula) · [Issues](https://github.com/AQWlala/Pangu-Nebula/issues)

</div>
