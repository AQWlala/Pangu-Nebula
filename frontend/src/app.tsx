// 主应用框架 - Titlebar + Sidebar + 主内容区 + StatusBar + MascotAssistant
import { useState, useEffect } from "preact/hooks"
import Titlebar from "./components/Titlebar"
import Sidebar from "./components/Sidebar"
import StatusBar from "./components/StatusBar"
import MascotAssistant from "./components/MascotAssistant"
import Settings from "./components/Settings"
import DegradedUI from "./components/DegradedUI"
// 以下组件由其他子智能体创建,路径已约定:
import ChatPanel from "./components/ChatPanel"
import PersonaManager from "./components/PersonaManager"
import OnboardingWizard from "./components/OnboardingWizard"
import SwarmProgress from "./components/SwarmProgress"
import DAGCanvas from "./components/DAGCanvas"
import MemoryGraph from "./components/MemoryGraph"
import MemoryInspector from "./components/MemoryInspector"
import SkillMarketplace from "./components/SkillMarketplace"
import WikiBrowser from "./components/WikiBrowser"
import WikiReviewInbox from "./components/WikiReviewInbox"
import Dashboard from "./components/Dashboard"
import { apiGet, apiPost, getApiBase, IS_TAURI, waitForSidecar } from "./lib/api"

export default function App() {
  // 当前页面 - 使用 useState 管理, 不使用 URL 路由 (PyWebView 环境)
  const [currentPage, setCurrentPage] = useState("chat")
  // 主题管理
  const [theme, setTheme] = useState(
    () => localStorage.getItem("app-theme") || "warm-orange"
  )
  // 引导向导
  const [showOnboarding, setShowOnboarding] = useState(false)
  // 助理心情
  const [mascotMood, setMascotMood] = useState("idle")
  // 状态栏数据
  const [providerName, setProviderName] = useState("未连接")
  const [personaName, setPersonaName] = useState("默认")
  const [syncStatus, setSyncStatus] = useState("离线")
  // Sidecar 就绪状态 (Tauri 模式下需等待 sidecar 启动完成)
  const [sidecarReady, setSidecarReady] = useState(!IS_TAURI)
  const [sidecarError, setSidecarError] = useState("")

  // 初始化: 等待 sidecar 就绪 + 设置主题 + 检查引导
  useEffect(() => {
    document.documentElement.dataset.theme = theme

    const init = async () => {
      // Tauri 模式: 等待 sidecar 就绪 (最多 90s, PyInstaller 首次启动较慢)
      if (IS_TAURI) {
        const ready = await waitForSidecar(90000, 500)
        if (!ready) {
          setSidecarError("Sidecar 启动超时,请重试或检查日志")
          return
        }
        setSidecarReady(true)
      }

      // sidecar 就绪后加载初始状态
      const onboardingDone = localStorage.getItem("onboarding-complete")
      if (!onboardingDone) {
        setShowOnboarding(true)
      }
      loadStatus()
    }
    init()
  }, [])

  // 主题变化时更新 DOM
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem("app-theme", theme)
  }, [theme])

  // 加载状态栏数据
  const loadStatus = async () => {
    try {
      // 获取活跃 Provider
      const providers = await apiGet<any[]>("/providers")
      if (providers && providers.length > 0) {
        const active = providers.find((p) => p.available) || providers[0]
        setProviderName(active.name || "未知")
      }
    } catch {
      setProviderName("未连接")
    }

    try {
      // 获取当前角色
      const persona = await apiGet<any>("/persona/active")
      if (persona && persona.name) {
        setPersonaName(persona.name)
      }
    } catch {
      // 暂无活跃角色
    }

    try {
      // 获取同步状态
      const relay = await apiGet<any>("/sync/relay/status")
      if (relay) {
        setSyncStatus(relay.active ? "在线" : "离线")
      }
    } catch {
      // 同步未配置
    }
  }

  // 主题切换
  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme)
  }

  // 导航
  const handleNavigate = (page: string) => {
    setCurrentPage(page)
    // 切换页面时更新助理心情
    setMascotMood("happy")
    setTimeout(() => setMascotMood("idle"), 1000)
  }

  // 引导完成
  const handleOnboardingComplete = () => {
    localStorage.setItem("onboarding-complete", "true")
    setShowOnboarding(false)
  }

  // 助理快捷操作
  const handleMascotAction = (action: string) => {
    switch (action) {
      case "new-chat":
        setCurrentPage("chat")
        break
      case "switch-persona":
        setCurrentPage("persona")
        break
      case "settings":
        setCurrentPage("settings")
        break
    }
  }

  // 渲染当前页面内容
  const renderPage = () => {
    switch (currentPage) {
      case "chat":
        return <ChatPanel />
      case "swarm":
        return <SwarmProgress />
      case "dag":
        return <DAGCanvas />
      case "memory":
        return <MemoryGraph />
      case "memory-inspector":
        return <MemoryInspector />
      case "skills":
        return <SkillMarketplace />
      case "wiki":
        return <WikiBrowser />
      case "wiki-review":
        return <WikiReviewInbox />
      case "persona":
        return <PersonaManager />
      case "evolution":
        return <EvolutionPage />
      case "dashboard":
        return <Dashboard />
      case "settings":
        return <Settings />
      case "diagnostics":
        return <DiagnosticsPage />
      default:
        return <ChatPanel />
    }
  }

  // Tauri 模式下, sidecar 未就绪时显示加载界面
  if (IS_TAURI && !sidecarReady) {
    return (
      <div
        className="flex flex-col h-screen items-center justify-center"
        style={{
          background: "var(--bg-primary)",
          color: "var(--text-primary)",
          gap: "16px",
        }}
      >
        {sidecarError ? (
          <>
            <div style={{ fontSize: "48px" }}>⚠️</div>
            <div style={{ fontSize: "var(--font-lg)", fontWeight: 700 }}>
              {sidecarError}
            </div>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "8px 24px",
                borderRadius: "var(--radius-md)",
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                cursor: "pointer",
                fontSize: "var(--font-sm)",
                fontWeight: 600,
              }}
            >
              重试
            </button>
          </>
        ) : (
          <>
            <div style={{ fontSize: "48px", animation: "spin 2s linear infinite" }}>⚙️</div>
            <div style={{ fontSize: "var(--font-lg)", fontWeight: 600 }}>
              正在启动 Pangu Nebula...
            </div>
            <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)" }}>
              等待后端服务就绪
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      {/* 标题栏 - 固定顶部 */}
      <Titlebar theme={theme} onThemeChange={handleThemeChange} />

      {/* 中间区域: 侧边栏 + 主内容 */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar current={currentPage} onNavigate={handleNavigate} />
        <main
          className="flex-1 overflow-y-auto"
          style={{ background: "var(--bg-primary)" }}
        >
          {renderPage()}
        </main>
      </div>

      {/* 状态栏 - 固定底部 */}
      <StatusBar
        provider={providerName}
        persona={personaName}
        syncStatus={syncStatus}
      />

      {/* 卡通助理 - 悬浮 */}
      <MascotAssistant mood={mascotMood} onAction={handleMascotAction} />

      {/* 引导向导 - 首次启动遮罩 */}
      {showOnboarding && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.4)",
            zIndex: 2000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <OnboardingWizard onComplete={handleOnboardingComplete} onSkip={handleOnboardingComplete} />
        </div>
      )}

      {/* P0-W5.4: 降级 UI — sidecar 崩溃/完整性校验失败时显示 */}
      <DegradedUI />
    </div>
  )
}

// --- 内联页面: 进化日志 ---
function EvolutionPage() {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    const load = async () => {
      try {
        // /evolution 返回引擎信息对象 (非数组), 日志列表在 /evolution/logs
        const data = await apiGet<{ items: any[]; count: number }>("/evolution/logs")
        // 防御性: 后端契约变更时不应崩溃
        setLogs(Array.isArray(data?.items) ? data.items : [])
      } catch (e: any) {
        setError(e.message || "加载失败")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div style={{ padding: "24px", maxWidth: "800px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "var(--font-2xl)", fontWeight: 700, color: "var(--text-primary)", marginBottom: "24px" }}>
        🌱 进化日志
      </h1>
      {loading && <div style={{ color: "var(--text-secondary)" }}>加载中...</div>}
      {error && (
        <div style={{ padding: "12px", borderRadius: "var(--radius-md)", background: "rgba(255,95,87,0.1)", color: "#FF5F57", marginBottom: "16px" }}>
          {error}
        </div>
      )}
      {!loading && !error && logs.length === 0 && (
        <div style={{ color: "var(--text-secondary)", textAlign: "center", padding: "40px" }}>
          暂无进化记录
        </div>
      )}
      {logs.map((log, i) => (
        <div
          key={i}
          style={{
            padding: "16px",
            borderRadius: "var(--radius-lg)",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            marginBottom: "12px",
          }}
        >
          <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "4px" }}>
            {log.title || log.event || "进化事件"}
          </div>
          <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)" }}>
            {log.description || log.detail || ""}
          </div>
          {log.created_at && (
            <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)", marginTop: "8px", opacity: 0.6 }}>
              {log.created_at}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// --- 内联页面: 诊断 ---
function DiagnosticsPage() {
  const [healthStatus, setHealthStatus] = useState<"checking" | "ok" | "fail">("checking")
  const [healthData, setHealthData] = useState<any>(null)
  const [healthCheckData, setHealthCheckData] = useState<any>(null)
  const [error, setError] = useState("")
  // 局部刷新触发器: 替代 window.location.reload() (避免重置到默认页)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const runDiagnostics = async () => {
      // /health 端点返回 {status: "ok"} 非统一格式, 用 raw fetch 直连
      // P0-W3: 使用 getApiBase() 支持动态端口 (Tauri sidecar 模式)
      try {
        const res = await fetch(`${getApiBase()}/health`)
        if (res.ok) {
          const data = await res.json()
          setHealthStatus(data.status === "ok" ? "ok" : "fail")
          setHealthData(data)
        } else {
          setHealthStatus("fail")
        }
      } catch {
        setHealthStatus("fail")
        setError("后端服务未响应")
      }

      // /health-check 端点返回统一格式
      try {
        const data = await apiGet<any>("/health-check")
        setHealthCheckData(data)
      } catch {
        // 健康检查模块可能未配置
      }
    }
    runDiagnostics()
  }, [refreshKey])

  const statusColor =
    healthStatus === "ok" ? "#28C840" : healthStatus === "fail" ? "#FF5F57" : "#FFBD2E"
  const statusText =
    healthStatus === "ok" ? "正常运行" : healthStatus === "fail" ? "服务异常" : "检查中..."

  return (
    <div style={{ padding: "24px", maxWidth: "800px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "var(--font-2xl)", fontWeight: 700, color: "var(--text-primary)", marginBottom: "24px" }}>
        🔧 系统诊断
      </h1>

      {/* 后端健康状态 */}
      <div
        style={{
          padding: "20px",
          borderRadius: "var(--radius-lg)",
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          marginBottom: "16px",
        }}
      >
        <div className="flex items-center gap-3 mb-3">
          <span
            style={{
              width: "12px",
              height: "12px",
              borderRadius: "50%",
              background: statusColor,
              boxShadow: `0 0 8px ${statusColor}`,
            }}
          />
          <span style={{ fontSize: "var(--font-lg)", fontWeight: 600, color: "var(--text-primary)" }}>
            后端服务: {statusText}
          </span>
        </div>
        {healthData && (
          <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)" }}>
            响应: {JSON.stringify(healthData)}
          </div>
        )}
        {error && (
          <div style={{ fontSize: "var(--font-sm)", color: "#FF5F57", marginTop: "8px" }}>
            {error}
          </div>
        )}
      </div>

      {/* 健康检查模块信息 */}
      {healthCheckData && (
        <div
          style={{
            padding: "20px",
            borderRadius: "var(--radius-lg)",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            marginBottom: "16px",
          }}
        >
          <div style={{ fontSize: "var(--font-lg)", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
            健康检查模块
          </div>
          <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)", marginBottom: "8px" }}>
            {healthCheckData.description || ""}
          </div>
          {healthCheckData.endpoints && (
            <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)", fontFamily: "monospace" }}>
              {healthCheckData.endpoints.map((ep: string, i: number) => (
                <div key={i} style={{ padding: "2px 0" }}>{ep}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 诊断操作 */}
      <div
        style={{
          padding: "20px",
          borderRadius: "var(--radius-lg)",
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
        }}
      >
        <div style={{ fontSize: "var(--font-lg)", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
          快速操作
        </div>
        <button
          onClick={async () => {
            try {
              await apiPost("/health-check/check-all", {})
              // 局部刷新诊断数据, 不重载整个应用 (避免重置到默认页)
              setRefreshKey((k) => k + 1)
            } catch (e: any) {
              setError(e.message)
            }
          }}
          style={{
            padding: "8px 16px",
            borderRadius: "var(--radius-md)",
            background: "var(--accent)",
            color: "#fff",
            border: "none",
            cursor: "pointer",
            fontSize: "var(--font-sm)",
          }}
        >
          检查所有 Provider
        </button>
      </div>
    </div>
  )
}
