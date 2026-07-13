// Pangu Nebula 降级 UI (v2.1.0 Phase 0 — P0-W5.4)
//
// 当 sidecar 崩溃重启超限或完整性校验失败时显示。
// 监听 Tauri 事件:
//   - "sidecar-degraded": 崩溃重启超限 (retry_count >= 3)
//   - "sidecar-integrity-failed": 文件哈希不匹配
//   - "sidecar-error": sidecar 启动失败
//
// 显示模式: 全屏遮罩 + 错误信息 + 操作按钮 (重试/退出)

import { useState, useEffect } from "preact/hooks"
import { IS_TAURI } from "../lib/api"

export type DegradedReason = "crash" | "integrity" | "spawn-error" | null

export interface DegradedInfo {
  reason: DegradedReason
  title: string
  message: string
  details?: any
}

export default function DegradedUI() {
  const [degraded, setDegraded] = useState<DegradedInfo | null>(null)

  useEffect(() => {
    if (!IS_TAURI) return

    // 动态导入 Tauri event API
    let unlisteners: Array<() => void> = []

    const setup = async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event")

        // 监听 sidecar-degraded (崩溃重启超限)
        const un1 = await listen("sidecar-degraded", (event: any) => {
          console.error("[sidecar] Degraded:", event.payload)
          setDegraded({
            reason: "crash",
            title: "后端服务不可用",
            message: "Python sidecar 多次崩溃重启失败,已进入降级模式。",
            details: event.payload,
          })
        })

        // 监听 sidecar-integrity-failed (完整性校验失败)
        const un2 = await listen("sidecar-integrity-failed", (event: any) => {
          console.error("[sidecar] Integrity failed:", event.payload)
          const payload = event.payload || {}
          const mismatches = payload.mismatches || []
          const missing = payload.missing || []
          const detailParts: string[] = []
          if (mismatches.length > 0) {
            detailParts.push(`${mismatches.length} 个文件哈希不匹配`)
          }
          if (missing.length > 0) {
            detailParts.push(`${missing.length} 个文件缺失`)
          }
          setDegraded({
            reason: "integrity",
            title: "Sidecar 完整性校验失败",
            message: `检测到 sidecar 文件被篡改或损坏 (${detailParts.join(", ")})。为安全起见,已拒绝启动后端服务。`,
            details: payload,
          })
        })

        // 监听 sidecar-error (启动失败)
        const un3 = await listen("sidecar-error", (event: any) => {
          console.error("[sidecar] Spawn error:", event.payload)
          setDegraded({
            reason: "spawn-error",
            title: "后端服务启动失败",
            message: `Python sidecar 启动失败: ${event.payload?.error || "未知错误"}`,
            details: event.payload,
          })
        })

        unlisteners = [un1, un2, un3]
        console.log("[DegradedUI] Event listeners registered")
      } catch (e) {
        console.warn("[DegradedUI] Failed to register listeners:", e)
      }
    }

    setup()

    return () => {
      unlisteners.forEach((un) => {
        try {
          un()
        } catch {
          // ignore
        }
      })
    }
  }, [])

  // 无降级状态时不渲染
  if (!degraded) return null

  const handleRetry = () => {
    // 重新加载页面 (Tauri 会重新走 setup 钩子,重新 spawn sidecar)
    window.location.reload()
  }

  const handleDismiss = () => {
    // 关闭降级提示 (继续使用前端,但后端不可用)
    setDegraded(null)
  }

  // 根据原因选择图标和颜色
  const icon =
    degraded.reason === "integrity" ? "🛡️" : degraded.reason === "crash" ? "💥" : "⚠️"
  const accentColor =
    degraded.reason === "integrity" ? "#FF5F57" : degraded.reason === "crash" ? "#FFBD2E" : "#FF9500"

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        zIndex: 3000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: "520px",
          width: "90%",
          background: "var(--bg-card, #fff)",
          borderRadius: "16px",
          boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
          overflow: "hidden",
        }}
      >
        {/* 顶部色条 */}
        <div style={{ height: "4px", background: accentColor }} />

        {/* 内容区 */}
        <div style={{ padding: "32px" }}>
          {/* 图标 + 标题 */}
          <div style={{ textAlign: "center", marginBottom: "20px" }}>
            <div style={{ fontSize: "48px", marginBottom: "12px" }}>{icon}</div>
            <h2
              style={{
                fontSize: "20px",
                fontWeight: 700,
                color: "var(--text-primary, #1a1a1a)",
                margin: 0,
              }}
            >
              {degraded.title}
            </h2>
          </div>

          {/* 消息 */}
          <p
            style={{
              fontSize: "14px",
              color: "var(--text-secondary, #666)",
              lineHeight: 1.6,
              textAlign: "center",
              marginBottom: "20px",
            }}
          >
            {degraded.message}
          </p>

          {/* 详情 (可折叠) */}
          {degraded.details && (
            <details
              style={{
                marginBottom: "20px",
                padding: "12px",
                background: "var(--bg-secondary, #f5f5f5)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            >
              <summary
                style={{
                  cursor: "pointer",
                  color: "var(--text-secondary, #666)",
                  fontWeight: 600,
                }}
              >
                技术详情
              </summary>
              <pre
                style={{
                  marginTop: "8px",
                  overflow: "auto",
                  maxHeight: "200px",
                  fontSize: "11px",
                  color: "var(--text-secondary, #666)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {JSON.stringify(degraded.details, null, 2)}
              </pre>
            </details>
          )}

          {/* 操作按钮 */}
          <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
            <button
              onClick={handleRetry}
              style={{
                padding: "10px 24px",
                borderRadius: "8px",
                background: accentColor,
                color: "#fff",
                border: "none",
                cursor: "pointer",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              重试
            </button>
            {degraded.reason !== "integrity" && (
              <button
                onClick={handleDismiss}
                style={{
                  padding: "10px 24px",
                  borderRadius: "8px",
                  background: "transparent",
                  color: "var(--text-secondary, #666)",
                  border: "1px solid var(--border, #ddd)",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                忽略并继续
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
