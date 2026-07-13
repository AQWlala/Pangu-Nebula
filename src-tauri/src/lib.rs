//! Pangu Nebula Tauri 2 主进程库 (v2.1.0 Phase 0)
//!
//! P0-W1: 脚手架骨架 — 仅初始化 Tauri 应用 + 注册插件，无 sidecar 集成。
//! Sidecar 启动器、端口协商、IPC 转发将在 P0-W2 实现。

use tracing_subscriber;

// P0-W2 将在此引入 sidecar supervisor 模块
// mod sidecar;
// mod ipc;

/// 初始化日志订阅 (tracing + tracing-subscriber)
fn init_tracing() {
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .with_target(false)
        .init();
}

/// Tauri 应用入口 — P0-W1 骨架版本
///
/// P0-W1: 仅注册插件 + 打开窗口，无 sidecar 集成。
/// P0-W2 将添加 sidecar 启动 + 端口协商 + /health/ready 轮询。
/// P0-W3 将添加 IPC 转发 (invoke → reqwest → Python)。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_tracing();
    tracing::info!("Pangu Nebula Tauri shell starting (P0-W1 scaffold)");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_fs::init())
        // P0-W6 将添加: .plugin(tauri_plugin_updater::init())
        .setup(|_app| {
            tracing::info!("Tauri setup complete (P0-W1 scaffold — no sidecar yet)");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
