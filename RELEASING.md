# Releasing Pangu Nebula

本文档描述 Pangu Nebula 的版本发布流程,涵盖版本号规范、发布前检查、打包、GitHub Release、回滚与紧急修复。

> 当前版本: **v1.1.0**
> 发布渠道: [GitHub Releases](https://github.com/AQWlala/Pangu-Nebula/releases)

---

## 一、版本号规范

遵循 [Semantic Versioning](https://semver.org/spec/v2.0.0.html): `MAJOR.MINOR.PATCH`

| 版本段 | 何时升级 | 示例 |
|---|---|---|
| **MAJOR** | 不兼容的 API 变更 | v1.x.x → v2.0.0 |
| **MINOR** | 向下兼容的新功能 | v1.1.x → v1.2.0 |
| **PATCH** | 向下兼容的 bug 修复 | v1.1.0 → v1.1.1 |

### 1.1 版本号更新位置

发布新版本时,需同步更新以下文件:

| 文件 | 字段 | 示例 |
|---|---|---|
| `pyproject.toml` | `version` | `version = "1.2.0"` |
| `CHANGELOG.md` | 新增版本段落 + `[Unreleased]` 链接 | `[1.2.0] - 2026-xx-xx` |
| `README.md` | Roadmap 表格 (如涉及) | — |

> **注意**: `pyproject.toml` 当前为 `version = "0.1.0"`,与 git tag 不一致。发布前需手动更新此字段到对应版本号。

### 1.2 预发布版本

预发布版本使用后缀:

| 类型 | 格式 | 示例 |
|---|---|---|
| Alpha | `vX.Y.Z-alpha.N` | `v0.2.0-alpha.1` |
| Beta | `vX.Y.Z-beta.N` | `v0.2.0-beta.1` |
| Release Candidate | `vX.Y.Z-rc.N` | `v0.2.0-rc.1` |

预发布版本不打 GitHub Release (仅打 tag),避免污染 Release 页面。

---

## 二、发布前检查清单

发布前**必须**逐项确认,任何一项失败则阻塞发布。

### 2.1 代码质量

```bash
# 1. 后端单元测试全绿
pytest tests/ -v --tb=short
# 预期: 62+ tests passed (当前 v1.1.0 基线)

# 2. mypy 类型检查通过
mypy server/services server/db server/api server/providers server/tools

# 3. black 格式检查
black --check server/ tests/ scripts/

# 4. ruff lint 通过
ruff check server/ tests/ scripts/
```

### 2.2 前端构建

```bash
cd frontend

# 5. TypeScript 类型检查 0 errors
npx tsc --noEmit

# 6. Vite 构建成功
npm run build

# 7. 确认产物存在
ls dist/index.html
# 预期: dist/index.html 存在

cd ..
```

### 2.3 打包验证

```bash
# 8. PyInstaller 打包成功 (本地预演)
python -m PyInstaller pangu-nebula.spec --noconfirm

# 9. EXE 可启动
dist\PanguNebula\PanguNebula.exe
# 预期: 窗口正常打开,后端 /health 返回 200

# 10. 清理打包残留
rmdir /s /q dist
rmdir /s /q build
```

### 2.4 文档与版本号

- [ ] `pyproject.toml` 的 `version` 已更新
- [ ] `CHANGELOG.md` 新增版本段落,`[Unreleased]` 为空
- [ ] `README.md` 版本徽章与 Roadmap 已更新 (如涉及)
- [ ] 所有变更已提交并推送到 `main`

### 2.5 检查清单汇总

| # | 项目 | 命令 / 检查 | 期望结果 |
|:---:|---|---|---|
| 1 | 后端测试 | `pytest tests/ -v` | 全绿 (≥ 62 tests) |
| 2 | 类型检查 | `mypy server/...` | 0 errors |
| 3 | 格式检查 | `black --check` | 全部通过 |
| 4 | Lint | `ruff check` | 0 errors |
| 5 | 前端类型 | `npx tsc --noEmit` | 0 errors |
| 6 | 前端构建 | `npm run build` | 成功 |
| 7 | 产物存在 | `dist/index.html` | 文件存在 |
| 8 | 打包 | `pyinstaller pangu-nebula.spec` | 成功 |
| 9 | EXE 启动 | `dist\PanguNebula\PanguNebula.exe` | 窗口正常 |
| 10 | 版本号 | `pyproject.toml` + `CHANGELOG.md` | 已更新 |

---

## 三、PyInstaller 打包步骤

PyInstaller 配置在 `pangu-nebula.spec`,采用 **onedir** 模式 (单文件夹分发,支持增量更新)。

### 3.1 前置准备

```bash
# 安装打包依赖
pip install pyinstaller
pip install -r requirements.txt

# 构建前端 (必须先于打包)
cd frontend && npm ci && npm run build && cd ..
```

### 3.2 执行打包

```bash
# 标准打包命令
python -m PyInstaller pangu-nebula.spec --noconfirm
```

### 3.3 产物验证

```powershell
# 验证 EXE 存在
$exe = "dist\PanguNebula\PanguNebula.exe"
if (-not (Test-Path $exe)) {
    Write-Error "EXE 构建失败: $exe 不存在"
    exit 1
}
$sizeMB = [math]::Round((Get-Item $exe).Length / 1MB, 2)
Write-Host "✅ EXE 构建成功: $exe ($sizeMB MB)"

# 启动验证
& $exe
# 预期: 窗口打开,后端启动,可正常交互
```

### 3.4 清理运行时数据

打包后,`dist\PanguNebula\` 可能残留开发期的运行时数据,发布前需清理:

```powershell
Remove-Item -Recurse -Force "dist\PanguNebula\data" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "dist\PanguNebula\__pycache__" -ErrorAction SilentlyContinue
```

### 3.5 打包为 ZIP

```powershell
$tag = "v1.1.0"  # 替换为实际版本
$zipName = "PanguNebula-$tag-win64.zip"
Compress-Archive -Path "dist\PanguNebula" -DestinationPath "dist\$zipName" -CompressionLevel Optimal
Write-Host "✅ ZIP 打包完成: dist\$zipName"
```

### 3.6 spec 文件关键配置

| 配置 | 值 | 说明 |
|---|---|---|
| 模式 | onedir | 单文件夹,快速启动 |
| 入口 | `launch.py` | PyWebView 启动 uvicorn + 桌面窗口 |
| `console` | `False` | GUI 应用,无控制台窗口 |
| 前端资源 | `frontend/dist` → `frontend/dist` | 打包进 exe 目录 |
| hidden imports | `collect_submodules("server")` + uvicorn/sqlalchemy/webview 子模块 | 动态导入的模块 |
| excludes | tkinter / matplotlib / pytest | 排除不需要的大依赖 |

---

## 四、GitHub Release 流程

Release 流程通过 GitHub Actions 自动化 (`.github/workflows/release.yml`):打 tag → 自动构建 → 上传到 Release。

### 4.1 创建版本提交

```bash
# 1. 确保在 main 分支且最新
git checkout main
git pull origin main

# 2. 更新版本号 (pyproject.toml + CHANGELOG.md)
# 编辑 pyproject.toml: version = "1.2.0"
# 编辑 CHANGELOG.md: 新增 [1.2.0] 段落

# 3. 提交版本变更
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): v1.2.0"

# 4. 推送到 main
git push origin main
```

### 4.2 打 Tag 触发自动构建

```bash
# 5. 创建 tag (格式: vX.Y.Z)
git tag v1.2.0

# 6. 推送 tag (触发 release.yml workflow)
git push origin v1.2.0
```

### 4.3 自动构建流程

推送 `v*` tag 后,`release.yml` 自动执行:

1. Checkout 代码
2. Setup Python 3.11 + Node 20
3. Install Python dependencies + PyInstaller
4. Install frontend dependencies
5. Build frontend (`npm run build`)
6. Verify `frontend/dist/index.html` 存在
7. Run pytest (打包前测试)
8. Build EXE (`pyinstaller pangu-nebula.spec --noconfirm`)
9. Verify EXE 存在 + 输出大小
10. Clean runtime data
11. Package ZIP (`PanguNebula-vX.Y.Z-win64.zip`)
12. Upload to GitHub Release (softprops/action-gh-release@v2)
13. Upload build artifact (保留 30 天)

### 4.4 验证 Release

1. 前往 [Releases 页面](https://github.com/AQWlala/Pangu-Nebula/releases) 确认新 Release 已创建
2. 确认 `PanguNebula-vX.Y.Z-win64.zip` 附件已上传
3. 下载 ZIP,解压,运行 `PanguNebula.exe`,确认可正常启动
4. 检查 GitHub Actions 构建日志无报错

### 4.5 发布公告 (可选)

Release 发布后:

- 更新 README 版本徽章
- 在 GitHub Release 描述中粘贴 CHANGELOG 对应段落
- (可选) 社交媒体公告

---

## 五、回滚流程

当发布版本存在严重问题需要撤回时。

### 5.1 评估回滚必要性

| 情况 | 处理方式 |
|---|---|
| 严重 bug 影响启动 | 回滚 |
| 安全漏洞 | 紧急修复 (见第六节),通常不回滚而是发 patch |
| 功能缺陷但不影响启动 | 发 patch,不回滚 |
| CI 构建失败但 tag 已推 | 删除 tag,修复后重新打 tag |

### 5.2 回滚步骤

```bash
# 1. 删除 GitHub Release (保留 tag 以便追溯,或一并删除)
# 通过 GitHub UI: Releases → 找到目标版本 → Delete
# 或通过 gh CLI:
gh release delete v1.2.0 --yes

# 2. 删除 tag (本地 + 远程)
git tag -d v1.2.0
git push origin :refs/tags/v1.2.0

# 3. Revert 版本提交 (如版本号变更已推送)
git revert <version-commit-hash>
git push origin main

# 4. 修复问题后重新发布 (见第四节)
```

### 5.3 回滚后通知

- 在 GitHub Issues 说明回滚原因
- 如有用户已下载问题版本,发布 Issue 说明升级到修复版本
- 更新 CHANGELOG,标注回滚版本

---

## 六、紧急修复流程 (Hotfix)

当已发布版本发现严重 bug 或安全漏洞,需立即发布 patch 版本。

### 6.1 创建 hotfix 分支

```bash
# 1. 从最新 tag 创建 hotfix 分支
git checkout -b hotfix/v1.1.1 v1.1.0

# 2. 修复问题 (最小变更,仅修复目标问题)
# 编码 + 测试
pytest tests/ -v --tb=short
```

### 6.2 发布 patch 版本

```bash
# 3. 更新版本号 (PATCH 段 +1)
# pyproject.toml: version = "1.1.1"
# CHANGELOG.md: 新增 [1.1.1] 段落

# 4. 提交并打 tag
git add -A
git commit -m "fix: 紧急修复 xxx 问题

- 修复具体原因
- 回归测试已覆盖

Fixes #123"

git tag v1.1.1
git push origin hotfix/v1.1.1
git push origin v1.1.1
```

### 6.3 合并回 main

```bash
# 5. 创建 PR 将 hotfix 合并回 main
git checkout main
git pull origin main
git merge hotfix/v1.1.1
git push origin main

# 6. 删除 hotfix 分支
git branch -d hotfix/v1.1.1
git push origin :hotfix/v1.1.1
```

### 6.4 紧急修复时间目标

| 严重程度 | 目标时间 |
|---|---|
| 严重 (CVSS ≥ 9.0 / 启动崩溃) | 24 小时内发布 patch |
| 高 (CVSS 7.0-8.9) | 3 天内发布 patch |
| 中 (CVSS 4.0-6.9) | 下一个常规版本 |
| 低 (CVSS < 4.0) | 下一个常规版本 |

---

## 七、手动触发 Release (应急)

当 tag 未自动触发或需要重新构建时,可手动触发 `release.yml`:

1. 前往 GitHub Actions 页面
2. 选择 "Release" workflow
3. 点击 "Run workflow"
4. 输入 tag (如 `v1.1.0`)
5. 确认触发

> 手动触发会重新构建并上传到已有 Release (覆盖原附件)。

---

## 八、版本发布检查总表

| 阶段 | 步骤 | 负责人 | 状态 |
|---|---|:---:|:---:|
| 发布前 | pytest 全绿 | dev | ⬜ |
| 发布前 | tsc 0 errors | dev | ⬜ |
| 发布前 | npm build 成功 | dev | ⬜ |
| 发布前 | PyInstaller 本地打包成功 | dev | ⬜ |
| 发布前 | EXE 本地启动验证 | dev | ⬜ |
| 发布前 | pyproject.toml 版本号更新 | dev | ⬜ |
| 发布前 | CHANGELOG.md 更新 | dev | ⬜ |
| 发布前 | 版本提交推送到 main | dev | ⬜ |
| 发布 | 打 tag + push tag | dev | ⬜ |
| 发布 | GitHub Actions 自动构建 | CI | ⬜ |
| 发布 | Release 附件验证 | dev | ⬜ |
| 发布后 | 下载 ZIP 实际启动验证 | dev | ⬜ |
| 发布后 | Release 描述粘贴 CHANGELOG | dev | ⬜ |
| 发布后 | README 版本徽章更新 | dev | ⬜ |
