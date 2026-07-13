// 统一 API 客户端
// v2.1.0 Phase 0: 支持 Tauri sidecar 模式 (动态端口 + Bearer token)
//
// 双模式工作:
// 1. PyWebView 模式 (v2.0.x): 固定 http://127.0.0.1:7860,无 token
// 2. Tauri sidecar 模式 (v2.1.0+): 监听 sidecar-ready 事件获取动态 PORT/TOKEN
//
// 前端启动时:
// - 检测 window.__NEBULA_PORT__ (由 Tauri 主进程注入)
// - 若存在,使用动态端口 + Bearer token
// - 若不存在,回退到固定 7860 端口 (PyWebView 模式)

// 检测 Tauri 环境 (window.__TAURI__ 或 window.__TAURI_INTERNALS__)
declare global {
  interface Window {
    __NEBULA_PORT__?: number
    __NEBULA_TOKEN__?: string
    __TAURI__?: any
    __TAURI_INTERNALS__?: any
  }
}

/** 是否运行在 Tauri sidecar 模式 */
export const IS_TAURI =
  typeof window !== "undefined" &&
  (window.__TAURI__ !== undefined || window.__TAURI_INTERNALS__ !== undefined)

/** API 基础 URL: Tauri 模式动态端口,否则固定 7860 */
function getApiBase(): string {
  if (IS_TAURI && window.__NEBULA_PORT__) {
    return `http://127.0.0.1:${window.__NEBULA_PORT__}`
  }
  return "http://127.0.0.1:7860"
}

/** Bearer token: Tauri 模式从 window.__NEBULA_TOKEN__ 读取,否则空 */
function getAuthToken(): string {
  if (IS_TAURI && window.__NEBULA_TOKEN__) {
    return window.__NEBULA_TOKEN__
  }
  return ""
}

// 向后兼容: 导出 API_BASE (PyWebView 模式固定值)
// 注意: Tauri 模式下应使用 getApiBase() 动态获取
export const API_BASE = "http://127.0.0.1:7860"

interface ApiResponse<T> {
  ok: boolean
  data: T
  error: string | null
}

/** 发送 HTTP 请求并解析统一响应格式 */
async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const baseUrl = getApiBase()
  const url = `${baseUrl}${path}`
  const token = getAuthToken()

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  // Tauri sidecar 模式下附加 Bearer token
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const options: RequestInit = { method, headers }
  if (body !== undefined) {
    options.body = JSON.stringify(body)
  }
  const res = await fetch(url, options)
  const json: ApiResponse<T> = await res.json()
  if (!json.ok) {
    throw new Error(json.error || "请求失败")
  }
  return json.data
}

/** GET 请求,返回 data 字段 */
export async function apiGet<T>(path: string): Promise<T> {
  return request<T>("GET", path)
}

/** POST 请求,返回 data 字段 */
export async function apiPost<T>(path: string, body?: any): Promise<T> {
  return request<T>("POST", path, body)
}

/** PUT 请求,返回 data 字段 */
export async function apiPut<T>(path: string, body?: any): Promise<T> {
  return request<T>("PUT", path, body)
}

/** DELETE 请求,返回 data 字段 */
export async function apiDelete<T>(path: string): Promise<T> {
  return request<T>("DELETE", path)
}

/** SSE 流式请求 - 用 fetch + ReadableStream 解析 data: 行 */
export async function apiStream(
  path: string,
  body: any,
  onChunk: (text: string) => void
): Promise<void> {
  const baseUrl = getApiBase()
  const url = `${baseUrl}${path}`
  const token = getAuthToken()

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  })
  if (!res.body) throw new Error("无响应流")

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith("data: ")) {
        const data = trimmed.slice(6)
        if (data === "[DONE]") return
        onChunk(data)
      }
    }
  }
}

/**
 * 初始化 sidecar 事件监听 (仅 Tauri 模式)
 *
 * 监听 Tauri 主进程 emit 的 "sidecar-ready" 事件,
 * 将 port/token 注入 window.__NEBULA_PORT__/__NEBULA_TOKEN__。
 * 在 main.tsx 入口处调用此函数。
 */
export async function initSidecarListener(): Promise<void> {
  if (!IS_TAURI) return

  // 动态导入 Tauri event API (避免 PyWebView 模式下加载失败)
  try {
    const { listen } = await import("@tauri-apps/api/event")

    // 监听 sidecar-ready 事件
    await listen<{ port: number; token: string }>("sidecar-ready", (event) => {
      const { port, token } = event.payload
      window.__NEBULA_PORT__ = port
      window.__NEBULA_TOKEN__ = token
      console.log(`[sidecar] Ready: port=${port}, token=${token.slice(0, 8)}...`)
    })

    // 监听 sidecar-health 事件 (后端 /health/ready 就绪)
    await listen<{ status: string }>("sidecar-health", (event) => {
      console.log(`[sidecar] Health: ${event.payload.status}`)
    })

    // 监听 sidecar-error 事件
    await listen<{ error: string }>("sidecar-error", (event) => {
      console.error(`[sidecar] Error: ${event.payload.error}`)
    })

    console.log("[sidecar] Event listeners registered")
  } catch (e) {
    console.warn("[sidecar] Failed to register Tauri event listeners:", e)
  }
}
