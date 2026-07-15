//! Pangu Nebula Sidecar Supervisor (v2.1.0 Phase 0 — P0-W5)
//!
//! 职责:
//! 1. 崩溃检测: 定期检查 sidecar 子进程存活状态 (2s 间隔)
//! 2. 指数退避重启: 1s → 2s → 4s, 上限 3 次
//! 3. 优雅关闭: POST /shutdown → 5s → kill (fallback)
//! 4. 降级通知: 重启超限后 emit "sidecar-degraded" 事件
//!
//! 设计要点:
//! - supervisor 在独立线程中运行,不阻塞主线程
//! - 使用 SidecarState 存储 retry_count (Mutex<u32>)
//! - 重启成功后 retry_count 重置为 0
//! - 崩溃检测两种方式:
//!   a) 主动轮询 child.try_wait() (2s 间隔)
//!   b) 主动轮询 /health/ready (5s 间隔,检测 sidecar 卡死)

use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

use crate::sidecar::{spawn_and_wait_ready, SidecarState};

/// 最大重启次数 (超过后触发降级 UI)
const MAX_RESTART_RETRIES: u32 = 3;

/// 崩溃检测轮询间隔
const CRASH_CHECK_INTERVAL: Duration = Duration::from_secs(2);

/// 健康检查轮询间隔
const HEALTH_CHECK_INTERVAL: Duration = Duration::from_secs(5);

/// 优雅关闭超时 (POST /shutdown 后等待)
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);

/// Supervisor 状态 (存入 Tauri app.state)
pub struct SupervisorState {
    /// 当前重启次数 (0 = 正常, >=3 = 降级)
    pub retry_count: Mutex<u32>,
    /// 是否正在关闭 (避免关闭时触发重启)
    pub shutting_down: Mutex<bool>,
}

impl Default for SupervisorState {
    fn default() -> Self {
        Self {
            retry_count: Mutex::new(0),
            shutting_down: Mutex::new(false),
        }
    }
}

/// 启动 supervisor 监控线程
///
/// 在 sidecar 启动成功后调用。监控线程定期检查:
/// 1. 子进程是否存活 (try_wait)
/// 2. /health/ready 是否响应 (检测卡死)
///
/// 崩溃后触发指数退避重启。超过 MAX_RESTART_RETRIES 后 emit "sidecar-degraded"。
pub fn start_supervisor(app: AppHandle) {
    tracing::info!("Sidecar supervisor started (crash check {}s, health check {}s)",
        CRASH_CHECK_INTERVAL.as_secs(), HEALTH_CHECK_INTERVAL.as_secs());

    tauri::async_runtime::spawn(async move {
        let mut last_health_check = Instant::now();

        loop {
            // 检查是否正在关闭 (避免关闭时触发重启)
            {
                let shutting_down = app.state::<SupervisorState>();
                let is_shutting_down = *shutting_down.shutting_down.lock().unwrap();
                if is_shutting_down {
                    tracing::info!("Supervisor: shutting down, stopping monitor loop");
                    break;
                }
            }

            // 1. 检查子进程存活
            let child_exited = {
                let state = app.state::<SidecarState>();
                let mut child_guard = state.child.lock().unwrap();
                if let Some(ref mut child) = *child_guard {
                    match child.try_wait() {
                        Ok(Some(status)) => {
                            tracing::warn!("Sidecar process exited: {}", status);
                            true
                        }
                        Ok(None) => false, // 仍在运行
                        Err(e) => {
                            tracing::error!("Failed to check sidecar status: {}", e);
                            true // 视为崩溃
                        }
                    }
                } else {
                    false // 无子进程 (可能正在重启)
                }
            };

            if child_exited {
                // 子进程退出,触发重启
                tracing::warn!("Sidecar crashed, attempting restart...");
                match restart_with_backoff(&app).await {
                    Ok(()) => {
                        tracing::info!("Sidecar restarted successfully");
                        continue; // 重启成功,继续监控
                    }
                    Err(e) => {
                        tracing::error!("Sidecar restart failed: {}", e);
                        // 重启失败,检查是否超限
                        let supervisor_state = app.state::<SupervisorState>();
                        let retry_count = *supervisor_state.retry_count.lock().unwrap();
                        if retry_count >= MAX_RESTART_RETRIES {
                            tracing::error!("Sidecar restart retries exhausted ({}), emitting sidecar-degraded", retry_count);
                            let _ = app.emit("sidecar-degraded", serde_json::json!({
                                "error": e,
                                "retry_count": retry_count,
                            }));
                            break; // 退出 supervisor
                        }
                    }
                }
            }

            // 2. 定期健康检查 (检测 sidecar 卡死但进程未退出)
            if last_health_check.elapsed() > HEALTH_CHECK_INTERVAL {
                check_sidecar_health(&app).await;
                last_health_check = Instant::now();
            }

            // 等待下一次检查
            tokio::time::sleep(CRASH_CHECK_INTERVAL).await;
        }

        tracing::info!("Sidecar supervisor loop ended");
    });
}

/// 指数退避重启 sidecar
///
/// 退避策略: 1s → 2s → 4s (2^retry_count)
/// 重启成功后 retry_count 重置为 0
/// 超过 MAX_RESTART_RETRIES 后返回 Err
async fn restart_with_backoff(app: &AppHandle) -> Result<(), String> {
    // 使用块作用域确保 MutexGuard 在 await 前 drop (Send 约束)
    let (delay_secs, current_retry) = {
        let supervisor_state = app.state::<SupervisorState>();
        let mut retry_count = supervisor_state.retry_count.lock().unwrap();

        if *retry_count >= MAX_RESTART_RETRIES {
            return Err(format!(
                "Max restart retries ({}) exceeded",
                MAX_RESTART_RETRIES
            ));
        }

        let delay_secs = 2u64.pow(*retry_count); // 1s → 2s → 4s
        *retry_count += 1;
        let current_retry = *retry_count;
        (delay_secs, current_retry)
    }; // guard 在此 drop

    tracing::info!(
        "Restarting sidecar (attempt {}/{}, delay {}s)",
        current_retry,
        MAX_RESTART_RETRIES,
        delay_secs
    );

    tokio::time::sleep(Duration::from_secs(delay_secs)).await;

    // 清理旧的子进程 (如果还存在)
    {
        let state = app.state::<SidecarState>();
        let mut child_guard = state.child.lock().unwrap();
        if let Some(mut child) = child_guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    // 重新 spawn sidecar
    match spawn_and_wait_ready(app).await {
        Ok(_) => {
            // 重启成功,重置 retry_count
            let supervisor_state = app.state::<SupervisorState>();
            *supervisor_state.retry_count.lock().unwrap() = 0;
            Ok(())
        }
        Err(e) => Err(format!("Restart failed: {}", e)),
    }
}

/// 检查 sidecar 健康状态 (/health/ready)
///
/// 如果 /health/ready 无响应,可能 sidecar 卡死,需要重启。
async fn check_sidecar_health(app: &AppHandle) {
    let state = app.state::<SidecarState>();
    let handshake = {
        let guard = state.handshake.lock().unwrap();
        match guard.clone() {
            Some(h) => h,
            None => return, // sidecar 未就绪,跳过
        }
    };

    let url = format!("http://127.0.0.1:{}/health/ready", handshake.port);
    // async reqwest (避免在 async 上下文中使用 blocking 导致 panic)
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();

    match client.get(&url).send().await {
        Ok(resp) if resp.status().is_success() => {
            tracing::debug!("Health check OK: /health/ready 200");
        }
        Ok(resp) => {
            tracing::warn!("Health check warning: /health/ready returned {}", resp.status());
        }
        Err(e) => {
            tracing::warn!("Health check failed: /health/ready error: {}", e);
            // 注意: 健康检查失败不直接触发重启 (可能是临时网络问题)
            // 只有子进程退出才触发重启
        }
    }
}

/// 优雅关闭 sidecar
///
/// 流程:
/// 1. 标记 shutting_down = true (阻止 supervisor 重启)
/// 2. POST /shutdown (带 Bearer token)
/// 3. 等待 5s
/// 4. 如果进程还活着, kill
pub async fn graceful_shutdown(app: &AppHandle) {
    tracing::info!("Graceful shutdown initiated");

    // 1. 标记正在关闭
    let supervisor_state = app.state::<SupervisorState>();
    *supervisor_state.shutting_down.lock().unwrap() = true;

    // 2. 获取 handshake (port + token)
    let handshake = {
        let state = app.state::<SidecarState>();
        let guard = state.handshake.lock().unwrap();
        guard.clone()
    };

    if let Some(handshake) = handshake {
        // 3. POST /shutdown
        let url = format!("http://127.0.0.1:{}/shutdown", handshake.port);
        let client = reqwest::Client::new();
        match client
            .post(&url)
            .header("Authorization", format!("Bearer {}", handshake.token))
            .send()
            .await
        {
            Ok(resp) => {
                tracing::info!("POST /shutdown responded: {}", resp.status());
            }
            Err(e) => {
                tracing::warn!("POST /shutdown failed: {}", e);
            }
        }

        // 4. 等待优雅关闭
        tokio::time::sleep(GRACEFUL_SHUTDOWN_TIMEOUT).await;
    }

    // 5. 如果进程还活着, kill (fallback)
    let state = app.state::<SidecarState>();
    let mut child_guard = state.child.lock().unwrap();
    if let Some(mut child) = child_guard.take() {
        match child.try_wait() {
            Ok(None) => {
                tracing::warn!("Sidecar still alive after graceful shutdown, killing...");
                let _ = child.kill();
                let _ = child.wait();
            }
            Ok(Some(_)) => {
                tracing::info!("Sidecar exited gracefully");
            }
            Err(e) => {
                tracing::error!("Failed to check sidecar status during shutdown: {}", e);
                let _ = child.kill();
            }
        }
    }

    tracing::info!("Graceful shutdown complete");
}
