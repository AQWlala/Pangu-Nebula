# Contributing to Pangu Nebula

感谢你对 Pangu Nebula 的关注!本文档帮助贡献者快速搭建开发环境并参与项目。

> 项目地址: https://github.com/AQWlala/Pangu-Nebula
> 许可协议: MIT

---

## 一、开发环境搭建

### 1.1 前置要求

| 工具 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+ | 3.12 亦可,CI 双版本验证 |
| Node.js | 20+ | 22 亦可,CI 双版本验证 |
| Git | 2.30+ | 支持 Conventional Commits hook |
| 操作系统 | Windows 10+ | 当前仅 Windows 完整支持,macOS/Linux 适配在 v1.0.0 |

### 1.2 搭建步骤

```bash
# 1. 克隆仓库
git clone https://github.com/AQWlala/Pangu-Nebula.git
cd Pangu-Nebula

# 2. 创建 Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. 安装后端依赖 (含开发依赖)
pip install -e ".[dev]"

# 4. 安装前端依赖
cd frontend
npm install
cd ..

# 5. 构建前端
cd frontend && npm run build && cd ..

# 6. 启动应用
python launch.py              # 桌面应用
python launch.py --no-window  # 仅后端 (调试用)
```

### 1.3 开发模式

前端热更新开发模式:

```bash
# 终端 1: 启动后端
python launch.py --no-window

# 终端 2: 启动前端 dev server (热更新)
cd frontend
npm run dev
```

---

## 二、项目结构

```
Pangu Nebula/
├── launch.py              # 桌面应用入口 (PyWebView + uvicorn)
├── pangu-nebula.spec      # PyInstaller 打包配置
├── pyproject.toml         # Python 项目元数据 + 工具配置
├── requirements.txt       # 运行时依赖
├── server/                # 后端 (Python + FastAPI)
│   ├── api/               # 24 个路由模块, 200+ 端点
│   ├── services/          # 47 个服务模块 (核心业务逻辑)
│   ├── core/              # 公共 API 再导出层 (稳定接口)
│   ├── providers/         # LLM provider 适配器 (OpenAI/Anthropic/Gemini)
│   ├── tools/             # 内置工具注册表
│   └── db/                # ORM 模型 + 引擎
├── frontend/              # 前端 (Preact + TypeScript + Tailwind)
│   ├── src/
│   │   ├── components/    # 14 个 UI 组件
│   │   ├── lib/           # API 客户端 + 类型定义
│   │   └── styles/        # 全局样式 + CSS 变量
│   └── package.json
├── tests/                 # 测试 (pytest)
│   ├── test_*.py          # 单元测试
│   └── e2e/               # 端到端测试
├── scripts/               # 开发/构建脚本
├── docs/                  # 设计文档与计划
└── .github/workflows/     # CI/CD (ci.yml / release.yml / pages.yml / security.yml)
```

### 目录约定

| 目录 | 职责 | 贡献者注意 |
|---|---|---|
| `server/api/` | HTTP 路由层,薄封装 | 路由只做参数校验与调用 service,不写业务逻辑 |
| `server/services/` | 核心业务逻辑 | 新功能主要在此添加 |
| `server/core/` | 稳定公共 API | 仅做再导出,外部代码应优先 import 此处 |
| `server/providers/` | LLM 适配 | 新增 provider 继承 `BaseProvider` |
| `frontend/src/components/` | UI 组件 | 单文件单组件,命名 PascalCase |
| `tests/` | 测试 | 文件名 `test_*.py`,函数名 `test_*` |

---

## 三、代码风格

### 3.1 Python

工具链: **black + ruff + mypy**,配置在 `pyproject.toml`。

```bash
# 格式化
black server/ tests/ scripts/

# lint
ruff check server/ tests/ scripts/

# 类型检查
mypy server/services server/db server/api server/providers server/tools
```

关键约定:

| 规则 | 要求 |
|---|---|
| 行宽 | 88 (black 默认) |
| 缩进 | 4 空格 |
| 引号 | 双引号 (black 默认) |
| import 排序 | isort black profile |
| 类型标注 | 公共函数与 service 层必须标注 |
| `ignore_missing_imports` | mypy 已开启,第三方库缺类型时容忍 |

### 3.2 TypeScript / Preact

工具链: **tsc + ESLint**(通过 Vite 集成)。

```bash
cd frontend
npx tsc --noEmit          # 类型检查 (CI 强制)
npm run build             # 构建 (CI 强制)
```

关键约定:

| 规则 | 要求 |
|---|---|
| 组件命名 | PascalCase (`ChatPanel.tsx`) |
| 函数式组件 | 使用 Preact 函数式组件 + Hooks |
| 样式 | Tailwind CSS utility classes,避免自定义 CSS |
| 状态管理 | 通过 `lib/api.ts` 调用后端,前端不持久化业务状态 |

### 3.3 中文注释要求

- **公开 API 与 service 层**: 函数 docstring 使用中文,说明用途、参数、返回值
- **复杂业务逻辑**: 关键步骤加中文行内注释
- **commit message**: 详见第四节,中文 description 可接受但 type/scope 用英文
- **README / 文档**: 中文为主

示例:

```python
async def compress_memory(self, layer: int, threshold: int = 1000) -> int:
    """压缩指定记忆层,将超过阈值的历史记忆向上层归档。

    黑洞引擎不删除数据,而是提取关键信息写入上层,保留可追溯链接。

    Args:
        layer: 待压缩的记忆层 (0-5)
        threshold: 触发压缩的记录数阈值

    Returns:
        实际压缩的记录数
    """
```

---

## 四、提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

### 4.1 提交格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 4.2 type 清单

| type | 用途 | 示例 |
|---|---|---|
| `feat` | 新功能 | `feat(provider): 新增 DeepSeek provider` |
| `fix` | bug 修复 | `fix(window): 修复 console=False 启动崩溃` |
| `docs` | 文档变更 | `docs: 新增 CONTRIBUTING.md` |
| `refactor` | 重构 (无功能变化) | `refactor(db): 合并 models.py 到 orm.py` |
| `test` | 测试相关 | `test(memory): 新增 sponge engine 单元测试` |
| `chore` | 构建/工具/依赖 | `chore(deps): 升级 fastapi 到 0.115` |
| `style` | 代码格式 (不影响逻辑) | `style: black 格式化` |
| `perf` | 性能优化 | `perf(memory): 优化 FTS5 索引查询` |
| `ci` | CI 配置 | `ci: 新增 CodeQL 安全扫描` |

### 4.3 scope 建议

`provider` / `memory` / `swarm` / `skill` / `window` / `db` / `api` / `frontend` / `security` / `deps` / `ci`

### 4.4 示例

```
feat(swarm): 支持 worker 动态扩缩容

新增 worker_count 配置项,运行时可动态调整 2-8 个 worker。
资源不足时自动缩减至下限。

Closes #42
```

---

## 五、PR 流程

### 5.1 准备

1. **Fork** 仓库到你的 GitHub 账号
2. **Clone** 你的 fork 到本地
3. **同步** upstream main 分支:
   ```bash
   git remote add upstream https://github.com/AQWlala/Pangu-Nebula.git
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

### 5.2 开发

4. **创建分支** (从最新 main):
   ```bash
   git checkout -b feat/my-feature
   ```
   分支命名: `<type>/<short-description>`,如 `feat/deepseek-provider`、`fix/window-crash`

5. **编码 + 提交**: 遵循第四节提交规范,多个小提交优于一个大提交

6. **本地验证** (必须全部通过):
   ```bash
   # 后端
   pytest tests/ -v --tb=short
   mypy server/services server/db server/api server/providers server/tools
   black --check server/ tests/ scripts/
   ruff check server/ tests/ scripts/

   # 前端
   cd frontend
   npx tsc --noEmit
   npm run build
   ```

### 5.3 提交 PR

7. **Push** 到你的 fork:
   ```bash
   git push origin feat/my-feature
   ```

8. **创建 PR**: 目标分支 `main`,PR 标题遵循 Conventional Commits 格式

9. **PR 描述** 包含:
   - 变更说明 (做了什么、为什么)
   - 关联 Issue (`Closes #123`)
   - 测试情况 (本地验证结果)
   - 是否有破坏性变更

10. **CI 通过**: PR 会自动触发 CI (pytest + tsc + npm build),必须全绿

11. **Code Review**: 至少一名 maintainer review 通过后合并

---

## 六、测试要求

### 6.1 测试工具

| 层 | 工具 | 命令 |
|---|---|---|
| 后端单元测试 | pytest + pytest-asyncio | `pytest tests/ -v` |
| 后端覆盖率 | pytest-cov | `pytest --cov=server tests/` |
| 前端类型检查 | tsc | `cd frontend && npx tsc --noEmit` |
| 前端构建 | Vite | `cd frontend && npm run build` |
| 端到端 | pytest e2e/ | `pytest tests/e2e/ -v` |

### 6.2 测试规范

- **新增功能必须附带测试**: 新 service 函数至少 1 个单元测试
- **修复 bug 必须附回归测试**: 先写复现测试,再修复
- **测试文件位置**: `tests/test_<module>.py`
- **异步测试**: `pytest-asyncio` 已配置 `auto` 模式,直接 `async def test_xxx()`
- **测试隔离**: 每个测试用独立临时数据库,见 `tests/conftest.py`

### 6.3 CI 强制门槛

CI (`.github/workflows/ci.yml`) 会在每次 PR 时运行:

- Python 3.11 + 3.12 矩阵: `pytest tests/ -v --tb=short`
- Node 20 + 22 矩阵: `npx tsc --noEmit` + `npm run build`

**任何一项失败,PR 不可合并。**

---

## 七、问题与讨论

- **Bug 报告**: [GitHub Issues](https://github.com/AQWlala/Pangu-Nebula/issues) — 使用 Bug template
- **功能建议**: GitHub Issues — 使用 Feature Request template
- **安全漏洞**: 见 [SECURITY.md](./SECURITY.md) — **勿在公开 Issue 讨论安全问题**
- **代码讨论**: PR评论区

---

## 八、行为准则

- 尊重所有贡献者,不论身份与经验
- 聚焦技术讨论,对事不对人
- 欢迎新手提问,耐心解答
- 接受建设性批评,也乐于给出建设性反馈

---

## 九、致谢

感谢每一位为 Pangu Nebula 贡献代码、文档、Issue 和 Star 的人。你让这个项目变得更好。
