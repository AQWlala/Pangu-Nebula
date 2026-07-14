//! Pangu Nebula system tray (v2.1.6)
//!
//! Refactored with QuitFlag pattern from nomifun-tauri:
//! - "Quit" menu item sets QuitFlag before closing the window
//! - Window close is then handled by lib.rs on_window_event

use std::sync::atomic::Ordering;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewWindow,
};

use crate::lib::QuitFlag;

const MENU_SHOW: &str = "show";
const MENU_QUIT: &str = "quit";

/// Set up the system tray with Show/Quit menu
pub fn setup_tray(app: &AppHandle) -> Result<(), String> {
    let show_item = MenuItem::with_id(app, MENU_SHOW, "Show Window", true, None::<&str>)
        .map_err(|e| format!("Failed to create 'show' menu item: {}", e))?;
    let quit_item = MenuItem::with_id(app, MENU_QUIT, "Quit", true, None::<&str>)
        .map_err(|e| format!("Failed to create 'quit' menu item: {}", e))?;

    let menu = Menu::with_items(app, &[&show_item, &quit_item])
        .map_err(|e| format!("Failed to create tray menu: {}", e))?;

    let icon = app
        .default_window_icon()
        .ok_or("No default window icon found")?
        .clone();

    TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .tooltip("Pangu Nebula")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| {
            match event.id().as_ref() {
                MENU_SHOW => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                MENU_QUIT => {
                    tracing::info!("User clicked Quit from tray menu");
                    // Set QuitFlag so lib.rs knows this is a real exit
                    let quit_flag = app.state::<QuitFlag>();
                    quit_flag.0.store(true, Ordering::SeqCst);

                    if let Some(window) = app.get_webview_window("main") {
                        // Close the window — Destroyed event will trigger shutdown + exit
                        let _ = window.close();
                    } else {
                        // No window exists — exit immediately
                        app.exit(0);
                    }
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    toggle_window_visibility(&window);
                }
            }
        })
        .build(app)
        .map_err(|e| format!("Failed to build tray icon: {}", e))?;

    tracing::info!("System tray initialized");
    Ok(())
}

/// Toggle window visibility: visible → hide, hidden → show + focus
fn toggle_window_visibility(window: &WebviewWindow) {
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        let _ = window.show();
        let _ = window.set_focus();
    }
}
