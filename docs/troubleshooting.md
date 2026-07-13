# Pangu Nebula 故障排查指南 v1.0

> **版本**: v2.1.0 | **创建日期**: 2026-07-13
> **适用范围**: Tauri 2 + Python sidecar 双进程架构
> **关联文档**: [部署指南](./deployment-guide.md) | [Phase 0 规范](./v2.1.0-phase0-spec.md)

---

## 一、启动类问题

### 1.1 应用无法启动 / 启动后立即崩溃

**症状**：双击图标无反应，或启动后立即退出

**排查步骤**：

1. **检查 Tauri 主进程日志**
   ```
   Windows: %APPDATA%\pangu-nebula\logs\tauri.log
   macOS:   ~/Library/Application Support/pangu-nebula/logs/tauri.log
   Linux:   ~/.local/share/pangu-nebula/logs/tauri.log
   ```

2. **检查 sidecar 完整性**
   - 定位 sidecar 目录（参见部署指南 §4.2）
   - 检查 `sidecar.sha256` 清单是否存在
   - 手动校验：
     ```bash
     # Linux/macOS
     sha256sum -c sidecar.sha256
     # Windows (PowerShell)
     Get-FileHash pangu-nebula-sidecar.exe -Algorithm SHA256
     ```
   - **如校验失败**：sidecar 被篡改或损坏，需重新安装

3. **命令行启动查看错误**
   ```bash
   # Windows
   "C:\Program Files\Pangu Nebula\Pangu Nebula.exe"
   # macOS
   /Applications/"Pangu Nebula.app"/Contents/MacOS/"Pangu Nebula"
   # Linux
   /opt/pangu-nebula/pangu-nebula
   ```

**常见原因**：
- ✅ sidecar 二进制损坏 → 重新安装
- ✅ 杀毒软件误杀 → 添加白名单
- ✅ 缺少 Visual C++ Redistributable（Windows）→ 安装 VC++ 2015-2022
- ✅ 缺少 WebView2 Runtime（Windows）→ 从微软官网下载安装

---

### 1.2 Sidecar 启动失败

**症状**：应用窗口可见但功能不可用，DegradedUI 降级界面出现

**排查步骤**：

1. **检查 sidecar 日志**
   ```
   <data_dir>/logs/sidecar.log
   ```

2. **手动启动 sidecar 验证**
   ```bash
   cd <安装目录>/resources/pangu-sidecar
   NEBULA_SHELL=tauri ./pangu-nebula-sidecar
   # 预期输出:
   # PORT=xxxxx
   # TOKEN=yyyyy
   # INFO:     Uvicorn running on http://127.0.0.1:xxxxx
   ```

3. **检查端口冲突**
   - Sidecar 使用 OS 动态分配端口（`127.0.0.1:0`），不应冲突
   - 但防火墙可能阻止本地回环连接 → 检查防火墙规则

**常见错误**：

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `ModuleNotFoundError: No module named 'xxx'` | PyInstaller 打包遗漏模块 | 重新打包并添加 `--hidden-import=xxx` |
| `Address already in use` | 端口被占用（理论上不应发生） | 重启 Tauri 让其重新分配端口 |
| `Permission denied` | 可执行文件无执行权限 | `chmod +x pangu-nebula-sidecar`（Linux/macOS） |
| `sidecar.sha256 not found` | 完整性清单缺失 | 重新安装或运行 `gen_sidecar_hash.py` |
| `Integrity check failed` | sidecar 被篡改 | 重新安装应用 |

---

### 1.3 端口协商失败

**症状**：Tauri 日志显示 "Failed to parse PORT from sidecar stdout"

**排查步骤**：

1. **检查 stdout 握手协议**
   - Sidecar 必须按格式输出：`PORT=xxxxx\nTOKEN=yyyyy\n`
   - 顺序：PORT 行在前，TOKEN 行在后
   - 必须使用 `\n` 换行（非 `\r\n`）
   - 必须在 stdout 输出（非 stderr）

2. **手动测试**
   ```bash
   NEBULA_SHELL=tauri python launch.py
   # 应看到前两行:
   # PORT=54321
   # TOKEN=abc123...
   ```

3. **检查 PyInstaller 打包模式**
   - 必须使用 `--console`（Windows）保留 stdout
   - 不能使用 `--windowed` 或 `--noconsole`

**修复**：
- 如果 stdout 被其他日志污染，调整 Python logging 配置，确保启动握手前不输出其他内容
- Tauri 端解析超时默认 10s，过慢的 sidecar 启动需优化（如延迟加载非核心服务）

---

### 1.4 WebView2 缺失（Windows）

**症状**：启动报错 "WebView2 Runtime not found"

**解决方案**：

1. **方式一：自动安装**
   - 下载 `Microsoft Edge WebView2 Runtime` 离线安装包
   - 地址：https://developer.microsoft.com/microsoft-edge/webview2/

2. **方式二：Tauri 集成**
   - `tauri.conf.json` 已配置 `"webviewInstallMode": {"type": "downloadBootstrapper"}`
   - 首次启动会自动下载 bootstrapper 并安装

3. **方式三：企业部署**
   ```powershell
   # 静默安装 WebView2
   MicrosoftEdgeWebview2Setup.exe /silent /install
   ```

---

## 二、运行时问题

### 2.1 API 调用 401 未授权

**症状**：前端所有 API 调用返回 401 Unauthorized

**原因**：Bearer token 校验失败

**排查**：

1. **检查 token 是否正确注入**
   ```javascript
   // 浏览器 DevTools Console
   console.log(window.__NEBULA_TOKEN__)  // 应为非空字符串
   ```

2. **检查请求头**
   ```javascript
   // DevTools Network 面板
   // 检查请求是否携带: Authorization: Bearer <token>
   ```

3. **手动验证**
   ```bash
   # 无 token（应返回 401）
   curl http://127.0.0.1:PORT/health/ready
   # 有 token（应返回 200）
   curl -H "Authorization: Bearer TOKEN" http://127.0.0.1:PORT/health/ready
   ```

**修复**：
- 重启应用（token 每次 Tauri 启动时重新生成）
- 检查 `frontend/src/lib/api.ts` 中 TOKEN 读取逻辑

---

### 2.2 SSE 流式对话无响应

**症状**：聊天面板发送消息后无打字机效果，但 CRUD 接口正常

**原因**：SSE 直连链路问题

**排查**：

1. **检查 API_BASE 拼接**
   ```javascript
   // apiStream 必须直连 sidecar，不走 invoke
   // DevTools Network 中应看到: http://127.0.0.1:PORT/api/chat/stream
   // 而非: tauri://localhost/api/chat/stream
   ```

2. **检查 CSP 配置**
   - `tauri.conf.json` 中 `connect-src` 必须包含 `http://127.0.0.1:*`
   - 当前配置：`connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* ipc: http://ipc.localhost https://*`

3. **检查 sidecar 是否支持 SSE**
   ```bash
   curl -N -H "Authorization: Bearer TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"message":"hello"}' \
        http://127.0.0.1:PORT/api/chat/stream
   # 应看到流式输出 data: {...}\n\n
   ```

**修复**：
- 确保 `apiStream` 函数未误用 `invoke`
- 检查 CSP 中 `connect-src` 是否包含 `http://127.0.0.1:*`

---

### 2.3 Sidecar 反复崩溃重启

**症状**：DegradedUI 出现，日志显示多次重启记录

**排查**：

1. **查看 sidecar 日志定位崩溃原因**
   ```
   <data_dir>/logs/sidecar.log
   ```

2. **检查重启间隔**
   - 正常指数退避：1s → 2s → 4s
   - 超过 3 次后停止重启，显示 DegradedUI

3. **常见崩溃原因**：
   - 数据库文件损坏 → 备份后删除 `nebula.db` 重新创建
   - 第三方 API 密钥过期 → 检查配置文件
   - 内存不足 → 关闭其他应用释放内存

**应急处理**：
- 点击 DegradedUI 的"重试"按钮（重新触发重启序列）
- 或点击"忽略"按钮（继续使用受限功能）
- 实在无法恢复 → 切换 PyWebView 模式：`NEBULA_SHELL=pywebview python launch.py`

---

### 2.4 托盘图标不显示

**症状**：应用启动后系统托盘无图标

**平台差异**：
- **Windows**：可能被折叠到隐藏图标区，点击 `^` 展开查看
- **macOS**：顶部菜单栏右侧
- **Linux**：取决于桌面环境（GNOME 需扩展支持）

**修复**：
- Windows：任务栏设置 → 选择哪些图标显示在任务栏上 → 启用 Pangu Nebula
- Linux GNOME：安装 `AppIndicator` 扩展
- 检查 `src-tauri/src/lib.rs` 中 `TrayIconBuilder` 配置

---

### 2.5 单实例锁失效

**症状**：可以启动多个应用实例

**预期行为**：第二次启动应聚焦已有窗口，而非启动新实例

**排查**：
```rust
// src-tauri/src/lib.rs
tauri_plugin_single_instance::init(|app, _argv, _cwd| {
    let _ = app.get_webview_window("main").map(|w| {
        w.show().unwrap();
        w.set_focus().unwrap();
    });
})
```

**修复**：确保 `tauri-plugin-single-instance` 已正确注册

---

## 三、构建类问题

### 3.1 cargo tauri build 失败

**症状**：Tauri 构建报错

**常见错误**：

#### 错误 1：缺少 sidecar 产物
```
error: resource 'resources/pangu-sidecar/' not found
```

**修复**：
```bash
# 必须先构建 sidecar
python scripts/build_sidecar.py
# 然后构建 Tauri
npx tauri build
```

#### 错误 2：Linux WebKitGTK 版本
```
error: webkit2gtk-4.0 not found
```

**修复**：
```bash
# Tauri 2 要求 WebKitGTK 4.1
sudo apt-get install -y libwebkit2gtk-4.1-dev
```

#### 错误 3：Rust 编译失败
```
error[E0106]: missing lifetime specifier
```

**修复**：
```bash
# 确认 Rust 版本
rustc --version  # 应 >= 1.75.0
rustup update stable

# 清理缓存重新构建
cargo clean
npx tauri build
```

#### 错误 4：PyInstaller 模块缺失
```
ModuleNotFoundError: No module named 'uvicorn.loops.auto'
```

**修复**：在 `scripts/build_sidecar.py` 中添加 `--hidden-import`
```python
pyinstaller_args += [
    "--hidden-import=uvicorn.loops.auto",
    "--hidden-import=uvicorn.logging",
    # ...
]
```

---

### 3.2 签名失败

**症状**：`npx tauri build` 报签名错误

#### Windows 代码签名
```
error: SignTool Error: No certificates were found
```

**修复**：
- 确保证书已安装到 Current User/Local Machine 证书存储
- 或在 `tauri.conf.json` 中配置 `certificateThumbprint`
- 测试模式：将 `certificateThumbprint` 留空（跳过代码签名，仅 updater 签名）

#### Tauri updater 签名
```
error: TAURI_SIGNING_KEY not set
```

**修复**：
```bash
# 生成密钥对
tauri signer generate -w ~/.tauri/pangu-nebula.key
# 公钥写入 tauri.conf.json > plugins.updater.pubkey
# 私钥存入 GitHub Secrets: TAURI_SIGNING_KEY

# 本地构建时设置环境变量
export TAURI_SIGNING_KEY="<private-key-content>"
export TAURI_SIGNING_KEY_PASSWORD="<password>"
```

---

### 3.3 版本号不一致

**症状**：CI 中 `sync_version.py --check` 失败

**原因**：手动修改了一个文件的版本号，未同步其他文件

**修复**：
```bash
# 自动同步所有文件到 tauri.conf.json 的版本号
python scripts/sync_version.py

# 或指定版本号
python scripts/sync_version.py --version 2.1.0

# 再次检查
python scripts/sync_version.py --check
```

涉及文件：
- `src-tauri/tauri.conf.json`（单一真相源）
- `src-tauri/Cargo.toml`
- `pyproject.toml`
- `frontend/package.json`
- `launch.py`

---

### 3.4 Rust 模块双目标编译失败

**症状**：`cargo build --lib --features python` 失败

**原因**：PyO3 版本 API 变化

**修复**（PyO3 0.22 适配）：
```rust
// 旧 API（0.21）
#[pymodule]
fn module(py: Python, m: &PyModule) -> PyResult<()> { ... }

// 新 API（0.22+）
#[pymodule]
fn module(m: &Bound<'_, PyModule>) -> PyResult<()> { ... }

// 函数签名注解
#[pyfunction(signature = (text, threshold=0.5))]
fn find_text(text: &str, threshold: f64) -> PyResult<Vec<Match>> { ... }
```

参考：commit `566167b` — 适配 PyO3 0.22 API 修复 Rust 模块编译

---

## 四、性能问题

### 4.1 启动缓慢

**目标**：窗口可见 < 500ms，功能可用 < 3s

**排查**：
1. Tauri 主进程启动 → 计时
2. Sidecar spawn → stdout 输出 PORT → 计时
3. /health/ready 返回 200 → 计时

**优化方向**：
- 延迟加载非核心服务（如 RAG 索引、记忆压缩）
- 使用 `--onedir` 模式（比 `--onefile` 启动快）
- 预编译 Python 字节码：`python -m compileall server/`

### 4.2 内存占用过高

**目标**：空闲状态 < 250MB

**排查**：
- 任务管理器（Windows）/ Activity Monitor（macOS）/ `top`（Linux）
- Tauri 主进程 + Python sidecar 两个进程总和

**优化方向**：
- Python：检查是否有未释放的对象、大对象缓存
- Rust：使用 `tracing` 分析内存分配
- 参考值：v2.1.0 实测 190-260MB（双进程架构固有开销）

### 4.3 IPC 延迟过高

**目标**：p95 < 10ms

**排查**：
```bash
# 简单基准测试
for i in {1..100}; do
    curl -w "%{time_total}\n" -o /dev/null -s \
         -H "Authorization: Bearer $TOKEN" \
         http://127.0.0.1:$PORT/health/ready
done | sort -n | tail -5  # 查看 p95
```

**优化方向**：
- CRUD 走 invoke 有额外 Rust 中转开销，约 1-3ms
- SSE 必须直连，避免 invoke 破坏流式
- 大数据量响应考虑分页

---

## 五、安全相关

### 5.1 Sidecar 完整性校验失败

**症状**：Tauri 启动时拒绝启动 sidecar

**原因**：sidecar 二进制被篡改或 `sidecar.sha256` 清单不匹配

**修复**：
```bash
# 重新生成清单
python scripts/gen_sidecar_hash.py --output sidecar.sha256 --root .

# 或重新安装应用（推荐）
```

**安全建议**：
- 不要手动修改 sidecar 二进制
- 杀毒软件可能误报，需添加白名单
- 仅从官方 Releases 下载

### 5.2 Bearer token 泄露风险

**风险**：token 出现在前端代码或日志中

**防护**：
- token 仅在 Tauri 启动时生成一次，存储在 `window.__NEBULA_TOKEN__`
- 不会写入磁盘日志（仅 stdout 握手时短暂存在）
- 应用关闭后 token 失效

**排查**：
```bash
# 检查日志是否泄露 token
grep -r "TOKEN=" <data_dir>/logs/
# 预期：无输出（仅 Tauri stdout 临时存在）
```

---

## 六、回退方案

### 6.1 切换到 PyWebView 模式

```bash
# 完全绕过 Tauri，使用原 v2.0.x 单进程模式
# Windows
$env:NEBULA_SHELL="pywebview"
python launch.py

# macOS/Linux
NEBULA_SHELL=pywebview python launch.py
```

适用场景：
- Tauri 构建环境问题
- WebView2 无法安装
- 临时调试需要直接访问 Python 后端

### 6.2 回退到 v2.0.x

```bash
# 切换到 bugfix 分支
git checkout maint/v2.0.x
git pull origin maint/v2.0.x

# 运行 v2.0.x
python launch.py
```

数据兼容性：v2.0.x ↔ v2.1.x SQLite 格式完全兼容，无需迁移。

---

## 七、获取帮助

### 7.1 收集诊断信息

提交 issue 前请收集：

```bash
# 1. 系统信息
# Windows
systeminfo | findstr /B /C:"OS" /C:"System"
# macOS
sw_vers
# Linux
lsb_release -a

# 2. 应用版本
"Pangu Nebula.exe" --version

# 3. 日志文件
# 打包: <data_dir>/logs/ 下的所有 .log 文件

# 4. Sidecar 信息
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:$PORT/health/ready
```

### 7.2 常用诊断命令速查

```bash
# Tauri 启动（开发模式，查看详细日志）
RUST_LOG=debug cargo tauri dev

# Sidecar 单独启动
NEBULA_SHELL=tauri python launch.py

# 完整 pytest 回归
pytest tests/ -v

# Rust 模块测试
pytest tests/test_rust_modules.py -v

# 前端构建验证
cd frontend && npm run build

# 版本号一致性检查
python scripts/sync_version.py --check

# Sidecar 完整性校验
sha256sum -c sidecar.sha256  # Linux/macOS
```

---

## 附录：错误码对照表

| 错误码 | 含义 | 处理建议 |
|--------|------|---------|
| `SIDECAR_SPAWN_FAILED` | Sidecar 进程启动失败 | 检查可执行文件权限和路径 |
| `SIDECAR_TIMEOUT` | Sidecar 启动超时（10s） | 查看 sidecar.log 排查启动慢的原因 |
| `SIDECAR_INTEGRITY_FAIL` | 完整性校验失败 | 重新安装应用 |
| `PORT_NEGOTIATION_FAIL` | 端口协商失败 | 检查 stdout 握手协议 |
| `SIDECAR_CRASH_LIMIT` | 崩溃超过 3 次上限 | 查看 sidecar.log 定位崩溃原因 |
| `TOKEN_AUTH_FAIL` | Bearer token 认证失败 | 重启应用重新生成 token |
| `WEBVIEW2_MISSING` | WebView2 运行时缺失 | 安装 WebView2 Runtime |
| `CARGO_AUDIT_FAIL` | Rust 依赖有漏洞 | 更新依赖版本 |

---

**文档版本**: v1.0
**最后更新**: 2026-07-13
**维护者**: Pangu Nebula 团队
