// macOS 风格标题栏 - 交通灯 + 标题 + 主题切换 + 窗口按钮
import { useState } from "preact/hooks"

interface TitlebarProps {
  theme: string
  onThemeChange: (theme: string) => void
}

// 三套主题的切换顺序
const THEMES = ["warm-orange", "soft-pink", "cream-beige"]
const THEME_COLORS: Record<string, string> = {
  "warm-orange": "#FF8C42",
  "soft-pink": "#FF6B8A",
  "cream-beige": "#D4A574",
}

export default function Titlebar({ theme, onThemeChange }: TitlebarProps) {
  const [themeIdx, setThemeIdx] = useState(() => {
    const idx = THEMES.indexOf(theme)
    return idx >= 0 ? idx : 0
  })

  const cycleTheme = () => {
    const next = (themeIdx + 1) % THEMES.length
    setThemeIdx(next)
    onThemeChange(THEMES[next])
  }

  return (
    <div
      className="flex items-center justify-between select-none"
      style={{
        height: "32px",
        background: "var(--glass-bg)",
        backdropFilter: `blur(var(--glass-blur))`,
        WebkitBackdropFilter: `blur(var(--glass-blur))`,
        borderBottom: `1px solid var(--border)`,
        WebkitAppRegion: "drag" as any,
        flexShrink: 0,
      }}
    >
      {/* 左侧: 交通灯按钮 */}
      <div
        className="flex items-center gap-2 px-3"
        style={{ WebkitAppRegion: "no-drag" as any }}
      >
        <span
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            background: "#FF5F57",
            display: "inline-block",
            cursor: "pointer",
          }}
        />
        <span
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            background: "#FFBD2E",
            display: "inline-block",
            cursor: "pointer",
          }}
        />
        <span
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            background: "#28C840",
            display: "inline-block",
            cursor: "pointer",
          }}
        />
      </div>

      {/* 中间: 应用标题 */}
      <div
        className="absolute left-1/2 -translate-x-1/2"
        style={{
          fontSize: "var(--font-xs)",
          color: "var(--text-secondary)",
          fontWeight: 500,
          letterSpacing: "0.5px",
        }}
      >
        Pangu Nebula
      </div>

      {/* 右侧: 主题切换 + 窗口按钮 */}
      <div
        className="flex items-center gap-3 px-3"
        style={{ WebkitAppRegion: "no-drag" as any }}
      >
        {/* 主题切换 - 三色圆点 */}
        <button
          onClick={cycleTheme}
          title="切换主题"
          style={{
            width: "14px",
            height: "14px",
            borderRadius: "50%",
            background: THEME_COLORS[THEMES[themeIdx]],
            border: "2px solid rgba(255,255,255,0.6)",
            cursor: "pointer",
            padding: 0,
            boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
          }}
        />
        {/* 最小化按钮 */}
        <button
          title="最小化"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-secondary)",
            fontSize: "var(--font-xs)",
            padding: 0,
            lineHeight: 1,
          }}
        >
          &#8211;
        </button>
        {/* 关闭按钮 */}
        <button
          title="关闭"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-secondary)",
            fontSize: "var(--font-xs)",
            padding: 0,
            lineHeight: 1,
          }}
        >
          &#10005;
        </button>
      </div>
    </div>
  )
}
