// 侧边栏分组导航 - macOS Finder 风格, 5 组导航项
import { useState } from "preact/hooks"

interface SidebarProps {
  current: string
  onNavigate: (page: string) => void
}

interface NavItem {
  id: string
  label: string
  icon: string
}

interface NavGroup {
  title: string
  items: NavItem[]
}

// 导航分组定义
const NAV_GROUPS: NavGroup[] = [
  {
    title: "对话",
    items: [
      { id: "chat", label: "对话", icon: "💬" },
      { id: "swarm", label: "蜂群", icon: "🐝" },
      { id: "dag", label: "DAG 画布", icon: "🕸" },
    ],
  },
  {
    title: "知识",
    items: [
      { id: "memory", label: "记忆图谱", icon: "🧠" },
      { id: "skills", label: "技能市场", icon: "⚡" },
      { id: "wiki", label: "Wiki浏览", icon: "📖" },
      { id: "wiki-review", label: "审核收件箱", icon: "📥" },
      { id: "wikigraph", label: "知识图谱", icon: "🕸️" },
    ],
  },
  {
    title: "角色",
    items: [
      { id: "persona", label: "角色管理", icon: "🎭" },
      { id: "evolution", label: "进化日志", icon: "🌱" },
    ],
  },
  {
    title: "工具",
    items: [
      { id: "dashboard", label: "仪表盘", icon: "📊" },
      { id: "settings", label: "设置", icon: "⚙️" },
      { id: "computer-use", label: "自动化", icon: "🤖" },
    ],
  },
  {
    title: "系统",
    items: [
      { id: "diagnostics", label: "诊断", icon: "🔧" },
    ],
  },
]

export default function Sidebar({ current, onNavigate }: SidebarProps) {
  // 各分组的折叠状态, 默认全部展开
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const toggleGroup = (title: string) => {
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }))
  }

  return (
    <div
      className="flex flex-col py-2 overflow-y-auto"
      style={{
        width: "200px",
        flexShrink: 0,
        background: "var(--glass-bg)",
        backdropFilter: "blur(var(--glass-blur))",
        WebkitBackdropFilter: "blur(var(--glass-blur))",
        borderRight: "1px solid var(--border)",
      }}
    >
      {NAV_GROUPS.map((group) => {
        const isCollapsed = collapsed[group.title]
        return (
          <div key={group.title} className="mb-1">
            {/* 分组标题 - 可点击折叠 */}
            <button
              onClick={() => toggleGroup(group.title)}
              className="flex items-center gap-1 w-full px-3 py-1 text-left"
              style={{
                fontSize: "var(--font-xs)",
                color: "var(--text-secondary)",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  transition: "transform 0.2s",
                  transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
                  fontSize: "10px",
                }}
              >
                ▶
              </span>
              {group.title}
            </button>

            {/* 导航项列表 */}
            {!isCollapsed && (
              <div>
                {group.items.map((item) => {
                  const isActive = current === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => onNavigate(item.id)}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-left transition-colors"
                      style={{
                        fontSize: "var(--font-sm)",
                        color: isActive
                          ? "var(--text-primary)"
                          : "var(--text-secondary)",
                        background: isActive
                          ? "var(--bg-secondary)"
                          : "transparent",
                        border: "none",
                        borderLeft: isActive
                          ? "3px solid var(--accent)"
                          : "3px solid transparent",
                        cursor: "pointer",
                        fontWeight: isActive ? 600 : 400,
                      }}
                    >
                      <span style={{ fontSize: "16px", lineHeight: 1 }}>
                        {item.icon}
                      </span>
                      {item.label}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
