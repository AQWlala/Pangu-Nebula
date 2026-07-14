//! Pangu Nebula Tauri 2 主进程库 (v2.1.0 Phase 0)
//!
//! P0-W2: 集成 sidecar supervisor — spawn Python + 端口协商 + /health/ready 轮询。
//! P0-W3: IPC 适配层 — invoke('http_proxy') → reqwest → Python sidecar (CRUD 走代理)。
//! P0-W4: 窗口/托盘 — 系统托盘 + 单实例锁 + 最小化到托盘 + sidecar 就绪后显示窗口。
//! P0-W5: Sidecar Supervisor — 崩溃检测 + 指数退避重启 + 优雅关闭 + 降级通知。
//! P0-W6: 自动更新 — tauri-plugin-updater + check_for_update/install_update command。

use tracing_subscriber;

mod ipc;
mod integrity;
mod sidecar;
mod supervisor;
mod tray;
mod updater;

use ipc::{get_sidecar_handshake, http_proxy};
use sidecar::{spawn_and_wait_ready, SidecarState};
use supervisor::{start_supervisor, graceful_shutdown, SupervisorState};
use updater::{check_for_update, install_update};
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
/// P0-W4: 单实例锁 + 系统托盘 + 最小化到托盘。
/// 前端通过监听 "sidecar-ready" 事件获取 port/token。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_tracing();
    tracing::info!("Pangu Nebula Tauri shell starting (P0-W5 supervisor)");

    tauri::Builder::default()
        // P0-W4.3: 单实例锁 — 必须第一个注册 (Tauri 2 要求)
        // 第二次启动时聚焦已有窗口
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                tracing::info!("Single instance: focused existing window");
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_fs::init())
        // P0-W6.1: 自动更新插件 (tauri-plugin-updater)
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(SidecarState::default())
        .manage(SupervisorState::default())
        .invoke_handler(tauri::generate_handler![http_proxy, get_sidecar_handshake, check_for_update, install_update])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // P0-W4.2: 初始化系统托盘
            if let Err(e) = tray::setup_tray(&app_handle) {
                tracing::error!("Failed to setup tray: {}", e);
            }

            // 在独立线程中 spawn sidecar (避免阻塞 setup 钩子导致窗口不显示)
            // setup 钩子必须快速返回,Tauri 才能创建窗口
            tauri::async_runtime::spawn(async move {
                // P0-W5.1: 启动前完整性校验 (失败则拒绝启动 sidecar)
                if !integrity::check_and_emit(&app_handle) {
                    tracing::error!("Sidecar integrity check failed, refusing to start");
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.show();
                    }
                    return;
                }

                match spawn_and_wait_ready(&app_handle) {
                    Ok(handshake) => {
                        tracing::info!(
                            "Sidecar ready: port={}, token={}...",
                            handshake.port,
                            &handshake.token[..8]
                        );

                        // P0-W5: sidecar 就绪后启动 supervisor (崩溃检测 + 指数退避重启)
                        start_supervisor(app_handle.clone());

                        // P0-W4: sidecar 就绪后显示主窗口
                        // (tauri.conf.json 中 visible:false, 启动时隐藏)
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                            tracing::info!("Main window shown (sidecar ready)");
                        }
                    }
                    Err(e) => {
                        tracing::error!("Sidecar spawn failed: {}", e);
                        app_handle
                            .emit("sidecar-error", serde_json::json!({ "error": e }))
                            .ok();
                        // sidecar 失败也显示窗口 (让用户看到错误)
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let _ = window.show();
                        }
                    }
                }
            });

            tracing::info!("Tauri setup complete (sidecar spawning in background)");
            Ok(())
        })
        .on_window_event(|window, event| {
            // P0-W4.3: 最小化到托盘 — 拦截关闭按钮,隐藏而非退出
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
                tracing::info!("Window close prevented, hidden to tray");
            }

            // P0-W5: 窗口真正销毁时 (托盘退出) 优雅关闭 sidecar
            // graceful_shutdown 是 async,需 spawn 异步执行
            if let tauri::WindowEvent::Destroyed = event {
                tracing::info!("Window destroyed, gracefully shutting down sidecar...");
                let app_handle = window.app_handle().clone();
                tauri::async_runtime::spawn(async move {
                    graceful_shutdown(&app_handle).await;
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
