//! Pangu Nebula IPC 适配层 (v2.1.0 Phase 0 — P0-W3)
//!
//! 职责: 将前端 `invoke('http_proxy', ...)` 请求转发到 Python sidecar。
//!
//! 前端 Tauri 模式下:
//! - CRUD 请求走 invoke → reqwest → sidecar (统一错误处理 + 无 CSP 限制)
//! - apiStream (SSE) 保留直连 fetch (流式必须直连, 不走 invoke)
//!
//! 设计要点:
//! - 从 SidecarState 读取 port/token (由 P0-W2 握手协议注入)
//! - 返回 ProxyResponse { ok, data, error } 与前端 ApiResponse<T> 对齐
//! - 错误返回 Err(String) (Tauri 会包装为 reject promise)

use crate::sidecar::{SidecarHandshake, SidecarState};
use serde::{Deserialize, Serialize};
use tauri::State;

/// IPC 代理响应 (与前端 ApiResponse 对齐)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyResponse {
    pub ok: bool,
    pub data: Option<serde_json::Value>,
    pub error: Option<String>,
}

/// HTTP 代理 command — 前端 `invoke('http_proxy', { method, path, body })`
///
/// 从 SidecarState 读取 port/token, 用 reqwest 转发请求到 Python sidecar。
/// 返回 `ProxyResponse` (与前端 `ApiResponse<T>` 对齐)。
///
/// # 参数
/// - `method`: HTTP 方法 (GET/POST/PUT/DELETE)
/// - `path`: API 路径 (如 "/chat/list", "/memory/search")
/// - `body`: 请求体 JSON (POST/PUT 使用, GET/DELETE 忽略)
/// - `state`: Tauri 管理的 SidecarState (含 port/token)
///
/// # 错误
/// - Sidecar 未就绪 (handshake 缺失)
/// - 不支持的 HTTP 方法
/// - sidecar 请求失败 (网络错误)
/// - sidecar 返回非 2xx 状态码
/// - 响应解析失败
#[tauri::command]
pub async fn http_proxy(
    method: String,
    path: String,
    body: Option<serde_json::Value>,
    state: State<'_, SidecarState>,
) -> Result<ProxyResponse, String> {
    // 1. 从 state 读取 handshake (clone 后立即释放锁)
    let handshake = {
        let guard = state.handshake.lock().unwrap();
        guard
            .clone()
            .ok_or_else(|| "Sidecar not ready (handshake missing)".to_string())?
    };

    let url = format!("http://127.0.0.1:{}{}", handshake.port, path);
    tracing::debug!("IPC proxy: {} {} (body={})", method, url, body.is_some());

    // 2. 构建 reqwest 请求
    let client = reqwest::Client::new();
    let req = match method.as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url).json(&body),
        "PUT" => client.put(&url).json(&body),
        "DELETE" => client.delete(&url),
        _ => return Err(format!("Unsupported HTTP method: {}", method)),
    };

    // 3. 附加 Bearer token (sidecar 中间件校验)
    let req = req.header("Authorization", format!("Bearer {}", handshake.token));

    // 4. 发送请求
    let resp = req
        .send()
        .await
        .map_err(|e| format!("IPC proxy request failed: {}", e))?;

    let status = resp.status();
    if !status.is_success() {
        // 尝试读取错误响应体
        let body_text = resp.text().await.unwrap_or_default();
        return Err(format!(
            "Sidecar returned HTTP {}: {}",
            status,
            body_text.chars().take(500).collect::<String>()
        ));
    }

    // 5. 解析响应
    //    优先识别统一格式 { ok, data, error };
    //    对于非统一格式 (如 /health 返回 {"status":"ok"}),
    //    基于 HTTP status 判断成功, 整个响应体作为 data 返回。
    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse sidecar response as JSON: {}", e))?;

    if let Some(ok_flag) = json.get("ok").and_then(|v| v.as_bool()) {
        // 统一格式响应
        Ok(ProxyResponse {
            ok: ok_flag,
            data: json.get("data").cloned(),
            error: json
                .get("error")
                .and_then(|v| v.as_str())
                .map(String::from),
        })
    } else {
        // 非统一格式响应 (如 /health, /health/ready)
        // HTTP status 已确认成功 (上面已校验), 整个响应体作为 data 返回
        Ok(ProxyResponse {
            ok: true,
            data: Some(json),
            error: None,
        })
    }
}

/// 获取 sidecar 握手信息 (port + token)
///
/// 前端通过 `invoke('get_sidecar_handshake')` 获取 sidecar 的 port 和 token。
/// 用于解决 sidecar-ready 事件的 fire-and-forget 竞态问题:
/// 如果事件在 listen() 注册前发出, 前端可通过此命令主动获取。
///
/// 返回:
/// - `Some({ port, token })` — sidecar 已就绪
/// - `None` — sidecar 尚未就绪
#[tauri::command]
pub async fn get_sidecar_handshake(
    state: State<'_, SidecarState>,
) -> Result<Option<serde_json::Value>, String> {
    let guard = state.handshake.lock().unwrap();
    Ok(guard.as_ref().map(|h: &SidecarHandshake| {
        serde_json::json!({
            "port": h.port,
            "token": h.token,
        })
    }))
}
