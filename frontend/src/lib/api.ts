// 统一 API 客户端 - 与后端 FastAPI (http://127.0.0.1:7860) 交互
// 所有响应遵循统一格式: { ok: bool, data: ..., error: ... }

export const API_BASE = "http://127.0.0.1:7860"

interface ApiResponse<T> {
  ok: boolean
  data: T
  error: string | null
}

/** 发送 HTTP 请求并解析统一响应格式 */
async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const url = `${API_BASE}${path}`
  const options: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  }
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
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
