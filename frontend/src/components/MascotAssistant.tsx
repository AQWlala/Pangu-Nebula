// 暖色迪士尼风格卡通助理 - 右下角悬浮,纯 CSS/SVG 绘制
import { useState, useEffect } from "preact/hooks"

interface MascotAssistantProps {
  mood: string // idle | happy | thinking | working
  onAction: (action: string) => void
}

export default function MascotAssistant({ mood, onAction }: MascotAssistantProps) {
  const [expanded, setExpanded] = useState(false)
  const [animClass, setAnimClass] = useState("")

  // 根据 mood 切换动画类
  useEffect(() => {
    if (mood === "working") {
      setAnimClass("mascot-working")
    } else if (mood === "thinking") {
      setAnimClass("mascot-thinking")
    } else {
      setAnimClass("mascot-idle")
    }
  }, [mood])

  const quickActions = [
    { id: "new-chat", label: "💬 新对话" },
    { id: "switch-persona", label: "🎭 切换角色" },
    { id: "settings", label: "⚙️ 设置" },
  ]

  return (
    <div
      style={{
        position: "fixed",
        right: "20px",
        bottom: "40px",
        zIndex: 1000,
      }}
    >
      {/* 快捷操作气泡 */}
      {expanded && (
        <div
          style={{
            position: "absolute",
            right: "0",
            bottom: "72px",
            background: "var(--bg-card)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-lg)",
            border: "1px solid var(--border)",
            padding: "8px",
            minWidth: "140px",
            animation: "mascot-pop 0.2s ease-out",
          }}
        >
          {quickActions.map((action) => (
            <button
              key={action.id}
              onClick={() => {
                onAction(action.id)
                setExpanded(false)
              }}
              style={{
                display: "block",
                width: "100%",
                padding: "8px 12px",
                background: "none",
                border: "none",
                borderRadius: "var(--radius-md)",
                cursor: "pointer",
                fontSize: "var(--font-sm)",
                color: "var(--text-primary)",
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-secondary)"
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "none"
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {/* 卡通形象主体 - 可点击 */}
      <div
        className={animClass}
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "64px",
          height: "64px",
          cursor: "pointer",
          position: "relative",
        }}
      >
        <svg
          width="64"
          height="64"
          viewBox="0 0 64 64"
          style={{
            filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.15))",
          }}
        >
          {/* 云朵身体 - 圆滚滚的形状 */}
          <ellipse cx="32" cy="36" rx="26" ry="22" fill="var(--accent)" opacity="0.9" />
          <circle cx="16" cy="30" r="10" fill="var(--accent)" opacity="0.9" />
          <circle cx="48" cy="30" r="10" fill="var(--accent)" opacity="0.9" />
          <circle cx="32" cy="22" r="12" fill="var(--accent)" opacity="0.9" />

          {/* 腮红 */}
          <circle cx="18" cy="40" r="4" fill="#FF6B6B" opacity="0.3" />
          <circle cx="46" cy="40" r="4" fill="#FF6B6B" opacity="0.3" />

          {/* 表情 - 根据 mood 变化 */}
          {mood === "idle" && (
            <>
              {/* 闭眼微笑 - 弧形眼 */}
              <path d="M 22 32 Q 26 28 30 32" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
              <path d="M 34 32 Q 38 28 42 32" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
              {/* 微笑嘴 */}
              <path d="M 26 42 Q 32 46 38 42" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
            </>
          )}
          {mood === "happy" && (
            <>
              {/* 睁眼大笑 - 圆眼 */}
              <circle cx="26" cy="31" r="3" fill="#fff" />
              <circle cx="38" cy="31" r="3" fill="#fff" />
              <circle cx="26" cy="31" r="1.5" fill="#333" />
              <circle cx="38" cy="31" r="1.5" fill="#333" />
              {/* 大笑嘴 */}
              <path d="M 24 40 Q 32 48 40 40" stroke="#fff" strokeWidth="2.5" fill="rgba(255,255,255,0.2)" strokeLinecap="round" />
            </>
          )}
          {mood === "thinking" && (
            <>
              {/* 一只眼眨 */}
              <circle cx="26" cy="31" r="2.5" fill="#fff" />
              <circle cx="26" cy="31" r="1.2" fill="#333" />
              <path d="M 34 32 Q 38 29 42 32" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
              {/* 思考嘴 */}
              <path d="M 28 42 L 36 42" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
            </>
          )}
          {mood === "working" && (
            <>
              {/* 转圈眼 */}
              <circle cx="26" cy="31" r="2.5" fill="#fff" />
              <circle cx="38" cy="31" r="2.5" fill="#fff" />
              <path d="M 26 31 L 26 29 M 26 31 L 28 31 M 26 31 L 26 33 M 26 31 L 24 31" stroke="#333" strokeWidth="0.8" strokeLinecap="round" />
              <path d="M 38 31 L 38 29 M 38 31 L 40 31 M 38 31 L 38 33 M 38 31 L 36 31" stroke="#333" strokeWidth="0.8" strokeLinecap="round" />
              {/* O 嘴 */}
              <ellipse cx="32" cy="42" rx="3" ry="2" fill="none" stroke="#fff" strokeWidth="2" />
            </>
          )}
        </svg>
      </div>

      {/* 内联动画样式 */}
      <style>{`
        @keyframes mascot-bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        @keyframes mascot-breathe {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.05); }
        }
        @keyframes mascot-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes mascot-wink {
          0%, 90%, 100% { transform: scale(1); }
          45% { transform: scale(0.95) rotate(-3deg); }
        }
        @keyframes mascot-pop {
          from { opacity: 0; transform: translateY(10px) scale(0.9); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .mascot-idle {
          animation: mascot-bounce 3s ease-in-out infinite, mascot-breathe 4s ease-in-out infinite;
        }
        .mascot-thinking {
          animation: mascot-wink 2s ease-in-out infinite, mascot-bounce 3s ease-in-out infinite;
        }
        .mascot-working {
          animation: mascot-spin 2s linear infinite, mascot-breathe 1.5s ease-in-out infinite;
        }
      `}</style>
    </div>
  )
}
