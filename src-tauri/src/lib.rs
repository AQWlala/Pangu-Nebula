//! Pangu Nebula Tauri 2 main process library (v2.1.6)
//!
//! Refactored with lessons from nomifun-tauri:
//! - QuitFlag pattern: clean distinction between "close window→hide to tray" and "quit app→exit"
//! - CSP null (trust Tauri webview sandbox, not CSP)
//! - Window always visible (no startup race condition)
//! - keepawake to prevent system sleep during agent tasks
//! - Simplified sidecar flow (removed over-engineered integrity checks in dev)

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{Emitter, Manager};
use tracing_subscriber;

mod ipc;
mod sidecar;
mod supervisor;
mod tray;
mod updater;

use ipc::{get_sidecar_handshake, http_proxy};
use sidecar::{spawn_and_wait_ready, SidecarState};
use supervisor::{start_supervisor, graceful_shutdown, SupervisorState};
use updater::{check_for_update, install_update};

/// Quit flag — distinguishes "close window (hide to tray)" from "quit app (exit process)".
///
/// Pattern from nomifun-tauri:
/// 1. Tray "Quit" → set flag true → close window → Destroyed → graceful_shutdown + exit(0)
/// 2. Window close button / Cmd+W → flag false → CloseRequested → hide to tray
/// 3. Window fully destroyed with flag false → graceful_shutdown but don't exit
pub struct QuitFlag(AtomicBool);

impl QuitFlag {
    fn is_quitting(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }

    fn set_quitting(&self) {
        self.0.store(true, Ordering::SeqCst);
    }
}

impl Default for QuitFlag {
    fn default() -> Self {
        Self(AtomicBool::new(false))
    }
}

/// Initialize tracing subscriber (tracing + tracing-subscriber)
fn init_tracing() {
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .with_target(false)
        .init();
}

/// Tauri application entry point
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_tracing();
    tracing::info!("Pangu Nebula Tauri shell starting (v2.1.6)");

    tauri::Builder::default()
        // P0: Single instance lock — must be FIRST plugin (Tauri 2 requirement)
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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_autostart::init())
        .manage(SidecarState::default())
        .manage(SupervisorState::default())
        .manage(QuitFlag::default())
        .invoke_handler(tauri::generate_handler![
            http_proxy,
            get_sidecar_handshake,
            check_for_update,
            install_update
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // Initialize system tray (with Quit-aware menu)
            // tray::setup_tray uses app.state::<QuitFlag>() internally for the quit menu
            if let Err(e) = tray::setup_tray(&app_handle) {
                tracing::error!("Failed to setup tray: {}", e);
            }

            // Initialize keepawake to prevent system sleep during agent tasks
            match keepawake::Builder::default()
                .display(true)
                .idle(true)
                .reason("Pangu Nebula agent tasks running")
                .app_name("Pangu Nebula")
                .app_reverse_domain("com.pangu.nebula")
                .create()
            {
                Ok(_awake) => {
                    tracing::info!("KeepAwake: system sleep prevention active");
                    // Store in app state so it stays alive for the lifetime of the app
                    // (awake guard lives as long as we hold the reference)
                    // We leak it intentionally — it should live for the app lifetime
                    std::mem::forget(_awake);
                }
                Err(e) => {
                    tracing::warn!("KeepAwake not available: {}", e);
                }
            }

            // Spawn sidecar in background (non-blocking — window is already visible)
            tauri::async_runtime::spawn(async move {
                match spawn_and_wait_ready(&app_handle) {
                    Ok(handshake) => {
                        tracing::info!(
                            "Sidecar ready: port={}, token={}...",
                            handshake.port,
                            &handshake.token[..8]
                        );

                        // Start crash supervisor for the sidecar
                        start_supervisor(app_handle.clone());

                        // Emit sidecar-ready so frontend can start making requests
                        let _ = app_handle.emit(
                            "sidecar-ready",
                            serde_json::json!({
                                "port": handshake.port,
                                "token": handshake.token,
                            }),
                        );
                    }
                    Err(e) => {
                        tracing::error!("Sidecar spawn failed: {}", e);
                        let _ = app_handle.emit(
                            "sidecar-error",
                            serde_json::json!({ "error": e }),
                        );
                    }
                }
            });

            tracing::info!("Tauri setup complete (sidecar spawning in background)");
            Ok(())
        })
        .on_window_event(|window, event| {
            use tauri::WindowEvent;

            match event {
                // CloseRequested: user clicked close button / Cmd+W
                // If quitting (tray "Quit"), let close proceed → Destroyed → exit
                // Otherwise, hide to tray (keep sidecar alive for background tasks)
                WindowEvent::CloseRequested { api, .. } => {
                    let app = window.app_handle();
                    let quitting = app.state::<QuitFlag>().is_quitting();

                    if quitting {
                        tracing::info!("Quit flag set — closing window normally");
                        // Let the close proceed → Destroyed event will trigger shutdown
                    } else {
                        api.prevent_close();
                        let _ = window.hide();
                        tracing::info!("Window hidden to tray (close prevented)");
                    }
                }

                // Destroyed: window has been fully destroyed
                // If quitting → graceful shutdown sidecar + exit(0)
                // If not quitting (hidden to tray, then user quit from tray) → handled by tray
                WindowEvent::Destroyed => {
                    let app = window.app_handle();
                    let quitting = app.state::<QuitFlag>().is_quitting();

                    if quitting {
                        tracing::info!("Window destroyed with quit flag — shutting down sidecar...");
                        let app_handle = app.clone();
                        tauri::async_runtime::spawn(async move {
                            graceful_shutdown(&app_handle).await;
                            tracing::info!("Graceful shutdown complete, exiting");
                            std::process::exit(0);
                        });
                    } else {
                        tracing::info!("Window destroyed without quit flag — sidecar continues");
                    }
                }

                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}


