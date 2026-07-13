/**
 * lib/api.ts 双实现单元测试 (v2.1.0 Phase 0 — P0-W3.5)
 *
 * 测试双模式分支:
 * - Tauri 模式: request() 调用 invoke('http_proxy', ...)
 * - 浏览器模式: request() 调用 fetch
 * - apiStream 两种模式都走 fetch (SSE 必须直连)
 *
 * 注意: 此测试需要 vitest 配置才能运行。当前项目未配置 vitest,
 * 此文件作为代码结构存在,后续配置 vitest 后可直接运行。
 *
 * 配置步骤 (未来):
 * 1. npm install -D vitest @testing-library/preact jsdom
 * 2. vitest.config.ts: { test: { environment: 'jsdom' } }
 * 3. package.json: "test": "vitest run"
 */

// @ts-nocheck  (vitest 未安装, 类型检查跳过; 配置 vitest 后移除此行)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// Mock invoke (Tauri API)
const mockInvoke = vi.fn()
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}))

// Mock @tauri-apps/api/event (initSidecarListener 使用)
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn().mockResolvedValue(() => vi.fn()),
}))

// 导入被测模块 (必须在 mock 之后)
import {
  getApiBase,
  getAuthToken,
  apiGet,
  apiPost,
  apiPut,
  apiDelete,
  apiStream,
} from "../api"

// ----------------------------------------------------------------------
// 工具: 切换 Tauri / 浏览器模式
// ----------------------------------------------------------------------

function setTauriMode(enabled: boolean, port?: number, token?: string) {
  if (enabled) {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      value: {},
      configurable: true,
    })
    if (port) (window as any).__NEBULA_PORT__ = port
    if (token) (window as any).__NEBULA_TOKEN__ = token
  } else {
    delete (window as any).__TAURI_INTERNALS__
    delete (window as any).__NEBULA_PORT__
    delete (window as any).__NEBULA_TOKEN__
  }
}

// ----------------------------------------------------------------------
// 测试
// ----------------------------------------------------------------------

describe("api.ts 双实现", () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    vi.restoreAllMocks()
    setTauriMode(false)
  })

  afterEach(() => {
    setTauriMode(false)
  })

  // --- getApiBase ---

  describe("getApiBase()", () => {
    it("浏览器模式: 返回固定 7860", () => {
      setTauriMode(false)
      expect(getApiBase()).toBe("http://127.0.0.1:7860")
    })

    it("Tauri 模式: 返回动态端口", () => {
      setTauriMode(true, 12345, "fake-token")
      expect(getApiBase()).toBe("http://127.0.0.1:12345")
    })

    it("Tauri 模式但未注入 PORT: 回退到 7860", () => {
      setTauriMode(true)
      expect(getApiBase()).toBe("http://127.0.0.1:7860")
    })
  })

  // --- getAuthToken ---

  describe("getAuthToken()", () => {
    it("浏览器模式: 返回空字符串", () => {
      setTauriMode(false)
      expect(getAuthToken()).toBe("")
    })

    it("Tauri 模式: 返回注入的 token", () => {
      setTauriMode(true, 12345, "my-secret-token")
      expect(getAuthToken()).toBe("my-secret-token")
    })
  })

  // --- request() Tauri 模式 ---

  describe("Tauri 模式 CRUD (invoke http_proxy)", () => {
    it("apiGet: 调用 invoke('http_proxy') 并返回 data", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({
        ok: true,
        data: { items: [1, 2, 3] },
        error: null,
      })

      const result = await apiGet<{ items: number[] }>("/test/list")
      expect(mockInvoke).toHaveBeenCalledWith("http_proxy", {
        method: "GET",
        path: "/test/list",
        body: undefined,
      })
      expect(result).toEqual({ items: [1, 2, 3] })
    })

    it("apiPost: 传递 body 到 invoke", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({
        ok: true,
        data: { id: 42 },
        error: null,
      })

      const result = await apiPost<{ id: number }>("/test/create", {
        name: "test",
      })
      expect(mockInvoke).toHaveBeenCalledWith("http_proxy", {
        method: "POST",
        path: "/test/create",
        body: { name: "test" },
      })
      expect(result).toEqual({ id: 42 })
    })

    it("apiPut: 传递 body 到 invoke", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({
        ok: true,
        data: { updated: true },
        error: null,
      })

      await apiPut("/test/1", { name: "updated" })
      expect(mockInvoke).toHaveBeenCalledWith("http_proxy", {
        method: "PUT",
        path: "/test/1",
        body: { name: "updated" },
      })
    })

    it("apiDelete: 不传递 body", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({
        ok: true,
        data: { deleted: true },
        error: null,
      })

      await apiDelete("/test/1")
      expect(mockInvoke).toHaveBeenCalledWith("http_proxy", {
        method: "DELETE",
        path: "/test/1",
        body: undefined,
      })
    })

    it("invoke 返回 ok=false: 抛出错误", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({
        ok: false,
        data: null,
        error: "Not found",
      })

      await expect(apiGet("/test/missing")).rejects.toThrow("Not found")
    })

    it("invoke 返回 ok=false 且 error=null: 抛出默认错误", async () => {
      setTauriMode(true, 12345, "token-abc")
      mockInvoke.mockResolvedValue({ ok: false, data: null, error: null })

      await expect(apiGet("/test/fail")).rejects.toThrow("请求失败")
    })
  })

  // --- request() 浏览器模式 ---

  describe("浏览器模式 CRUD (fetch 直连)", () => {
    it("apiGet: 调用 fetch 并返回 data", async () => {
      setTauriMode(false)
      const mockFetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({ ok: true, data: { hello: "world" }, error: null }),
      })
      vi.stubGlobal("fetch", mockFetch)

      const result = await apiGet<{ hello: string }>("/test/hello")
      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:7860/test/hello",
        expect.objectContaining({ method: "GET" })
      )
      expect(result).toEqual({ hello: "world" })
    })

    it("apiPost: fetch 包含 body", async () => {
      setTauriMode(false)
      const mockFetch = vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ ok: true, data: {}, error: null }),
      })
      vi.stubGlobal("fetch", mockFetch)

      await apiPost("/test/create", { x: 1 })
      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:7860/test/create",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ x: 1 }),
        })
      )
    })

    it("fetch 返回 ok=false: 抛出错误", async () => {
      setTauriMode(false)
      const mockFetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({ ok: false, data: null, error: "Server error" }),
      })
      vi.stubGlobal("fetch", mockFetch)

      await expect(apiGet("/test/fail")).rejects.toThrow("Server error")
    })
  })

  // --- apiStream (两种模式都走 fetch) ---

  describe("apiStream (SSE 直连, 不走 invoke)", () => {
    it("Tauri 模式: apiStream 走 fetch (不走 invoke)", async () => {
      setTauriMode(true, 12345, "stream-token")
      const chunks = ["data: hello", "data: world", "data: [DONE]"]

      // Mock ReadableStream
      const encoder = new TextEncoder()
      const mockFetch = vi.fn().mockResolvedValue({
        body: {
          getReader: () => {
            let i = 0
            return {
              read: () => {
                if (i < chunks.length) {
                  return Promise.resolve({
                    done: false,
                    value: encoder.encode(chunks[i++] + "\n"),
                  })
                }
                return Promise.resolve({ done: true, value: undefined })
              },
            }
          },
        },
      })
      vi.stubGlobal("fetch", mockFetch)

      const received: string[] = []
      await apiStream("/chat/stream", { msg: "hi" }, (chunk) => {
        received.push(chunk)
      })

      // apiStream 不应调用 invoke
      expect(mockInvoke).not.toHaveBeenCalled()
      // 应该调用 fetch (直连 sidecar 动态端口)
      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:12345/chat/stream",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Authorization: "Bearer stream-token",
          }),
        })
      )
      // 应该收到 hello 和 world ([DONE] 触发 return)
      expect(received).toEqual(["hello", "world"])
    })
  })
})
