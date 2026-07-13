//! Pangu Nebula Tauri 2 主进程库 (v2.1.0 Phase 0)
//!
//! P0-W2: 集成 sidecar supervisor — spawn Python + 端口协商 + /health/ready 轮询。
//! P0-W3: IPC 适配层 — invoke('http_proxy') → reqwest → Python sidecar (CRUD 走代理)。

use tracing_subscriber;

mod ipc;
mod sidecar;

use ipc::http_proxy;
use sidecar::{shutdown_sidecar, spawn_and_wait_ready, SidecarState};
use tauri::{Emitter, Manager};

/// 初始化日志订阅 (tracing + tracing-subscriber)
fn init_tracing() {
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .with_target(false)
        .init();
}

/// Tauri 应用入口
///
/// P0-W2: setup 钩子中 spawn Python sidecar + 等待 /health/ready 就绪。
/// 前端通过监听 "sidecar-ready" 事件获取 port/token。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_tracing();
    tracing::info!("Pangu Nebula Tauri shell starting (P0-W2 sidecar PoC)");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_fs::init())
        // P0-W6 将添加: .plugin(tauri_plugin_updater::init())
        .manage(SidecarState::default())
        .invoke_handler(tauri::generate_handler![http_proxy])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // 在独立线程中 spawn sidecar (避免阻塞 setup 钩子导致窗口不显示)
            // setup 钩子必须快速返回,Tauri 才能创建窗口
            tauri::async_runtime::spawn(async move {
                match spawn_and_wait_ready(&app_handle) {
                    Ok(handshake) => {
                        tracing::info!(
                            "Sidecar ready: port={}, token={}...",
                            handshake.port,
                            &handshake.token[..8]
                        );
                    }
                    Err(e) => {
                        tracing::error!("Sidecar spawn failed: {}", e);
                        app_handle
                            .emit("sidecar-error", serde_json::json!({ "error": e }))
                            .ok();
                    }
                }
            });

            tracing::info!("Tauri setup complete (sidecar spawning in background)");
            Ok(())
        })
        .on_window_event(|window, event| {
            // 窗口关闭时优雅关闭 sidecar
            if let tauri::WindowEvent::Destroyed = event {
                tracing::info!("Window destroyed, shutting down sidecar...");
                shutdown_sidecar(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
