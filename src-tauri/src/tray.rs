//! Pangu Nebula 系统托盘 (v2.1.0 Phase 0 — P0-W4)
//!
//! 职责:
//! 1. 创建系统托盘图标 (使用 app 默认窗口图标)
//! 2. 右键菜单: 显示主窗口 / 退出
//! 3. 左键单击: 切换窗口显示/隐藏
//! 4. 窗口关闭按钮拦截 → 隐藏到托盘 (而非退出应用)

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewWindow,
};

/// 菜单项 ID
const MENU_SHOW: &str = "show";
const MENU_QUIT: &str = "quit";

/// 设置系统托盘
///
/// 在 Tauri Builder.setup() 中调用。
/// 创建托盘图标 + 右键菜单 + 事件处理。
pub fn setup_tray(app: &AppHandle) -> Result<(), String> {
    // 1. 构建右键菜单
    let show_item = MenuItem::with_id(app, MENU_SHOW, "显示主窗口", true, None::<&str>)
        .map_err(|e| format!("Failed to create 'show' menu item: {}", e))?;
    let quit_item = MenuItem::with_id(app, MENU_QUIT, "退出", true, None::<&str>)
        .map_err(|e| format!("Failed to create 'quit' menu item: {}", e))?;

    let menu = Menu::with_items(app, &[&show_item, &quit_item])
        .map_err(|e| format!("Failed to create tray menu: {}", e))?;

    // 2. 构建托盘图标
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
                    tracing::info!("User quit from tray menu");
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            // 左键单击: 切换窗口显示/隐藏
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

/// 切换窗口可见性
///
/// 可见 → 隐藏
/// 隐藏 → 显示 + 聚焦
fn toggle_window_visibility(window: &WebviewWindow) {
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
        tracing::debug!("Window hidden (tray toggle)");
    } else {
        let _ = window.show();
        let _ = window.set_focus();
        tracing::debug!("Window shown (tray toggle)");
    }
}
