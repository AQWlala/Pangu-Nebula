//! Pangu Nebula Sidecar Supervisor (v2.1.0 Phase 0 — P0-W2)
//!
//! 职责:
//! 1. spawn Python sidecar 子进程 (打包环境用 PyInstaller exe,开发环境用 python launch.py)
//! 2. 读取子进程 stdout,解析 PORT=/TOKEN=/READY 握手协议
//! 3. 轮询 /health/ready 就绪检测 (200ms 间隔, 10s 超时)
//! 4. 通过 Tauri 事件将 port/token 注入前端
//! 5. (P0-W4 将添加) 崩溃检测 + 指数退避重启
//! 6. (P0-W5 将添加) 优雅关闭 (POST /shutdown)
//!
//! 端口协商协议:
//!   Python sidecar 启动时 stdout 输出:
//!     PORT=12345
//!     TOKEN=<64 hex chars>
//!     READY
//!   Tauri 主进程逐行读取并解析。

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

/// Sidecar 握手信息 (由 Python stdout 解析得到)
#[derive(Debug, Clone)]
pub struct SidecarHandshake {
    pub port: u16,
    pub token: String,
}

/// Sidecar 全局状态 (存入 Tauri app.state 供后续 IPC 转发使用)
pub struct SidecarState {
    pub handshake: Mutex<Option<SidecarHandshake>>,
    pub child: Mutex<Option<Child>>,
}

impl Default for SidecarState {
    fn default() -> Self {
        Self {
            handshake: Mutex::new(None),
            child: Mutex::new(None),
        }
    }
}

/// 启动 Python sidecar 子进程并解析 stdout 握手协议
///
/// 流程:
/// 1. spawn `python launch.py` (env: NEBULA_SHELL=tauri)
/// 2. 逐行读取 stdout,解析 PORT=/TOKEN=/READY
/// 3. 超时 15s 未收到 READY 返回错误
/// 4. 将 handshake 存入 app.state,emit "sidecar-ready" 事件
/// 5. 轮询 /health/ready 就绪检测 (200ms 间隔, 10s 超时)
/// 6. emit "sidecar-health" 事件通知前端后端就绪
pub fn spawn_and_wait_ready(app: &AppHandle) -> Result<SidecarHandshake, String> {
    tracing::info!("Spawning Python sidecar (NEBULA_SHELL=tauri)...");

    // 1. 确定 sidecar 可执行文件路径
    //    打包环境: <resource_dir>/pangu-sidecar/pangu-nebula-sidecar/pangu-nebula-sidecar[.exe]
    //    开发环境: python launch.py (fallback)
    let (program, args, cwd): (PathBuf, Vec<String>, Option<PathBuf>) = {
        match app.path().resource_dir() {
            Ok(resource_dir) => {
                let sidecar_dir = resource_dir
                    .join("pangu-sidecar")
                    .join("pangu-nebula-sidecar");
                let sidecar_exe = sidecar_dir.join(format!(
                    "pangu-nebula-sidecar{}",
                    std::env::consts::EXE_SUFFIX
                ));

                if sidecar_exe.exists() {
                    tracing::info!(
                        "Using bundled sidecar: {}",
                        sidecar_exe.display()
                    );
                    // onedir 模式: CWD 设为 sidecar 目录,确保 PyInstaller 能找到同目录依赖
                    (sidecar_exe, vec![], Some(sidecar_dir))
                } else {
                    tracing::warn!(
                        "Bundled sidecar not found at {}, falling back to python launch.py",
                        sidecar_exe.display()
                    );
                    (PathBuf::from("python"), vec!["launch.py".to_string()], None)
                }
            }
            Err(e) => {
                tracing::warn!(
                    "resource_dir() failed ({}), falling back to python launch.py",
                    e
                );
                (PathBuf::from("python"), vec!["launch.py".to_string()], None)
            }
        }
    };

    // 2. spawn 子进程
    let mut command = Command::new(&program);
    for arg in &args {
        command.arg(arg);
    }
    if let Some(dir) = &cwd {
        command.current_dir(dir);
    }
    // Windows: 隐藏 PyInstaller --console 模式产生的控制台窗口
    // stdout/stderr 仍可通过 piped 读取,仅阻止可见窗口
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let mut child = command
        .env("NEBULA_SHELL", "tauri")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar ({}): {}", program.display(), e))?;

    // 2. 读取 stdout 解析握手协议
    let stdout = child
        .stdout
        .take()
        .ok_or("Failed to capture sidecar stdout")?;
    let handshake = parse_handshake(stdout)?;

    tracing::info!(
        "Sidecar handshake received: port={}, token={}...",
        handshake.port,
        &handshake.token[..8]
    );

    // 3. 存入 app.state
    let state = app.state::<SidecarState>();
    *state.handshake.lock().unwrap() = Some(handshake.clone());
    *state.child.lock().unwrap() = Some(child);

    // 4. emit "sidecar-ready" 事件 (前端监听后注入 window.__NEBULA_PORT__/__NEBULA_TOKEN__)
    app.emit(
        "sidecar-ready",
        serde_json::json!({
            "port": handshake.port,
            "token": handshake.token,
        }),
    )
    .map_err(|e| format!("Failed to emit sidecar-ready: {}", e))?;

    // 5. 轮询 /health/ready 就绪检测
    poll_health_ready(&handshake)?;

    // 6. emit "sidecar-health" 事件
    app.emit("sidecar-health", serde_json::json!({ "status": "ready" }))
        .map_err(|e| format!("Failed to emit sidecar-health: {}", e))?;

    tracing::info!("Sidecar is ready and healthy");
    Ok(handshake)
}

/// 解析 sidecar stdout 握手协议
///
/// 期望格式 (逐行):
///   PORT=12345
///   TOKEN=<64 hex chars>
///   READY
///
/// 超时 15s。
fn parse_handshake<R: std::io::Read>(stdout: R) -> Result<SidecarHandshake, String> {
    let reader = BufReader::new(stdout);
    let start = Instant::now();
    let timeout = Duration::from_secs(15);

    let mut port: Option<u16> = None;
    let mut token: Option<String> = None;

    for line_result in reader.lines() {
        if start.elapsed() > timeout {
            return Err("Sidecar handshake timeout (15s)".to_string());
        }

        let line = line_result.map_err(|e| format!("Failed to read sidecar stdout: {}", e))?;
        tracing::debug!("sidecar stdout: {}", line);

        if let Some(rest) = line.strip_prefix("PORT=") {
            port = Some(rest.trim().parse::<u16>().map_err(|e| {
                format!("Invalid PORT value '{}': {}", rest, e)
            })?);
        } else if let Some(rest) = line.strip_prefix("TOKEN=") {
            token = Some(rest.trim().to_string());
        } else if line.trim() == "READY" {
            // 握手完成
            let port = port.ok_or("Handshake READY received but PORT not set")?;
            let token = token.ok_or("Handshake READY received but TOKEN not set")?;
            if token.len() != 64 {
                return Err(format!(
                    "Invalid token length: expected 64, got {}",
                    token.len()
                ));
            }
            return Ok(SidecarHandshake { port, token });
        }
    }

    Err("Sidecar stdout closed before READY signal".to_string())
}

/// 轮询 /health/ready 就绪检测
///
/// 间隔 200ms, 超时 10s。返回 Ok 表示 sidecar 已就绪。
fn poll_health_ready(handshake: &SidecarHandshake) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{}/health/ready", handshake.port);
    let start = Instant::now();
    let timeout = Duration::from_secs(10);
    let interval = Duration::from_millis(200);

    tracing::info!("Polling {} (200ms interval, 10s timeout)...", url);

    // 同步阻塞轮询 (在 setup 钩子中,阻塞是预期的)
    // 使用 ureq 或 reqwest blocking 客户端;这里用 reqwest::blocking
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(1))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

    while start.elapsed() < timeout {
        match client.get(&url).send() {
            Ok(resp) if resp.status().is_success() => {
                tracing::debug!("/health/ready returned 200");
                return Ok(());
            }
            Ok(resp) => {
                tracing::debug!("/health/ready returned status: {}", resp.status());
            }
            Err(e) => {
                tracing::debug!("/health/ready connection failed: {}", e);
            }
        }
        std::thread::sleep(interval);
    }

    Err(format!(
        "Sidecar /health/ready timeout (10s) at {}",
        url
    ))
}

/// 优雅关闭 sidecar (P0-W5 将扩展为 POST /shutdown)
///
/// 当前实现: kill 子进程。P0-W5 将改为先 POST /shutdown 再 wait + fallback kill。
#[allow(dead_code)]
pub fn shutdown_sidecar(app: &AppHandle) {
    let state = app.state::<SidecarState>();
    let mut child_guard = state.child.lock().unwrap();
    if let Some(mut child) = child_guard.take() {
        tracing::info!("Shutting down sidecar...");
        // P0-W5: 先尝试 POST /shutdown,等 2s,再 kill
        let _ = child.kill();
        let _ = child.wait();
        tracing::info!("Sidecar shut down");
    }
}
