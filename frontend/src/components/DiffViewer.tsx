// Diff Viewer 组件 (T2.6)
// - 渲染 unified-diff,支持新增/删除/修改高亮
// - 显示行号(旧/新)
// - 支持对比新旧内容
// - 后端端点: GET /wiki-review/{id}/diff
import { useState, useEffect } from 'preact/hooks'
import { apiGet } from '../lib/api'

// 结构化 diff 行
interface DiffLine {
  type: 'context' | 'added' | 'removed'
  old_line_no: number | null
  new_line_no: number | null
  content: string
}

// diff 接口响应
interface DiffResponse {
  id: number
  wiki_id: number
  diff: string
  has_changes: boolean
  structured?: DiffLine[]
  stats?: {
    added: number
    removed: number
    context: number
  }
}

interface DiffViewerProps {
  /** 审核条目 ID */
  itemId: number | null
  /** 关闭回调 */
  onClose?: () => void
}

// 颜色映射
const LINE_COLORS: Record<string, { bg: string; marker: string; textColor: string }> = {
  added: {
    bg: 'rgba(16, 185, 129, 0.08)',
    marker: '+',
    textColor: '#065F46',
  },
  removed: {
    bg: 'rgba(239, 68, 68, 0.08)',
    marker: '-',
    textColor: '#991B1B',
  },
  context: {
    bg: 'transparent',
    marker: ' ',
    textColor: 'var(--text-primary)',
  },
}

export default function DiffViewer({ itemId, onClose }: DiffViewerProps) {
  const [diff, setDiff] = useState<DiffResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 视图模式: 'unified' (合并视图) | 'split' (分栏对比)
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified')

  // 加载 diff
  useEffect(() => {
    if (itemId == null) {
      setDiff(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    apiGet<DiffResponse>(`/wiki-review/${itemId}/diff`)
      .then((data) => {
        if (!cancelled) setDiff(data)
      })
      .catch((e: any) => {
        if (!cancelled) {
          setError(e?.message || '加载 diff 失败')
          setDiff(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [itemId])

  // 不渲染:无 itemId
  if (itemId == null) return null

  return (
    <div
      className="rounded-xl flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2 p-3 flex-wrap">
        <div>
          <div
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            🔍 Diff 预览 (#{itemId})
          </div>
          {diff?.stats && (
            <div
              className="text-xs mt-0.5 flex items-center gap-3"
              style={{ color: 'var(--text-secondary)' }}
            >
              <span style={{ color: '#065F46' }}>+{diff.stats.added}</span>
              <span style={{ color: '#991B1B' }}>-{diff.stats.removed}</span>
              <span>{diff.stats.context} 上下文</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* 视图模式切换 */}
          <div
            className="flex rounded-lg overflow-hidden"
            style={{ border: '1px solid var(--border)' }}
          >
            <button
              onClick={() => setViewMode('unified')}
              className="px-3 py-1 text-xs"
              style={{
                background:
                  viewMode === 'unified'
                    ? 'var(--accent)'
                    : 'var(--bg-secondary)',
                color: viewMode === 'unified' ? '#fff' : 'var(--text-primary)',
              }}
            >
              合并视图
            </button>
            <button
              onClick={() => setViewMode('split')}
              className="px-3 py-1 text-xs"
              style={{
                background:
                  viewMode === 'split' ? 'var(--accent)' : 'var(--bg-secondary)',
                color: viewMode === 'split' ? '#fff' : 'var(--text-primary)',
              }}
            >
              分栏对比
            </button>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="px-2 py-1 rounded-lg text-xs"
              style={{
                background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            >
              ✕ 关闭
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div
          className="text-center py-6 text-sm"
          style={{ color: 'var(--text-secondary)' }}
        >
          加载中...
        </div>
      )}

      {error && (
        <div
          className="mx-3 mb-3 p-2 rounded-lg text-xs"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            color: '#EF4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {!loading && !error && diff && (
        <>
          {!diff.has_changes ? (
            <div
              className="text-center py-6 text-sm"
              style={{ color: 'var(--text-secondary)' }}
            >
              无变更
            </div>
          ) : diff.structured && diff.structured.length > 0 ? (
            viewMode === 'unified' ? (
              // 合并视图
              <UnifiedView lines={diff.structured} />
            ) : (
              // 分栏对比视图
              <SplitView lines={diff.structured} />
            )
          ) : (
            // 兜底: 显示原始 unified diff 文本
            <pre
              className="px-3 pb-3 text-xs overflow-auto"
              style={{
                color: 'var(--text-primary)',
                fontFamily: 'monospace',
                fontSize: 12,
                lineHeight: 1.6,
                maxHeight: 500,
              }}
            >
              {diff.diff}
            </pre>
          )}
        </>
      )}
    </div>
  )
}

// 合并视图组件
function UnifiedView({ lines }: { lines: DiffLine[] }) {
  return (
    <div
      className="overflow-auto"
      style={{ maxHeight: 500, background: 'var(--bg-primary)' }}
    >
      <table
        className="w-full"
        style={{
          fontFamily: 'monospace',
          fontSize: 12,
          borderCollapse: 'collapse',
        }}
      >
        <tbody>
          {lines.map((line, i) => {
            const color = LINE_COLORS[line.type]
            return (
              <tr
                key={i}
                style={{
                  background: color.bg,
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <td
                  style={{
                    width: 50,
                    textAlign: 'right',
                    padding: '2px 8px',
                    color: 'var(--text-secondary)',
                    opacity: 0.7,
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {line.old_line_no ?? ''}
                </td>
                <td
                  style={{
                    width: 50,
                    textAlign: 'right',
                    padding: '2px 8px',
                    color: 'var(--text-secondary)',
                    opacity: 0.7,
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {line.new_line_no ?? ''}
                </td>
                <td
                  style={{
                    width: 20,
                    textAlign: 'center',
                    padding: '2px 4px',
                    color: color.textColor,
                    fontWeight: 700,
                    userSelect: 'none',
                  }}
                >
                  {color.marker}
                </td>
                <td
                  style={{
                    padding: '2px 8px',
                    color: color.textColor,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}
                >
                  {line.content}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// 分栏对比视图组件
function SplitView({ lines }: { lines: DiffLine[] }) {
  // 构建左右两列: removed/context 放左, added/context 放右
  // 简化策略: 按 context 行对齐,中间的 added/removed 分别填充
  interface Row {
    left: DiffLine | null
    right: DiffLine | null
  }
  const rows: Row[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.type === 'context') {
      rows.push({ left: line, right: line })
      i++
    } else if (line.type === 'removed') {
      // 收集连续的 removed
      const removedBlock: DiffLine[] = []
      while (i < lines.length && lines[i].type === 'removed') {
        removedBlock.push(lines[i])
        i++
      }
      // 收集紧随其后的 added
      const addedBlock: DiffLine[] = []
      while (i < lines.length && lines[i].type === 'added') {
        addedBlock.push(lines[i])
        i++
      }
      // 配对填充
      const maxLen = Math.max(removedBlock.length, addedBlock.length)
      for (let k = 0; k < maxLen; k++) {
        rows.push({
          left: removedBlock[k] || null,
          right: addedBlock[k] || null,
        })
      }
    } else if (line.type === 'added') {
      // 纯 added(无 removed 在前)
      rows.push({ left: null, right: line })
      i++
    } else {
      i++
    }
  }

  return (
    <div
      className="overflow-auto grid grid-cols-2"
      style={{ maxHeight: 500, background: 'var(--bg-primary)' }}
    >
      {/* 左栏: 当前版本 */}
      <div style={{ borderRight: '1px solid var(--border)' }}>
        <div
          className="text-xs font-semibold px-3 py-2 sticky top-0"
          style={{
            background: 'var(--bg-secondary)',
            color: 'var(--text-secondary)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          当前版本
        </div>
        {rows.map((row, i) => {
          const line = row.left
          if (!line) {
            return (
              <div
                key={i}
                style={{
                  padding: '2px 8px',
                  background: 'rgba(16, 185, 129, 0.04)',
                  minHeight: 20,
                  fontFamily: 'monospace',
                  fontSize: 12,
                }}
              >
                
              </div>
            )
          }
          const color = LINE_COLORS[line.type]
          return (
            <div
              key={i}
              style={{
                padding: '2px 8px',
                background: color.bg,
                color: color.textColor,
                fontFamily: 'monospace',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <span
                style={{
                  opacity: 0.5,
                  marginRight: 8,
                  userSelect: 'none',
                }}
              >
                {line.old_line_no ?? ''}
              </span>
              {line.content}
            </div>
          )
        })}
      </div>
      {/* 右栏: 提议版本 */}
      <div>
        <div
          className="text-xs font-semibold px-3 py-2 sticky top-0"
          style={{
            background: 'var(--bg-secondary)',
            color: 'var(--text-secondary)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          提议版本
        </div>
        {rows.map((row, i) => {
          const line = row.right
          if (!line) {
            return (
              <div
                key={i}
                style={{
                  padding: '2px 8px',
                  background: 'rgba(239, 68, 68, 0.04)',
                  minHeight: 20,
                  fontFamily: 'monospace',
                  fontSize: 12,
                }}
              >
                
              </div>
            )
          }
          const color = LINE_COLORS[line.type]
          return (
            <div
              key={i}
              style={{
                padding: '2px 8px',
                background: color.bg,
                color: color.textColor,
                fontFamily: 'monospace',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <span
                style={{
                  opacity: 0.5,
                  marginRight: 8,
                  userSelect: 'none',
                }}
              >
                {line.new_line_no ?? ''}
              </span>
              {line.content}
            </div>
          )
        })}
      </div>
    </div>
  )
}
