// 记忆图谱可视化组件
// 使用 SVG 绘制力导向图(简化版: 圆形布局 + 节点拖拽)
import { useState, useEffect, useRef, useMemo } from 'preact/hooks'
import { apiGet } from '../lib/api'
import type { Memory } from '../lib/types'

// 图谱节点
interface GraphNode {
  id: number
  title: string
  layer: string
  tags: string[]
  x: number
  y: number
  connections: number
  created_at?: string
}

// 层级颜色映射
const LAYER_COLORS: Record<string, string> = {
  L0: '#9CA3AF', // 灰色
  L1: '#FF8C42', // 橙色
  L2: '#FF6B8A', // 粉色
  L3: '#52C41A', // 绿色
  L4: '#3B82F6', // 蓝色
  L5: '#8B5CF6', // 紫色
}

const LAYER_LABELS: Record<string, string> = {
  L0: 'L0 感官',
  L1: 'L1 事件',
  L2: 'L2 情感',
  L3: 'L3 概念',
  L4: 'L4 程序',
  L5: 'L5 自我',
}

// 画布尺寸
const SVG_WIDTH = 900
const SVG_HEIGHT = 560
const CENTER_X = SVG_WIDTH / 2
const CENTER_Y = SVG_HEIGHT / 2
const RADIUS = 200

export default function MemoryGraph() {
  // 原始数据
  const [rawNodes, setRawNodes] = useState<Memory[]>([])
  const [rawEdges, setRawEdges] = useState<[number, number][]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 过滤条件
  const [layerFilter, setLayerFilter] = useState<string>('all')
  const [tagFilter, setTagFilter] = useState<string>('')
  const [timeRange, setTimeRange] = useState<string>('all')
  const [search, setSearch] = useState<string>('')

  // 节点位置(可拖拽)
  const [positions, setPositions] = useState<Record<number, { x: number; y: number }>>({})
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const dragRef = useRef<{ id: number | null; offsetX: number; offsetY: number }>({
    id: null,
    offsetX: 0,
    offsetY: 0,
  })
  const svgRef = useRef<SVGSVGElement | null>(null)

  // 加载图谱数据
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await apiGet<{ nodes: Memory[]; edges: [number, number][] }>('/memory/graph')
        if (cancelled) return
        const nodes = Array.isArray(data?.nodes) ? data.nodes : []
        const edges = Array.isArray(data?.edges) ? data.edges : []
        setRawNodes(nodes)
        setRawEdges(edges)
        // 计算圆形布局
        const layout: Record<number, { x: number; y: number }> = {}
        nodes.forEach((n, idx) => {
          const angle = (idx / Math.max(nodes.length, 1)) * Math.PI * 2
          layout[n.id] = {
            x: CENTER_X + RADIUS * Math.cos(angle),
            y: CENTER_Y + RADIUS * Math.sin(angle),
          }
        })
        setPositions(layout)
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载图谱失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  // 连接数统计
  const connectionCounts = useMemo(() => {
    const counts: Record<number, number> = {}
    rawEdges.forEach(([s, t]) => {
      counts[s] = (counts[s] || 0) + 1
      counts[t] = (counts[t] || 0) + 1
    })
    return counts
  }, [rawEdges])

  // 过滤后的节点与边
  const { filteredNodes, filteredEdges } = useMemo(() => {
    const now = Date.now()
    const rangeMs: Record<string, number> = {
      '7d': 7 * 24 * 3600 * 1000,
      '30d': 30 * 24 * 3600 * 1000,
      '90d': 90 * 24 * 3600 * 1000,
    }
    const nodes = rawNodes.filter((n) => {
      if (layerFilter !== 'all' && n.layer !== layerFilter) return false
      if (tagFilter && !(n.tags || []).includes(tagFilter)) return false
      if (search && !(n.title || '').toLowerCase().includes(search.toLowerCase())) return false
      if (timeRange !== 'all' && n.created_at) {
        const created = new Date(n.created_at).getTime()
        if (now - created > (rangeMs[timeRange] || 0)) return false
      }
      return true
    })
    const nodeIds = new Set(nodes.map((n) => n.id))
    const edges = rawEdges.filter(([s, t]) => nodeIds.has(s) && nodeIds.has(t))
    return { filteredNodes: nodes, filteredEdges: edges }
  }, [rawNodes, rawEdges, layerFilter, tagFilter, search, timeRange])

  // 构建显示用节点
  const graphNodes: GraphNode[] = useMemo(() => {
    return filteredNodes.map((n) => ({
      id: n.id,
      title: n.title || `#${n.id}`,
      layer: n.layer || 'L0',
      tags: n.tags || [],
      connections: connectionCounts[n.id] || 0,
      created_at: n.created_at,
      x: positions[n.id]?.x ?? CENTER_X,
      y: positions[n.id]?.y ?? CENTER_Y,
    }))
  }, [filteredNodes, positions, connectionCounts])

  // 所有标签(用于标签过滤提示)
  const allTags = useMemo(() => {
    const s = new Set<string>()
    rawNodes.forEach((n) => (n.tags || []).forEach((t) => s.add(t)))
    return Array.from(s)
  }, [rawNodes])

  // 节点半径(按连接数)
  function nodeRadius(conn: number) {
    return 14 + Math.min(conn, 6) * 4
  }

  // 拖拽处理
  function onNodeMouseDown(e: MouseEvent, node: GraphNode) {
    e.preventDefault()
    const svg = svgRef.current
    if (!svg) return
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return
    const loc = pt.matrixTransform(ctm.inverse())
    dragRef.current = {
      id: node.id,
      offsetX: loc.x - node.x,
      offsetY: loc.y - node.y,
    }
    window.addEventListener('mousemove', onWindowMouseMove)
    window.addEventListener('mouseup', onWindowMouseUp)
  }

  function onWindowMouseMove(e: MouseEvent) {
    const drag = dragRef.current
    const svg = svgRef.current
    if (drag.id == null || !svg) return
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return
    const loc = pt.matrixTransform(ctm.inverse())
    const nx = Math.max(30, Math.min(SVG_WIDTH - 30, loc.x - drag.offsetX))
    const ny = Math.max(30, Math.min(SVG_HEIGHT - 30, loc.y - drag.offsetY))
    setPositions((prev) => ({ ...prev, [drag.id as number]: { x: nx, y: ny } }))
  }

  function onWindowMouseUp() {
    dragRef.current.id = null
    window.removeEventListener('mousemove', onWindowMouseMove)
    window.removeEventListener('mouseup', onWindowMouseUp)
  }

  // 层级统计
  const layerStats = useMemo(() => {
    const stats: Record<string, number> = {}
    filteredNodes.forEach((n) => {
      stats[n.layer || 'L0'] = (stats[n.layer || 'L0'] || 0) + 1
    })
    return stats
  }, [filteredNodes])

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-4"
      style={{
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border)',
      }}
    >
      {/* 顶部工具栏 */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold mr-2" style={{ color: 'var(--text-primary)' }}>
          🧠 记忆图谱
        </h2>
        <select
          value={layerFilter}
          onChange={(e) => setLayerFilter((e.target as HTMLSelectElement).value)}
          className="px-3 py-1.5 rounded-lg text-sm"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="all">全部层级</option>
          {Object.keys(LAYER_LABELS).map((l) => (
            <option key={l} value={l}>
              {LAYER_LABELS[l]}
            </option>
          ))}
        </select>
        <input
          type="text"
          list="memory-tag-list"
          placeholder="标签过滤"
          value={tagFilter}
          onInput={(e) => setTagFilter((e.target as HTMLInputElement).value)}
          className="px-3 py-1.5 rounded-lg text-sm w-36"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
        <datalist id="memory-tag-list">
          {allTags.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        <select
          value={timeRange}
          onChange={(e) => setTimeRange((e.target as HTMLSelectElement).value)}
          className="px-3 py-1.5 rounded-lg text-sm"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="all">全部时间</option>
          <option value="7d">近 7 天</option>
          <option value="30d">近 30 天</option>
          <option value="90d">近 90 天</option>
        </select>
        <input
          type="text"
          placeholder="🔍 搜索标题..."
          value={search}
          onInput={(e) => setSearch((e.target as HTMLInputElement).value)}
          className="px-3 py-1.5 rounded-lg text-sm flex-1 min-w-[160px]"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
      </div>

      {/* 主体 SVG */}
      <div
        className="rounded-xl relative overflow-hidden"
        style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
      >
        {loading ? (
          <div
            className="flex items-center justify-center"
            style={{ height: SVG_HEIGHT, color: 'var(--text-secondary)' }}
          >
            加载中...
          </div>
        ) : error ? (
          <div
            className="flex items-center justify-center"
            style={{ height: SVG_HEIGHT, color: '#EF4444' }}
          >
            {error}
          </div>
        ) : graphNodes.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center gap-2"
            style={{ height: SVG_HEIGHT, color: 'var(--text-secondary)' }}
          >
            <div className="text-5xl">🌐</div>
            <div>暂无记忆图谱数据</div>
            <div className="text-xs">创建记忆并添加关联后,这里会展示图谱</div>
          </div>
        ) : (
          <svg
            ref={svgRef}
            width="100%"
            viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
            style={{ display: 'block', maxHeight: SVG_HEIGHT }}
          >
            {/* 边 */}
            {filteredEdges.map(([s, t], idx) => {
              const sp = positions[s]
              const tp = positions[t]
              if (!sp || !tp) return null
              return (
                <line
                  key={`e-${idx}`}
                  x1={sp.x}
                  y1={sp.y}
                  x2={tp.x}
                  y2={tp.y}
                  stroke="var(--border)"
                  strokeWidth={1.5}
                  strokeOpacity={0.6}
                />
              )
            })}
            {/* 节点 */}
            {graphNodes.map((node) => {
              const r = nodeRadius(node.connections)
              const color = LAYER_COLORS[node.layer] || LAYER_COLORS.L0
              return (
                <g
                  key={node.id}
                  onMouseDown={(e) => onNodeMouseDown(e, node)}
                  onClick={() => setSelected(node)}
                  style={{ cursor: 'grab' }}
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r}
                    fill={color}
                    fillOpacity={0.85}
                    stroke="#FFFFFF"
                    strokeWidth={2}
                    style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.15))' }}
                  />
                  <text
                    x={node.x}
                    y={node.y + r + 14}
                    textAnchor="middle"
                    fontSize={11}
                    fill="var(--text-primary)"
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {node.title.length > 10 ? node.title.slice(0, 10) + '…' : node.title}
                  </text>
                </g>
              )
            })}
          </svg>
        )}

        {/* 节点详情浮窗 */}
        {selected && (
          <div
            className="absolute top-3 right-3 p-4 rounded-xl"
            style={{
              background: 'var(--glass-bg)',
              backdropFilter: 'blur(var(--glass-blur))',
              border: '1px solid var(--glass-border)',
              boxShadow: 'var(--shadow-lg)',
              width: 240,
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <div
                className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                style={{ background: LAYER_COLORS[selected.layer] || LAYER_COLORS.L0 }}
              >
                {LAYER_LABELS[selected.layer] || selected.layer}
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                ✕
              </button>
            </div>
            <h3 className="font-semibold mt-2" style={{ color: 'var(--text-primary)' }}>
              {selected.title}
            </h3>
            <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              连接数: {selected.connections} · ID: #{selected.id}
            </div>
            {selected.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {selected.tags.map((t) => (
                  <span
                    key={t}
                    className="px-2 py-0.5 rounded-full text-xs"
                    style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                  >
                    #{t}
                  </span>
                ))}
              </div>
            )}
            {selected.created_at && (
              <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                创建于 {new Date(selected.created_at).toLocaleString('zh-CN')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部: 图例 + 统计 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {Object.keys(LAYER_LABELS).map((l) => (
            <div key={l} className="flex items-center gap-1.5 text-xs">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{ background: LAYER_COLORS[l] }}
              />
              <span style={{ color: 'var(--text-secondary)' }}>{LAYER_LABELS[l]}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span>节点 {graphNodes.length}</span>
          <span>·</span>
          <span>边 {filteredEdges.length}</span>
          {Object.keys(layerStats).length > 0 && (
            <>
              <span>·</span>
              <span>
                {Object.entries(layerStats)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(' ')}
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
