// 底部状态栏 - Provider 状态 + 当前角色 + 同步状态 + 版本号
import { useEffect, useState } from "preact/hooks"

interface StatusBarProps {
  provider: string
  persona: string
  syncStatus: string
}

export default function StatusBar({ provider, persona, syncStatus }: StatusBarProps) {
  // 连接状态: green(已连接) / yellow(连接中) / red(断开)
  const [connStatus, setConnStatus] = useState<"green" | "yellow" | "red">("yellow")

  useEffect(() => {
    // 轮询后端 /health 检查连接状态
    let active = true
    const check = async () => {
      try {
        const res = await fetch("http://127.0.0.1:7860/health")
        if (!active) return
        setConnStatus(res.ok ? "green" : "red")
      } catch {
        if (active) setConnStatus("red")
      }
    }
    check()
    const timer = setInterval(check, 10000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  const connColor =
    connStatus === "green" ? "#28C840" : connStatus === "yellow" ? "#FFBD2E" : "#FF5F57"

  return (
    <div
      className="flex items-center justify-between px-3 select-none"
      style={{
        height: "24px",
        fontSize: "var(--font-xs)",
        color: "var(--text-secondary)",
        background: "var(--glass-bg)",
        backdropFilter: "blur(var(--glass-blur))",
        WebkitBackdropFilter: "blur(var(--glass-blur))",
        borderTop: "1px solid var(--border)",
        flexShrink: 0,
      }}
    >
      {/* 左侧: Provider 名称 + 连接指示灯 */}
      <div className="flex items-center gap-1.5">
        <span
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: connColor,
            display: "inline-block",
            boxShadow: `0 0 4px ${connColor}`,
          }}
        />
        <span>{provider}</span>
      </div>

      {/* 中间: 当前角色名称 */}
      <div className="flex items-center gap-1">
        <span style={{ opacity: 0.6 }}>角色:</span>
        <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>
          {persona}
        </span>
      </div>

      {/* 右侧: 同步状态 + 版本号 */}
      <div className="flex items-center gap-3">
        <span style={{ opacity: 0.7 }}>同步: {syncStatus}</span>
        <span style={{ opacity: 0.5 }}>v1.0.0</span>
      </div>
    </div>
  )
}
