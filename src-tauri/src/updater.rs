//! Pangu Nebula 自动更新模块 (v2.1.0 Phase 0 — P0-W6.1)
//!
//! 职责:
//! 1. 封装 tauri-plugin-updater 的 check + download + install 流程
//! 2. 提供 Tauri command 供前端 invoke 调用
//! 3. 通过 emit 事件通知前端更新进度
//!
//! 前端调用方式:
//!   - invoke('check_for_update') → 检查是否有新版本
//!   - invoke('install_update') → 下载并安装 (重启后生效)
//!
//! 事件:
//!   - "update-available": { version, notes, date }
//!   - "update-progress": { downloaded, total } (下载进度)
//!   - "update-installed": {} (安装完成,等待重启)
//!   - "update-error": { error }

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::UpdaterExt;

/// 更新检查结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateInfo {
    /// 是否有可用更新
    pub available: bool,
    /// 新版本号 (如 "2.1.1")
    pub version: Option<String>,
    /// 更新说明
    pub notes: Option<String>,
    /// 发布日期 (ISO 8601 字符串)
    pub date: Option<String>,
}

/// 检查更新 (Tauri command)
///
/// 前端调用: invoke('check_for_update')
/// 返回 UpdateInfo JSON
#[tauri::command]
pub async fn check_for_update(app: AppHandle) -> Result<UpdateInfo, String> {
    tracing::info!("Checking for updates...");

    let updater = app.updater().map_err(|e| {
        let msg = format!("Failed to get updater: {}", e);
        tracing::error!("{}", msg);
        msg
    })?;

    match updater.check().await {
        Ok(Some(update)) => {
            // 将 OffsetDateTime 转为 ISO 8601 字符串
            let date_str = update.date.map(|d| {
                // 使用 UTC 格式化
                format!(
                    "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
                    d.year(),
                    d.month(),
                    d.day(),
                    d.hour(),
                    d.minute(),
                    d.second()
                )
            });

            let info = UpdateInfo {
                available: true,
                version: Some(update.version.clone()),
                notes: update.body.clone(),
                date: date_str.clone(),
            };
            tracing::info!(
                "Update available: v{} (date: {:?})",
                update.version,
                date_str
            );

            // 通知前端
            let _ = app.emit(
                "update-available",
                serde_json::json!({
                    "version": update.version,
                    "notes": update.body,
                    "date": date_str,
                }),
            );

            Ok(info)
        }
        Ok(None) => {
            tracing::info!("No updates available");
            Ok(UpdateInfo {
                available: false,
                version: None,
                notes: None,
                date: None,
            })
        }
        Err(e) => {
            let msg = format!("Update check failed: {}", e);
            tracing::error!("{}", msg);
            let _ = app.emit("update-error", serde_json::json!({ "error": &msg }));
            Err(msg)
        }
    }
}

/// 下载并安装更新 (Tauri command)
///
/// 前端调用: invoke('install_update')
/// 流程: check → download → install → emit "update-installed"
#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<(), String> {
    tracing::info!("Installing update...");

    let updater = app.updater().map_err(|e| {
        let msg = format!("Failed to get updater: {}", e);
        tracing::error!("{}", msg);
        msg
    })?;

    let update = updater
        .check()
        .await
        .map_err(|e| format!("Update check failed: {}", e))?
        .ok_or_else(|| "No update available".to_string())?;

    tracing::info!("Downloading update v{}", update.version);

    // 下载 + 安装
    // download_and_install 签名: (on_chunk: FnMut(usize, Option<u64>), on_download_finish: FnOnce())
    // on_chunk 回调参数: (chunk_len, content_length)
    let app_handle = app.clone();
    let mut downloaded: u64 = 0;

    update
        .download_and_install(
            move |chunk_len, content_length| {
                downloaded += chunk_len as u64;
                let _ = app_handle.emit(
                    "update-progress",
                    serde_json::json!({
                        "downloaded": downloaded,
                        "total": content_length.unwrap_or(0),
                    }),
                );
            },
            || {
                tracing::info!("Update download finished, installing...");
            },
        )
        .await
        .map_err(|e| {
            let msg = format!("Update install failed: {}", e);
            tracing::error!("{}", msg);
            let _ = app.emit("update-error", serde_json::json!({ "error": &msg }));
            msg
        })?;

    tracing::info!("Update installed, restart required");
    let _ = app.emit("update-installed", serde_json::json!({}));

    Ok(())
}
