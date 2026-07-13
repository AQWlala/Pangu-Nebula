# Pangu Nebula 部署指南 v1.0

> **版本**: v2.1.0 | **创建日期**: 2026-07-13
> **架构**: Tauri 2 (主壳) + Python FastAPI (sidecar) + Preact (前端)
> **支持平台**: Windows 10/11 x64, macOS 11+ (Apple Silicon + Intel), Ubuntu 22.04+

---

## 一、用户安装（终端用户）

### 1.1 Windows

#### 系统要求
- Windows 10 1809+ 或 Windows 11
- WebView2 Runtime（系统自带，缺失时安装包会自动下载安装）
- 150MB 可用磁盘空间

#### 安装方式

**方式一：MSI 安装包（推荐企业部署）**
1. 从 [Releases 页面](https://github.com/pangu-nebula/pangu-nebula/releases) 下载 `pangu-nebula_x.y.0_x64_en-US.msi`（或 `zh-CN.msi`）
2. 双击运行，按向导完成安装
3. 默认安装路径：`C:\Program Files\Pangu Nebula\`
4. 开始菜单 → "Pangu Nebula" 启动

**方式二：NSIS 安装包（推荐个人用户）**
1. 下载 `pangu-nebula_x.y.0_x64-setup.exe`
2. 双击运行（支持 displayLanguageSelector 选择语言）
3. 安装模式：`currentUser`（无需管理员权限）

#### 静默安装（企业）
```powershell
# MSI 静默安装
msiexec /i pangu-nebula_2.1.0_x64_en-US.msi /quiet /norestart INSTALLDIR="C:\Program Files\Pangu Nebula"

# NSIS 静默安装
.\pangu-nebula_2.1.0_x64-setup.exe /S
```

#### 卸载
- 控制面板 → 程序和功能 → Pangu Nebula → 卸载
- 或运行 `C:\Program Files\Pangu Nebula\uninstall.exe`

### 1.2 macOS

#### 系统要求
- macOS 11 Big Sur 或更高
- Apple Silicon (M1/M2/M3) 或 Intel 处理器

#### 安装步骤
1. 根据处理器选择 DMG：
   - Apple Silicon: `pangu-nebula_aarch64.dmg`
   - Intel: `pangu-nebula_x86_64.dmg`
2. 双击 DMG 挂载
3. 将 "Pangu Nebula.app" 拖入 "Applications" 文件夹
4. 首次启动：右键 → 打开（绕过 Gatekeeper 警告）

#### 命令行安装
```bash
# 挂载并复制
hdiutil attach pangu-nebula_aarch64.dmg
cp -R "/Volumes/Pangu Nebula/Pangu Nebula.app" /Applications/
hdiutil detach "/Volumes/Pangu Nebula"

# 启动
open /Applications/"Pangu Nebula.app"
```

#### 卸载
```bash
rm -rf /Applications/"Pangu Nebula.app"
rm -rf ~/Library/Application\ Support/pangu-nebula
```

### 1.3 Linux

#### 系统要求
- Ubuntu 22.04 LTS 或同等版本
- WebKit2GTK 4.1
- libgtk-3, libayatana-appindicator3

#### 系统依赖安装
```bash
sudo apt-get update
sudo apt-get install -y \
    libwebkit2gtk-4.1-1 \
    libgtk-3-0 \
    libayatana-appindicator3-1 \
    librsvg2-2
```

#### AppImage 安装
```bash
chmod +x pangu-nebula_2.1.0_amd64.AppImage
./pangu-nebula_2.1.0_amd64.AppImage
```

#### 集成到桌面
```bash
# 提取桌面图标
./pangu-nebula_2.1.0_amd64.AppImage --appimage-extract

# 创建 .desktop 文件
cat > ~/.local/share/applications/pangu-nebula.desktop <<EOF
[Desktop Entry]
Name=Pangu Nebula
Exec=/opt/pangu-nebula/pangu-nebula.AppImage
Icon=pangu-nebula
Type=Application
Categories=Utility;
EOF
```

### 1.4 自动更新

应用内集成 Tauri Updater，无需手动下载升级包：
1. 打开应用 → 设置 → 关于 → "检查更新"
2. 发现新版本后点击"立即更新"
3. 应用自动下载 → 校验 Ed25519 签名 → 安装 → 重启

**更新校验机制**：
- 下载产物含 `.sig` 签名文件
- tauri.conf.json 中配置公钥 `plugins.updater.pubkey`
- 私钥存储于 GitHub Secrets `TAURI_SIGNING_KEY`
- 签名校验失败会拒绝安装，防止中间人攻击

---

## 二、开发者构建

### 2.1 开发环境

#### 通用依赖
```bash
# Node.js 20+
node --version  # 应 >= 20.0.0

# Python 3.11
python --version  # 应为 3.11.x

# Rust stable
rustc --version  # 应 >= 1.75.0
cargo --version

# Tauri CLI
npm install -g @tauri-apps/cli@^2
```

#### 平台特定依赖

**Windows**
- Visual Studio 2022 Build Tools（含 MSVC + Windows SDK）
- WebView2 Runtime（开发环境可从 https://developer.microsoft.com/microsoft-edge/webview2/ 安装）

**macOS**
- Xcode Command Line Tools: `xcode-select --install`

**Linux**
```bash
sudo apt-get install -y \
    libwebkit2gtk-4.1-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    patchelf
```

### 2.2 本地开发模式

```bash
# 1. 克隆仓库
git clone https://github.com/pangu-nebula/pangu-nebula.git
cd pangu-nebula

# 2. 安装 Python 依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt

# 3. 安装前端依赖
cd frontend
npm install
cd ..

# 4. 开发模式运行（二选一）

# 方式 A：Tauri 模式（推荐，与生产环境一致）
export NEBULA_SHELL=tauri  # Windows: $env:NEBULA_SHELL="tauri"
cargo tauri dev
# Tauri 自动：启动 Vite dev server → spawn Python sidecar → 打开窗口

# 方式 B：PyWebView 模式（兼容旧版）
python launch.py
# 不设置 NEBULA_SHELL 默认走此路径

# 方式 C：浏览器开发模式（前端独立开发）
# 终端 1：启动后端
python launch.py  # 或：uvicorn server.main:app --port 7860
# 终端 2：启动前端
cd frontend && npm run dev
# 浏览器访问 http://localhost:5173
```

### 2.3 构建生产包

#### 2.3.1 版本号同步

```bash
# 检查版本号一致性（CI 强制）
python scripts/sync_version.py --check

# 设置新版本号（同步到 tauri.conf.json + Cargo.toml + pyproject.toml + frontend/package.json + launch.py）
python scripts/sync_version.py --version 2.1.0
```

#### 2.3.2 构建 Python sidecar

```bash
# PyInstaller 打包 Python 后端为独立可执行
python scripts/build_sidecar.py

# 产物位置：src-tauri/resources/pangu-sidecar/
# 包含：pangu-nebula-sidecar.exe + 依赖库 + 内置 Python
```

构建参数说明：
- `--onedir`：目录模式（启动快，便于增量更新）
- `--console`：保留 stdout（用于 PORT=/TOKEN= 握手协议）
- `--collect-submodules=server,webview,pangu_memory_sdk`：自动收集子模块
- `--hidden-import=uvicorn.*`：uvicorn 内部模块需显式声明

#### 2.3.3 生成 sidecar 完整性清单

```bash
# 生成 SHA-256 清单（启动时 Tauri 校验防篡改）
python scripts/gen_sidecar_hash.py --output sidecar.sha256 --root .

# 文件格式（与 sha256sum 兼容）:
# <hash>  path/to/file
# <hash>  path/to/another/file
```

#### 2.3.4 构建 Tauri 应用

```bash
# 构建（含 updater 签名）
export TAURI_SIGNING_KEY="<your-private-key>"
export TAURI_SIGNING_KEY_PASSWORD="<password>"
npx tauri build

# 指定目标平台
npx tauri build --target x86_64-pc-windows-msvc
npx tauri build --target aarch64-apple-darwin
npx tauri build --target x86_64-unknown-linux-gnu
```

构建产物位置：
- Windows: `src-tauri/target/release/bundle/msi/*.msi` + `bundle/nsis/*-setup.exe`
- macOS: `src-tauri/target/release/bundle/dmg/*.dmg`
- Linux: `src-tauri/target/release/bundle/appimage/*.AppImage`

#### 2.3.5 Windows 代码签名

```powershell
# 方式一：signtool（证书已安装）
signtool sign /a /fd sha256 /tr http://timestamp.digicert.com /td sha256 `
    "src-tauri/target/release/bundle/msi/pangu-nebula_2.1.0_x64_en-US.msi"

# 方式二：Tauri 集成签名（在 tauri.conf.json 中配置）
# "windows": {
#   "certificateThumbprint": "<证书指纹>",
#   "digestAlgorithm": "sha256",
#   "timestampUrl": "http://timestamp.digicert.com"
# }
```

#### 2.3.6 macOS 代码签名 + 公证

```bash
# 1. 签名
codesign --deep --force --verify --verbose=2 \
    --sign "Developer ID Application: Your Name (TEAM_ID)" \
    --options runtime \
    "Pangu Nebula.app"

# 2. 公证
xcrun notarytool submit "pangu-nebula.dmg" \
    --apple-id "you@example.com" \
    --team-id "TEAM_ID" \
    --password "app-specific-password" \
    --wait

# 3. 装订公证票据
xcrun stapler staple "pangu-nebula.dmg"
```

### 2.4 发布流程

#### 2.4.1 创建 Release

```bash
# 1. 确认所有改动已提交
git status

# 2. 创建版本 tag（触发 tauri-release.yml workflow）
git tag -a v2.1.0 -m "Release v2.1.0 - Phase 0 Tauri 2 壳迁移"

# 3. 推送 tag
git push origin v2.1.0

# 4. GitHub Actions 自动执行：
#    - prepare: 创建 Draft Release
#    - build: 四平台并行构建（含 sidecar 打包 + Tauri 签名）
#    - publish: 生成 latest.json + Draft → Published
```

#### 2.4.2 tauri-release.yml 工作流

**三阶段流水线**：
1. **prepare**（ubuntu-latest）：从 tag 提取版本元数据，创建 Draft Release
2. **build**（4 平台并行）：
   - Windows x86_64
   - macOS aarch64 (Apple Silicon)
   - macOS x86_64 (Intel, 使用 macos-13 runner)
   - Linux x86_64
3. **publish**（ubuntu-latest）：下载所有产物 → 生成 latest.json → Draft 转 Published

**缓存优化**：
- `swatinem/rust-cache@v2` 缓存 `~/.cargo` + `src-tauri/target`
- 按平台分隔 `key: ${{ matrix.target }}`
- 预计减少构建时间 50-70%

#### 2.4.3 必需 GitHub Secrets

| Secret 名称 | 用途 | 示例 |
|-------------|------|------|
| `TAURI_SIGNING_KEY` | Tauri updater Ed25519 私钥 | `untrusted:...` 格式 |
| `TAURI_SIGNING_KEY_PASSWORD` | 私钥密码 | `your-password` |
| `WINDOWS_CERT_FILE` | Windows PFX 证书（base64） | base64 编码 |
| `WINDOWS_CERT_PASSWORD` | PFX 证书密码 | `your-password` |
| `APPLE_CERTIFICATE` | macOS 开发者证书（base64） | base64 编码 |
| `APPLE_CERTIFICATE_PASSWORD` | 证书密码 | `your-password` |
| `APPLE_ID` | Apple 公证账号 | `you@example.com` |
| `APPLE_PASSWORD` | App-specific password | `app-specific-password` |
| `APPLE_TEAM_ID` | Apple Team ID | `TEAM123456` |

#### 2.4.4 latest.json 示例

```json
{
    "version": "2.1.0",
    "notes": "Pangu Nebula v2.1.0",
    "pub_date": "2026-07-13T10:00:00Z",
    "platforms": {
        "windows-x86_64": {
            "url": "https://github.com/pangu-nebula/pangu-nebula/releases/download/v2.1.0/pangu-nebula_2.1.0_x64_en-US.msi",
            "signature": "dW50cnVzdGVkIGNvbW1lbnQ6..."
        },
        "darwin-aarch64": {
            "url": "https://github.com/pangu-nebula/pangu-nebula/releases/download/v2.1.0/pangu-nebula_aarch64.dmg",
            "signature": "dW50cnVzdGVkIGNvbW1lbnQ6..."
        },
        "darwin-x86_64": {
            "url": "https://github.com/pangu-nebula/pangu-nebula/releases/download/v2.1.0/pangu-nebula_x86_64.dmg",
            "signature": "dW50cnVzdGVkIGNvbW1lbnQ6..."
        },
        "linux-x86_64": {
            "url": "https://github.com/pangu-nebula/pangu-nebula/releases/download/v2.1.0/pangu-nebula_2.1.0_amd64.AppImage",
            "signature": "dW50cnVzdGVkIGNvbW1lbnQ6..."
        }
    }
}
```

---

## 三、CI/CD 配置

### 3.1 Workflows

| Workflow | 文件 | 触发 | 用途 |
|----------|------|------|------|
| Tauri Release | `.github/workflows/tauri-release.yml` | `v2.1.*` tag | 三平台构建 + 发布 |
| Cross-Platform CI | `.github/workflows/ci-cross-platform.yml` | push/PR | 三平台测试 |
| Security | `.github/workflows/security.yml` | push/PR + 周期 | 依赖安全扫描 |

### 3.2 Cargo 依赖安全扫描

**cargo-audit**：RustSec 漏洞数据库扫描
```bash
cd src-tauri
cargo install cargo-audit --locked
cargo audit --deny warnings  # CI 中失败即阻断
```

**cargo-deny**：许可证 + 禁用依赖检查
```bash
cd src-tauri
cargo install cargo-deny --locked
cargo deny check licenses advisories bans
```

`deny.toml` 允许的许可证：
```toml
[licenses]
allow = [
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "ISC", "Zlib", "Unicode-DFS-2016", "Unicode-3.0",
    "CC0-1.0", "MPL-2.0",
]
```

---

## 四、运行时数据

### 4.1 数据目录

| 平台 | 路径 |
|------|------|
| Windows | `%APPDATA%\pangu-nebula\` |
| macOS | `~/Library/Application Support/pangu-nebula/` |
| Linux | `~/.local/share/pangu-nebula/` |

包含：
- `nebula.db`：SQLite 主数据库
- `cache/`：缓存数据
- `logs/`：运行日志
- `config.json`：用户配置

### 4.2 Sidecar 进程

| 平台 | 可执行文件位置 |
|------|--------------|
| Windows | `<安装目录>\resources\pangu-sidecar\pangu-nebula-sidecar.exe` |
| macOS | `Pangu Nebula.app/Contents/Resources/pangu-sidecar/pangu-nebula-sidecar` |
| Linux | `/opt/pangu-nebula/resources/pangu-sidecar/pangu-nebula-sidecar` |

### 4.3 IPC 通信

**端口协商协议**：
1. Tauri 启动时 spawn Python sidecar 子进程
2. Sidecar 绑定 `127.0.0.1:0`（OS 分配空闲端口）
3. Sidecar 通过 stdout 输出 `PORT=xxxxx\nTOKEN=yyyy\n`
4. Tauri 解析 PORT + TOKEN，注入 `window.__NEBULA_PORT__` + `window.__NEBULA_TOKEN__`
5. 前端 API 调用时附带 `Authorization: Bearer <TOKEN>` 头部

**IPC 边界**：
- CRUD 请求：经 Tauri `http_proxy` command（`invoke`）→ Rust reqwest 转发到 sidecar
- SSE 流式（apiStream）：前端直接 `fetch` 到 `http://127.0.0.1:PORT/...`（绕过 invoke，保持流式）

### 4.4 崩溃恢复

Sidecar Supervisor 监控：
- 进程存活检查：2s 间隔
- /health/ready 探针：5s 间隔
- 崩溃自动重启：1s → 2s → 4s 指数退避，上限 3 次
- 超限后显示 DegradedUI（降级 UI），用户可选重试或忽略

---

## 五、回退方案

### 5.1 切换到 PyWebView 模式

```bash
# Windows
set NEBULA_SHELL=pywebview
python launch.py

# macOS/Linux
NEBULA_SHELL=pywebview python launch.py
```

### 5.2 v2.0.x bugfix 分支

```bash
# 紧急回退到 v2.0.x
git checkout maint/v2.0.x
git pull
python launch.py  # 原 PyWebView 单进程模式
```

### 5.3 数据兼容性

SQLite 数据库格式 v2.0.x ↔ v2.1.x 完全兼容，无需迁移。

---

## 六、监控与诊断

### 6.1 日志位置

- **Tauri 主进程**：`<data_dir>/logs/tauri.log`
- **Python sidecar**：`<data_dir>/logs/sidecar.log`
- **前端**：浏览器 DevTools Console

### 6.2 健康检查

```bash
# 找到 sidecar 端口（从 tauri.log 读取）
PORT=$(grep "PORT=" <data_dir>/logs/tauri.log | tail -1 | cut -d= -f2)
TOKEN=$(grep "TOKEN=" <data_dir>/logs/tauri.log | tail -1 | cut -d= -f2)

# 健康检查
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:$PORT/health/ready

# 预期响应
# {"status":"ready","db_initialized":true,"services_loaded":true}
```

### 6.3 优雅关闭

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:$PORT/shutdown
```

---

## 附录：版本号管理

| 文件 | 字段 |
|------|------|
| `src-tauri/tauri.conf.json` | `version`（单一真相源） |
| `src-tauri/Cargo.toml` | `package.version` |
| `pyproject.toml` | `project.version` |
| `frontend/package.json` | `version` |
| `launch.py` | `VERSION` 常量 |

使用 `scripts/sync_version.py` 自动同步所有文件版本号。

---

**文档版本**: v1.0
**最后更新**: 2026-07-13
**维护者**: Pangu Nebula 团队
