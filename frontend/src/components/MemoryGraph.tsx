// 记忆图谱可视化组件 (v2.3.0 Phase 3-B, v2.3.1 修复)
//
// 三级降级实时更新:
//   1. SSE (store.useGlobalState.memoryEvents) — 增量 patch
//   2. 5s 轮询 — SSE 断开时降级
//   3. 手动刷新按钮 — 始终可用
//
// 合并 MemoryInspector: 左侧图谱 + 右侧 Inspector 抽屉 (CRUD)
// 选中节点时, Inspector 显示详情 + 编辑/删除; 顶部 "+ 新建" 打开创建表单。
// CRUD 操作由后端 publish memory.graph.updated, 前端通过 SSE 增量 patch。
//
// v2.3.1 修复:
//   - 引入 DOMPurify 消毒后端返回的 html_content, 防 XSS
//   - pollTimerRef 改用 useState 跟踪轮询状态, SSE 状态指示器正确显示
//   - useGlobalState 改用 selector 模式订阅, 避免全组件树重渲染
//   - 图谱节点加 tabIndex + onKeyDown (WCAG 合规)
import { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks'
import DOMPurify from 'dompurify'
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api'
import { useGlobalState } from '../lib/store'
import type { Memory } from '../lib/types'

// 图谱节点 (与 Memory 兼容, 增加坐标)
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

// Memory 详情 (后端 _memory_to_dict 返回的额外字段)
interface MemoryDetail extends Memory {
  html_content?: string
  importance?: number
  updated_at?: string
  links?: string[]
  backlinks?: number[]
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

const LAYER_ORDER = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5']

// 画布尺寸
const SVG_WIDTH = 900
const SVG_HEIGHT = 560
const CENTER_X = SVG_WIDTH / 2
const CENTER_Y = SVG_HEIGHT / 2
const RADIUS = 200

// 极简 Markdown 渲染 (从 MemoryInspector 内联, 保持组件自包含)
function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  html = html.replace(/```([\s\S]*?)```/g, (_m, c) => `<pre class="md-pre">${c}</pre>`)
  html = html.replace(/^######\s+(.*)$/gm, '<h6>$1</h6>')
  html = html.replace(/^#####\s+(.*)$/gm, '<h5>$1</h5>')
  html = html.replace(/^####\s+(.*)$/gm, '<h4>$1</h4>')
  html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>')
  html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>')
  html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
  html = html.replace(/^[\-\*]\s+(.*)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
  html = html
    .split(/\n{2,}/)
    .map((b) => (b.startsWith('<') ? b : `<p>${b.replace(/\n/g, '<br/>')}</p>`))
    .join('')
  return html
}

export default function MemoryGraph() {
  // ===== 全局 store (SSE 事件流) — v2.3.1: 改用 selector 模式订阅 =====
  const memoryEvents = useGlobalState((s) => s.memoryEvents)
  const sseConnected = useGlobalState((s) => s.sseConnected)

  // ===== 原始数据 =====
  const [rawNodes, setRawNodes] = useState<Memory[]>([])
  const [rawEdges, setRawEdges] = useState<[number, number][]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ===== 过滤条件 =====
  const [layerFilter, setLayerFilter] = useState<string>('all')
  const [tagFilter, setTagFilter] = useState<string>('')
  const [timeRange, setTimeRange] = useState<string>('all')
  const [search, setSearch] = useState<string>('')

  // ===== 节点位置 (可拖拽) =====
  const [positions, setPositions] = useState<Record<number, { x: number; y: number }>>({})
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const dragRef = useRef<{ id: number | null; offsetX: number; offsetY: number }>({
    id: null,
    offsetX: 0,
    offsetY: 0,
  })
  const svgRef = useRef<SVGSVGElement | null>(null)

  // ===== Inspector 状态 (合并自 MemoryInspector) =====
  const [detail, setDetail] = useState<MemoryDetail | null>(null)
  const [backlinks, setBacklinks] = useState<Memory[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<{ layer: string; title: string; content: string; tags: string }>({
    layer: 'L1',
    title: '',
    content: '',
    tags: '',
  })
  const [saving, setSaving] = useState(false)

  // ===== SSE 增量 patch 去重 (按 seq) =====
  const lastProcessedSeqRef = useRef<number>(0)
  // v2.3.1: 5s 轮询降级改用 useState 跟踪轮询状态, 让 SSE 状态指示器正确重渲染
  // 原实现 pollTimerRef 是 ref, 变化不触发重渲染, 导致状态徽章始终显示 "离线"
  const [polling, setPolling] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // SSE 断开检测: 若 sseConnected 持续 false 超过 5s, 启用轮询
  const sseDownSinceRef = useRef<number | null>(null)

  // ===== 全量加载 (初始化 + 手动刷新 + 轮询降级) =====
  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<{ nodes: Memory[]; edges: [number, number][] }>('/memory/graph')
      const nodes = Array.isArray(data?.nodes) ? data.nodes : []
      const edges = Array.isArray(data?.edges) ? data.edges : []
      setRawNodes(nodes)
      setRawEdges(edges as [number, number][])
      // 计算圆形布局 (保留已有位置, 仅给新节点分配)
      setPositions((prev) => {
        const layout: Record<number, { x: number; y: number }> = { ...prev }
        nodes.forEach((n, idx) => {
          if (!layout[n.id]) {
            const angle = (idx / Math.max(nodes.length, 1)) * Math.PI * 2
            layout[n.id] = {
              x: CENTER_X + RADIUS * Math.cos(angle),
              y: CENTER_Y + RADIUS * Math.sin(angle),
            }
          }
        })
        // 清理已不存在的节点位置
        const validIds = new Set(nodes.map((n) => n.id))
        Object.keys(layout).forEach((k) => {
          const id = Number(k)
          if (!validIds.has(id)) delete layout[id]
        })
        return layout
      })
    } catch (e: any) {
      setError(e?.message || '加载图谱失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 初始化挂载时全量加载
  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  // ===== SSE 增量 patch: 监听 memoryEvents =====
  // 仅处理 memory.graph.updated / memory.l1.written / memory.l2.compressed 事件
  // create/update → 拉单条 /memory/{id} patch 进 rawNodes
  // delete → 从 rawNodes 移除
  useEffect(() => {
    if (!memoryEvents || memoryEvents.length === 0) return
    // 处理所有 seq > lastProcessedSeq 的事件
    const pending = memoryEvents.filter((ev) => ev.seq > lastProcessedSeqRef.current)
    if (pending.length === 0) return

    let cancelled = false
    async function applyEvents() {
      for (const ev of pending) {
        if (cancelled) return
        lastProcessedSeqRef.current = Math.max(lastProcessedSeqRef.current, ev.seq)
        const action = ev.action
        const nodeId = ev.nodeId
        // memory.graph.updated: 主通道 (create/update/delete)
        if (ev.eventType === 'memory.graph.updated') {
          if (action === 'delete') {
            if (nodeId == null) continue
            const id = nodeId
            setRawNodes((prev) => prev.filter((n) => n.id !== id))
            setRawEdges((prev) => prev.filter(([s, t]) => s !== id && t !== id))
            setSelected((sel) => (sel && sel.id === id ? null : sel))
          } else if (action === 'create' || action === 'update') {
            if (nodeId == null) continue
            const id = nodeId
            try {
              const detailNode = await apiGet<MemoryDetail>(`/memory/${id}`)
              if (cancelled || !detailNode) continue
              setRawNodes((prev) => {
                const idx = prev.findIndex((n) => n.id === id)
                const node: Memory = {
                  id: detailNode.id,
                  layer: detailNode.layer,
                  title: detailNode.title,
                  content: detailNode.content,
                  tags: detailNode.tags || [],
                  created_at: detailNode.created_at,
                }
                if (idx >= 0) {
                  const next = [...prev]
                  next[idx] = node
                  return next
                }
                return [...prev, node]
              })
              // update 时同步刷新 Inspector 详情 (若当前选中该节点)
              setSelected((sel) => {
                if (sel && sel.id === id) {
                  return {
                    ...sel,
                    title: detailNode.title || `#${id}`,
                    layer: detailNode.layer || 'L0',
                    tags: detailNode.tags || [],
                    created_at: detailNode.created_at,
                  }
                }
                return sel
              })
            } catch {
              // 单条拉取失败, 忽略 (下一次全量加载会修正)
            }
          }
        } else if (ev.eventType === 'memory.l1.written') {
          // 新 L1 记忆写入: payload.memory_id
          const newId = ev.payload?.memory_id
          if (newId == null) continue
          try {
            const detailNode = await apiGet<MemoryDetail>(`/memory/${newId}`)
            if (cancelled || !detailNode) continue
            setRawNodes((prev) => {
              if (prev.some((n) => n.id === newId)) return prev
              return [
                ...prev,
                {
                  id: detailNode.id,
                  layer: detailNode.layer,
                  title: detailNode.title,
                  content: detailNode.content,
                  tags: detailNode.tags || [],
                  created_at: detailNode.created_at,
                },
              ]
            })
          } catch {
            // ignore
          }
        } else if (ev.eventType === 'memory.l2.compressed') {
          // L1→L2 压缩: 全量重载 (结构变化较大, 增量 patch 不划算)
          try {
            await loadGraph()
          } catch {
            // ignore
          }
        }
      }
    }
    applyEvents()
    return () => {
      cancelled = true
    }
  }, [memoryEvents, loadGraph])

  // ===== 5s 轮询降级 (SSE 断开时启用) =====
  // v2.3.1: polling 改用 useState 跟踪, 启用/关闭轮询时同步 setState,
  //         SSE 状态徽章才能根据 polling 正确显示 "轮询 5s"。
  useEffect(() => {
    if (sseConnected) {
      sseDownSinceRef.current = null
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
        setPolling(false)
      }
      return
    }
    // SSE 断开
    if (sseDownSinceRef.current == null) {
      sseDownSinceRef.current = Date.now()
    }
    // 断开超过 5s 才启用轮询 (避免短暂抖动)
    const downMs = Date.now() - (sseDownSinceRef.current || Date.now())
    if (downMs < 5000 && pollTimerRef.current == null) {
      const t = setTimeout(() => {
        if (!sseConnected && pollTimerRef.current == null) {
          pollTimerRef.current = setInterval(() => {
            loadGraph()
          }, 5000)
          setPolling(true)
        }
      }, 5000 - downMs)
      return () => clearTimeout(t)
    }
    if (pollTimerRef.current == null && downMs >= 5000) {
      pollTimerRef.current = setInterval(() => {
        loadGraph()
      }, 5000)
      setPolling(true)
    }
    return () => {
      // 不在此 cleanup 中清除 interval (由 sseConnected=true 分支处理)
    }
  }, [sseConnected, loadGraph])

  // 卸载时清理
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
        setPolling(false)
      }
    }
  }, [])

  // ===== 连接数统计 =====
  const connectionCounts = useMemo(() => {
    const counts: Record<number, number> = {}
    rawEdges.forEach(([s, t]) => {
      counts[s] = (counts[s] || 0) + 1
      counts[t] = (counts[t] || 0) + 1
    })
    return counts
  }, [rawEdges])

  // ===== 过滤后的节点与边 =====
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

  // ===== 构建显示用节点 =====
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

  // ===== 所有标签 (用于标签过滤提示) =====
  const allTags = useMemo(() => {
    const s = new Set<string>()
    rawNodes.forEach((n) => (n.tags || []).forEach((t) => s.add(t)))
    return Array.from(s)
  }, [rawNodes])

  // ===== 层级统计 =====
  const layerStats = useMemo(() => {
    const stats: Record<string, number> = {}
    filteredNodes.forEach((n) => {
      stats[n.layer || 'L0'] = (stats[n.layer || 'L0'] || 0) + 1
    })
    return stats
  }, [filteredNodes])

  // ===== 节点半径 (按连接数) =====
  function nodeRadius(conn: number) {
    return 14 + Math.min(conn, 6) * 4
  }

  // ===== 拖拽处理 =====
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

  // ===== Inspector: 加载节点详情 + 反向链接 =====
  const loadDetail = useCallback(async (nodeId: number | null) => {
    if (nodeId == null) {
      setDetail(null)
      setBacklinks([])
      return
    }
    setDetailLoading(true)
    try {
      const [d, bl] = await Promise.all([
        apiGet<MemoryDetail>(`/memory/${nodeId}`).catch(() => null),
        apiGet<Memory[] | { items?: Memory[] }>(`/memory/${nodeId}/backlinks`).catch(() => []),
      ])
      setDetail(d)
      setBacklinks(Array.isArray(bl) ? bl : bl?.items || [])
    } finally {
      setDetailLoading(false)
    }
  }, [])

  // 选中节点变化时加载详情
  useEffect(() => {
    loadDetail(selected?.id ?? null)
    // 关闭编辑/创建表单
    setEditing(false)
    setCreating(false)
  }, [selected?.id, loadDetail])

  // ===== Inspector: CRUD 操作 =====
  function openCreate() {
    setForm({ layer: 'L1', title: '', content: '', tags: '' })
    setCreating(true)
    setEditing(false)
    setSelected(null) // 关闭节点详情, 突出表单
  }

  function openEdit() {
    if (!detail) return
    setForm({
      layer: detail.layer || 'L1',
      title: detail.title || '',
      content: detail.html_content || detail.content || '',
      tags: (detail.tags || []).join(', '),
    })
    setEditing(true)
    setCreating(false)
  }

  async function save() {
    if (!form.title.trim()) {
      alert('请输入标题')
      return
    }
    setSaving(true)
    try {
      const tags = form.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      if (editing && selected?.id != null) {
        await apiPut(`/memory/${selected.id}`, {
          layer: form.layer,
          title: form.title,
          html_content: form.content,
          tags,
        })
        // 后端会 publish memory.graph.updated(action=update) → SSE 增量 patch
        // 同时本地立即刷新详情
        await loadDetail(selected.id)
      } else {
        const created = await apiPost<MemoryDetail>('/memory', {
          layer: form.layer,
          title: form.title,
          content: form.content,
          html_content: form.content,
          tags,
        })
        // 后端会 publish memory.graph.updated(action=create) → SSE 增量 patch
        if (created?.id != null) {
          // 立即选中新建节点 (SSE patch 会补充节点数据)
          setSelected({
            id: created.id,
            title: created.title || `#${created.id}`,
            layer: created.layer || 'L0',
            tags: created.tags || [],
            connections: 0,
            x: CENTER_X,
            y: CENTER_Y,
            created_at: created.created_at,
          })
        }
      }
      setEditing(false)
      setCreating(false)
    } catch (e: any) {
      alert(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (selected?.id == null) return
    if (!confirm('确定删除这条记忆吗?')) return
    try {
      await apiDelete(`/memory/${selected.id}`)
      // 后端会 publish memory.graph.updated(action=delete) → SSE 增量 patch
      // 本地立即清理
      const id = selected.id
      setRawNodes((prev) => prev.filter((n) => n.id !== id))
      setRawEdges((prev) => prev.filter(([s, t]) => s !== id && t !== id))
      setSelected(null)
      setDetail(null)
      setBacklinks([])
    } catch (e: any) {
      alert(e?.message || '删除失败')
    }
  }

  // SSE 状态指示 (v2.3.1: 用 polling state 代替 pollTimerRef.current, 正确触发重渲染)
  const sseStatusText = sseConnected ? 'SSE 实时' : polling ? '轮询 5s' : '离线'
  const sseStatusColor = sseConnected ? '#28C840' : polling ? '#FFBD2E' : '#FF5F57'

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
        {/* SSE 状态徽章 */}
        <span
          className="px-2 py-0.5 rounded-full text-xs"
          style={{
            background: 'var(--bg-primary)',
            color: sseStatusColor,
            border: `1px solid ${sseStatusColor}`,
          }}
          title={sseConnected ? 'SSE 实时连接' : 'SSE 断开, 启用 5s 轮询降级'}
          >
          ● {sseStatusText}
        </span>
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
        {/* 手动刷新按钮 (三级降级的最后兜底) */}
        <button
          onClick={() => loadGraph()}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-sm"
          style={{
            background: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            cursor: loading ? 'wait' : 'pointer',
          }}
          title="手动刷新图谱"
        >
          {loading ? '⟳ 刷新中...' : '⟳ 刷新'}
        </button>
        {/* 新建记忆按钮 (Inspector 合并) */}
        <button
          onClick={openCreate}
          className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          + 新建
        </button>
      </div>

      {/* 主体: 左侧图谱 + 右侧 Inspector 抽屉 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* 左侧: SVG 图谱 */}
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
                const isSelected = selected?.id === node.id
                return (
                  <g
                    key={node.id}
                    tabIndex={0}
                    role="button"
                    aria-label={`记忆节点 ${node.title}, 层级 ${node.layer}, 连接数 ${node.connections}`}
                    onMouseDown={(e) => onNodeMouseDown(e, node)}
                    onClick={() => setSelected(node)}
                    onKeyDown={(e) => {
                      // v2.3.1 P1-12: WCAG 键盘可达性 (Enter/Space 触发选中)
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setSelected(node)
                      }
                    }}
                    style={{ cursor: 'grab', outline: 'none' }}
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={r}
                      fill={color}
                      fillOpacity={0.85}
                      stroke={isSelected ? '#FFD700' : '#FFFFFF'}
                      strokeWidth={isSelected ? 3 : 2}
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
        </div>

        {/* 右侧: Inspector 抽屉 (合并自 MemoryInspector) */}
        <div
          className="flex flex-col gap-3 p-4 rounded-xl overflow-y-auto"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            maxHeight: SVG_HEIGHT,
            minHeight: 320,
          }}
        >
          {creating || editing ? (
            // 新建/编辑表单
            <div className="flex flex-col gap-3">
              <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                {editing ? '编辑记忆' : '新建记忆'}
              </h3>
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  层级
                </label>
                <select
                  value={form.layer}
                  onChange={(e) => setForm({ ...form, layer: (e.target as HTMLSelectElement).value })}
                  className="px-3 py-2 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                >
                  {LAYER_ORDER.map((l) => (
                    <option key={l} value={l}>
                      {LAYER_LABELS[l]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  标题
                </label>
                <input
                  type="text"
                  value={form.title}
                  onInput={(e) => setForm({ ...form, title: (e.target as HTMLInputElement).value })}
                  className="px-3 py-2 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  标签(逗号分隔)
                </label>
                <input
                  type="text"
                  value={form.tags}
                  onInput={(e) => setForm({ ...form, tags: (e.target as HTMLInputElement).value })}
                  className="px-3 py-2 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  内容(Markdown)
                </label>
                <textarea
                  value={form.content}
                  onInput={(e) =>
                    setForm({ ...form, content: (e.target as HTMLTextAreaElement).value })
                  }
                  rows={8}
                  className="px-3 py-2 rounded-lg text-sm font-mono"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={save}
                  disabled={saving}
                  className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
                  style={{ background: 'var(--accent)' }}
                >
                  {saving ? '保存中...' : '保存'}
                </button>
                <button
                  onClick={() => {
                    setCreating(false)
                    setEditing(false)
                  }}
                  className="px-4 py-1.5 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          ) : !selected ? (
            <div
              className="flex flex-col items-center justify-center gap-2 flex-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">📖</div>
              <div className="text-sm">点击图谱节点查看详情</div>
              <div className="text-xs">或点击顶部 "+ 新建" 创建记忆</div>
            </div>
          ) : detailLoading ? (
            <div className="text-center py-6" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : (
            <>
              {/* 标题 + 层级 + 标签 + 操作按钮 */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <h3
                    className="text-base font-semibold break-words"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {detail?.title || selected.title || `#${selected.id}`}
                  </h3>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                      style={{
                        background:
                          LAYER_COLORS[detail?.layer || selected.layer] || LAYER_COLORS.L0,
                      }}
                    >
                      {LAYER_LABELS[detail?.layer || selected.layer] || selected.layer}
                    </span>
                    {(detail?.tags || selected.tags || []).map((t) => (
                      <span
                        key={t}
                        className="px-2 py-0.5 rounded-full text-xs"
                        style={{
                          background: 'var(--bg-secondary)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="text-sm shrink-0"
                  style={{ color: 'var(--text-secondary)' }}
                  title="关闭"
                >
                  ✕
                </button>
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-2">
                <button
                  onClick={openEdit}
                  className="px-3 py-1 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                  }}
                >
                  编辑
                </button>
                <button
                  onClick={remove}
                  className="px-3 py-1 rounded-lg text-sm text-white"
                  style={{ background: '#EF4444' }}
                >
                  删除
                </button>
              </div>

              {/* 元信息 */}
              <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                <div>ID: #{selected.id} · 连接数: {selected.connections}</div>
                {selected.created_at && (
                  <div>创建于 {new Date(selected.created_at).toLocaleString('zh-CN')}</div>
                )}
                {detail?.updated_at && (
                  <div>更新于 {new Date(detail.updated_at).toLocaleString('zh-CN')}</div>
                )}
              </div>

              {/* 内容 */}
              {detail && (detail.html_content || detail.content) && (
                <div
                  className="rounded-lg p-3 markdown-body text-sm overflow-y-auto"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    lineHeight: 1.7,
                    maxHeight: 240,
                  }}
                  dangerouslySetInnerHTML={{
                    // v2.3.1 P0-7: 后端 html_content 经 DOMPurify 消毒, 防 XSS
                    __html: DOMPurify.sanitize(
                      detail.html_content || renderMarkdown(detail.content || '')
                    ),
                  }}
                />
              )}

              {/* 反向链接 */}
              <div>
                <div
                  className="text-xs font-semibold mb-1.5"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  🔗 反向链接 ({backlinks.length})
                </div>
                {backlinks.length === 0 ? (
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    暂无反向链接
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    {backlinks.map((bl) => (
                      <button
                        key={bl.id}
                        onClick={() => {
                          // 切换选中到反向链接节点
                          const gn = graphNodes.find((n) => n.id === bl.id)
                          if (gn) setSelected(gn)
                          else
                            setSelected({
                              id: bl.id,
                              title: bl.title || `#${bl.id}`,
                              layer: bl.layer || 'L0',
                              tags: bl.tags || [],
                              connections: 0,
                              x: CENTER_X,
                              y: CENTER_Y,
                              created_at: bl.created_at,
                            })
                        }}
                        className="text-left px-2.5 py-1.5 rounded-lg text-sm"
                        style={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        <span
                          className="inline-block w-2 h-2 rounded-full mr-1.5"
                          style={{
                            background: LAYER_COLORS[bl.layer || 'L0'] || LAYER_COLORS.L0,
                          }}
                        />
                        {bl.title || `#${bl.id}`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
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
