// Pangu Nebula 更新检查 UI (v2.1.0 Phase 0 — P0-W6.2)
//
// 集成到设置页"关于"分类下,提供:
// 1. 检查更新按钮 (invoke check_for_update)
// 2. 更新进度显示 (监听 update-progress 事件)
// 3. 下载并安装按钮 (invoke install_update)
// 4. 安装完成提示 (监听 update-installed 事件,提示重启)
//
// 仅在 Tauri 模式下可用 (PyWebView 模式显示"暂不支持")

import { useState, useEffect } from "preact/hooks"
import { IS_TAURI } from "../lib/api"

type UpdateStatus = "idle" | "checking" | "available" | "no-update" | "downloading" | "installed" | "error"

interface UpdateInfo {
  available: boolean
  version?: string
  notes?: string
  date?: string
}

interface ProgressInfo {
  downloaded: number
  total: number
}

export default function UpdateChecker() {
  const [status, setStatus] = useState<UpdateStatus>("idle")
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [progress, setProgress] = useState<ProgressInfo>({ downloaded: 0, total: 0 })
  const [errorMsg, setErrorMsg] = useState("")

  useEffect(() => {
    if (!IS_TAURI) return

    let unlisteners: Array<() => void> = []

    const setup = async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event")

        // 监听下载进度
        const un1 = await listen<ProgressInfo>("update-progress", (event) => {
          setProgress(event.payload)
          setStatus("downloading")
        })

        // 监听安装完成
        const un2 = await listen("update-installed", () => {
          setStatus("installed")
        })

        // 监听更新错误
        const un3 = await listen<{ error: string }>("update-error", (event) => {
          setStatus("error")
          setErrorMsg(event.payload?.error || "更新失败")
        })

        unlisteners = [un1, un2, un3]
      } catch (e) {
        console.warn("[UpdateChecker] Failed to register listeners:", e)
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

  const handleCheck = async () => {
    if (!IS_TAURI) return

    setStatus("checking")
    setErrorMsg("")

    try {
      const { invoke } = await import("@tauri-apps/api/core")
      const info = await invoke<UpdateInfo>("check_for_update")
      setUpdateInfo(info)
      if (info.available) {
        setStatus("available")
      } else {
        setStatus("no-update")
      }
    } catch (e: any) {
      setStatus("error")
      setErrorMsg(e?.message || "检查更新失败")
    }
  }

  const handleInstall = async () => {
    if (!IS_TAURI) return

    setStatus("downloading")
    setProgress({ downloaded: 0, total: 0 })
    setErrorMsg("")

    try {
      const { invoke } = await import("@tauri-apps/api/core")
      await invoke("install_update")
      // update-installed 事件会触发 status = "installed"
    } catch (e: any) {
      setStatus("error")
      setErrorMsg(e?.message || "安装更新失败")
    }
  }

  // 非 Tauri 模式
  if (!IS_TAURI) {
    return (
      <div style={{ padding: "16px", borderRadius: "var(--radius-md)", background: "var(--bg-secondary)", color: "var(--text-secondary)", fontSize: "var(--font-sm)" }}>
        自动更新仅在桌面应用模式下可用
      </div>
    )
  }

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
  }

  const progressPercent =
    progress.total > 0 ? Math.round((progress.downloaded / progress.total) * 100) : 0

  return (
    <div style={{ padding: "16px", borderRadius: "var(--radius-lg)", background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      <div style={{ fontSize: "var(--font-md)", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
        🔄 自动更新
      </div>

      {/* 检查更新按钮 */}
      {status === "idle" && (
        <button
          onClick={handleCheck}
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
          检查更新
        </button>
      )}

      {/* 检查中 */}
      {status === "checking" && (
        <div style={{ color: "var(--text-secondary)", fontSize: "var(--font-sm)" }}>
          正在检查更新...
        </div>
      )}

      {/* 有可用更新 */}
      {status === "available" && updateInfo && (
        <div>
          <div style={{ marginBottom: "12px" }}>
            <span style={{ color: "#28C840", fontWeight: 600, fontSize: "var(--font-sm)" }}>
              ✨ 发现新版本 v{updateInfo.version}
            </span>
            {updateInfo.date && (
              <span style={{ color: "var(--text-secondary)", fontSize: "var(--font-xs)", marginLeft: "8px" }}>
                ({updateInfo.date.split("T")[0]})
              </span>
            )}
          </div>
          {updateInfo.notes && (
            <div
              style={{
                padding: "12px",
                borderRadius: "var(--radius-md)",
                background: "var(--bg-secondary)",
                fontSize: "var(--font-sm)",
                color: "var(--text-secondary)",
                marginBottom: "12px",
                maxHeight: "200px",
                overflow: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {updateInfo.notes}
            </div>
          )}
          <button
            onClick={handleInstall}
            style={{
              padding: "8px 16px",
              borderRadius: "var(--radius-md)",
              background: "#28C840",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontSize: "var(--font-sm)",
            }}
          >
            下载并安装
          </button>
        </div>
      )}

      {/* 无更新 */}
      {status === "no-update" && (
        <div style={{ color: "var(--text-secondary)", fontSize: "var(--font-sm)" }}>
          ✅ 当前已是最新版本
          <button
            onClick={handleCheck}
            style={{
              marginLeft: "12px",
              padding: "4px 12px",
              borderRadius: "var(--radius-md)",
              background: "transparent",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
              cursor: "pointer",
              fontSize: "var(--font-xs)",
            }}
          >
            重新检查
          </button>
        </div>
      )}

      {/* 下载中 */}
      {status === "downloading" && (
        <div>
          <div style={{ marginBottom: "8px", fontSize: "var(--font-sm)", color: "var(--text-secondary)" }}>
            正在下载更新... {progressPercent}%
          </div>
          <div
            style={{
              width: "100%",
              height: "6px",
              background: "var(--bg-secondary)",
              borderRadius: "3px",
              overflow: "hidden",
              marginBottom: "4px",
            }}
          >
            <div
              style={{
                width: `${progressPercent}%`,
                height: "100%",
                background: "var(--accent)",
                transition: "width 0.2s ease",
              }}
            />
          </div>
          <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
            {formatBytes(progress.downloaded)} / {formatBytes(progress.total)}
          </div>
        </div>
      )}

      {/* 安装完成 */}
      {status === "installed" && (
        <div style={{ color: "#28C840", fontSize: "var(--font-sm)" }}>
          ✅ 更新已安装,重启应用后生效
        </div>
      )}

      {/* 错误 */}
      {status === "error" && (
        <div>
          <div style={{ color: "#FF5F57", fontSize: "var(--font-sm)", marginBottom: "8px" }}>
            ❌ {errorMsg}
          </div>
          <button
            onClick={handleCheck}
            style={{
              padding: "4px 12px",
              borderRadius: "var(--radius-md)",
              background: "transparent",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
              cursor: "pointer",
              fontSize: "var(--font-xs)",
            }}
          >
            重试
          </button>
        </div>
      )}
    </div>
  )
}
