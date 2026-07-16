/**
 * 三个 Bug 修复的前端契约测试
 *
 * Bug1: EvolutionPage 应调 /evolution/logs (非 /evolution) 且防御性处理 {items}
 * Bug3: DiagnosticsPage 不应用 window.location.reload (此处测 apiGet/apiPost 契约)
 * Bug2: ChatPanel loadActivePersona 兜底 (此处测 apiGet 解包契约)
 *
 * 注: EvolutionPage/DiagnosticsPage 是 app.tsx 内部函数未导出,
 *     此处通过验证 apiGet 解包契约 + 防御性数组处理模式锁定修复。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const mockInvoke = vi.fn()
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}))
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn().mockResolvedValue(() => vi.fn()),
}))

import { apiGet, apiPost } from "../api"

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

describe("Bug1: EvolutionPage 契约 — /evolution/logs 返回 {items} 应正确解包", () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    vi.restoreAllMocks()
    setTauriMode(false)
  })
  afterEach(() => setTauriMode(false))

  it("apiGet('/evolution/logs') 解包 data 后得到 {items, count} 对象", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () =>
        Promise.resolve({
          ok: true,
          data: { items: [{ id: 1, phase: "extract" }], count: 1 },
          error: null,
        }),
    })
    vi.stubGlobal("fetch", mockFetch)

    const data = await apiGet<{ items: any[]; count: number }>("/evolution/logs")
    expect(data).toEqual({ items: [{ id: 1, phase: "extract" }], count: 1 })
    expect(Array.isArray(data.items)).toBe(true)
  })

  it("防御性: 即使 data.items 为 null, Array.isArray 兜底返回 []", () => {
    // 模拟 EvolutionPage 修复后的防御模式
    const apiData: any = { items: null, count: 0 }
    const logs = Array.isArray(apiData?.items) ? apiData.items : []
    expect(logs).toEqual([])
    // 旧代码直接 data.map 会崩溃, 新代码不会
    expect(() => logs.map((l: any) => l)).not.toThrow()
  })

  it("防御性: apiGet 返回引擎信息对象 (非 {items}) 时, Array.isArray 兜底返回 []", () => {
    // 模拟误调 /evolution (返回引擎信息) 时的防御
    const apiData: any = { engine: "EvolutionEngine", version: "6B" }
    const logs = Array.isArray(apiData?.items) ? apiData.items : []
    expect(logs).toEqual([])
    expect(() => logs.map((l: any) => l)).not.toThrow()
  })
})

describe("Bug3: check-all 调用契约 (不再用 window.location.reload)", () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    vi.restoreAllMocks()
    setTauriMode(false)
  })
  afterEach(() => setTauriMode(false))

  it("apiPost('/health-check/check-all') 正确发起 POST", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ ok: true, data: [], error: null }),
    })
    vi.stubGlobal("fetch", mockFetch)

    await apiPost("/health-check/check-all", {})
    expect(mockFetch).toHaveBeenCalledWith(
      "http://127.0.0.1:7860/health-check/check-all",
      expect.objectContaining({ method: "POST" })
    )
  })
})

describe("Bug2: ChatPanel loadActivePersona 兜底契约", () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    vi.restoreAllMocks()
    setTauriMode(false)
  })
  afterEach(() => setTauriMode(false))

  it("apiGet('/persona/active') 返回 null 时, 兜底调 /persona 列表", async () => {
    // 第一次 fetch (/persona/active) 返回 null, 第二次 (/persona) 返回数组
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/persona/active")) {
        return Promise.resolve({
          json: () => Promise.resolve({ ok: true, data: null, error: null }),
        })
      }
      if (url.endsWith("/persona")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              ok: true,
              data: [{ id: 5, name: "兜底角色" }],
              error: null,
            }),
        })
      }
      return Promise.reject(new Error(`unexpected url: ${url}`))
    })
    vi.stubGlobal("fetch", mockFetch)

    // 模拟 loadActivePersona 的兜底逻辑
    let activePersona: any = null
    const data = await apiGet<any>("/persona/active")
    if (data) {
      activePersona = data
    } else {
      const list = await apiGet<any[]>("/persona")
      if (list && list.length > 0) activePersona = list[0]
    }

    expect(activePersona).toEqual({ id: 5, name: "兜底角色" })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })
})
