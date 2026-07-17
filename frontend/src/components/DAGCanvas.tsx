// DAG 画布组件 (T2.2 + v2.3.0 多 DAG + SSE)
// - 可视化渲染 DAG 节点和边
// - 节点状态颜色: pending(灰)/running(蓝)/completed(绿)/failed(红)/skipped(黄)
// - 点击节点 -> 主区域显示 worker 对话
// - 自包含 SVG 边 + DOM 节点的混合实现,兼容 Preact
// - v2.3.0: 多 DAG 并排渲染,通过 store.visibleDagIds 驱动
// - v2.3.0: SSE 订阅 (通过 store.runningTasks),running 节点自动聚焦
import { useState, useEffect, useMemo, useCallback, useRef } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'
import { useGlobalState } from '../lib/store'
import ApprovalBanner from './ApprovalBanner'
import NodeConfigPanel from './NodeConfigPanel'

// DAG 节点类型
interface DAGNode {
  id: number
  dag_id: string
  node_id: string
  title: string
  node_type: string // task/decision/approval
  status: string // pending/running/completed/failed/skipped
  model: string | null
  brief: string | null
  config: Record<string, any>
  result: string | null
  created_at: string | null
  updated_at: string | null
}

// DAG 边类型
interface DAGEdge {
  id: number
  dag_id: string
  source_node_id: string
  target_node_id: string
  edge_type: string // sequence/condition/parallel
  condition: string | null
}

// DAG 完整数据
interface DAGData {
  dag_id: string
  nodes: DAGNode[]
  edges: DAGEdge[]
}

// DAG 列表摘要
interface DAGSummary {
  dag_id: string
  node_count: number
  edge_count: number
  statuses: Record<string, number>
}

// Worker 对话消息(点击节点查看)
interface WorkerMessage {
  role: string // user/assistant/system
  content: string
  ts: string | null
}

// 节点状态颜色映射
const STATUS_COLORS: Record<string, { bg: string; border: string; text: string; label: string }> = {
  pending: { bg: '#F3F4F6', border: '#9CA3AF', text: '#4B5563', label: '待执行' },
  running: { bg: '#DBEAFE', border: '#3B82F6', text: '#1E40AF', label: '执行中' },
  completed: { bg: '#D1FAE5', border: '#10B981', text: '#065F46', label: '已完成' },
  failed: { bg: '#FEE2E2', border: '#EF4444', text: '#991B1B', label: '失败' },
  skipped: { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E', label: '已跳过' },
}

// 节点类型图标
const NODE_TYPE_ICON: Record<string, string> = {
  task: '⚙️',
  decision: '🔀',
  approval: '✅',
}

// 节点尺寸常量(用于布局计算)
const NODE_WIDTH = 180
const NODE_HEIGHT = 70
const LAYER_GAP_X = 240
const LAYER_GAP_Y = 110

// 计算节点布局: 基于拓扑分层
function computeLayout(nodes: DAGNode[], edges: DAGEdge[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  if (nodes.length === 0) return positions

  // 构建前驱/后继映射
  const successors = new Map<string, string[]>()
  const predecessors = new Map<string, string[]>()
  nodes.forEach((n) => {
    successors.set(n.node_id, [])
    predecessors.set(n.node_id, [])
  })
  edges.forEach((e) => {
    if (successors.has(e.source_node_id) && predecessors.has(e.target_node_id)) {
      successors.get(e.source_node_id)!.push(e.target_node_id)
      predecessors.get(e.target_node_id)!.push(e.source_node_id)
    }
  })

  // 拓扑分层 (Kahn 算法): 无前驱的节点放第 0 层
  const layers = new Map<string, number>()
  nodes.forEach((n) => {
    const deg = predecessors.get(n.node_id)!.length
    if (deg === 0) layers.set(n.node_id, 0)
  })

  // 迭代分层: 层 = max(前驱层) + 1
  let changed = true
  let safety = nodes.length + 5
  while (changed && safety-- > 0) {
    changed = false
    nodes.forEach((n) => {
      const preds = predecessors.get(n.node_id) || []
      if (preds.length === 0) {
        if (!layers.has(n.node_id)) {
          layers.set(n.node_id, 0)
          changed = true
        }
      } else {
        let maxLayer = -1
        let allResolved = true
        for (const p of preds) {
          if (!layers.has(p)) {
            allResolved = false
            break
          }
          maxLayer = Math.max(maxLayer, layers.get(p)!)
        }
        if (allResolved) {
          const newLayer = maxLayer + 1
          if (layers.get(n.node_id) !== newLayer) {
            layers.set(n.node_id, newLayer)
            changed = true
          }
        }
      }
    })
  }

  // 兜底: 未分层(环)节点放到第 0 层
  nodes.forEach((n) => {
    if (!layers.has(n.node_id)) layers.set(n.node_id, 0)
  })

  // 按层分组,层内均匀分布
  const layerGroups = new Map<number, string[]>()
  layers.forEach((layer, nodeId) => {
    if (!layerGroups.has(layer)) layerGroups.set(layer, [])
    layerGroups.get(layer)!.push(nodeId)
  })

  const sortedLayers = Array.from(layerGroups.keys()).sort((a, b) => a - b)

  sortedLayers.forEach((layer) => {
    const group = layerGroups.get(layer)!
    const totalHeight = (group.length - 1) * LAYER_GAP_Y
    const startY = -totalHeight / 2
    group.forEach((nodeId, idx) => {
      positions.set(nodeId, {
        x: layer * LAYER_GAP_X,
        y: startY + idx * LAYER_GAP_Y,
      })
    })
  })

  return positions
}

// 计算 SVG 路径(贝塞尔曲线连接两个节点)
function computeEdgePath(
  source: { x: number; y: number },
  target: { x: number; y: number }
): string {
  const sx = source.x + NODE_WIDTH
  const sy = source.y + NODE_HEIGHT / 2
  const tx = target.x
  const ty = target.y + NODE_HEIGHT / 2
  const dx = (tx - sx) / 2
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`
}

// 从 result 字段提取 mock worker 对话
function extractWorkerMessages(node: DAGNode): WorkerMessage[] {
  const messages: WorkerMessage[] = []
  if (node.brief) {
    messages.push({
      role: 'user',
      content: node.brief,
      ts: node.created_at,
    })
  }
  if (node.result) {
    // 简单 mock: result 字段就是 assistant 回复
    messages.push({
      role: 'assistant',
      content: node.result,
      ts: node.updated_at,
    })
  }
  if (messages.length === 0) {
    messages.push({
      role: 'system',
      content: `节点 ${node.title} (#${node.node_id}) 暂无 worker 对话记录`,
      ts: null,
    })
  }
  return messages
}

// =========================================================================
// DAGView 子组件 — 单 DAG 的完整渲染 (画布 + 节点详情 + 配置面板)
// =========================================================================

interface DAGViewProps {
  dagId: string
  /** 变化时触发重新加载 DAG 数据 (SSE 驱动) */
  refreshTrigger: number
  /** 是否为当前聚焦的 DAG (影响布局权重) */
  isSelected: boolean
  /** 点击选中此 DAG */
  onSelect: () => void
}

function DAGView({ dagId, refreshTrigger, isSelected, onSelect }: DAGViewProps) {
  const [dagData, setDagData] = useState<DAGData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [showConfigPanel, setShowConfigPanel] = useState(false)

  // 画布容器 ref (用于 running 节点自动聚焦滚动)
  const canvasContainerRef = useRef<HTMLDivElement>(null)
  // running 节点 ref (自动聚焦)
  const runningNodeRef = useRef<HTMLDivElement | null>(null)

  // 加载 DAG 详情
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    apiGet<DAGData>(`/dag/${encodeURIComponent(dagId)}`)
      .then((data) => {
        if (!cancelled) {
          setDagData(data)
          setSelectedNodeId(null)
        }
      })
      .catch((e: any) => {
        if (!cancelled) {
          // 多 DAG 模式下 dag-swarm-{id} 可能尚未持久化,静默处理
          setError(e?.message || '加载 DAG 详情失败')
          setDagData(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [dagId, refreshTrigger])

  // 计算节点布局
  const layout = useMemo(() => {
    if (!dagData) return new Map<string, { x: number; y: number }>()
    return computeLayout(dagData.nodes, dagData.edges)
  }, [dagData])

  // 选中节点详情
  const selectedNode = useMemo(() => {
    if (!dagData || !selectedNodeId) return null
    return dagData.nodes.find((n) => n.node_id === selectedNodeId) || null
  }, [dagData, selectedNodeId])

  // worker 对话
  const workerMessages = useMemo(() => {
    if (!selectedNode) return []
    return extractWorkerMessages(selectedNode)
  }, [selectedNode])

  // 第一个 running 节点 (用于自动聚焦)
  const runningNodeId = useMemo(() => {
    if (!dagData) return null
    const running = dagData.nodes.find((n) => n.status === 'running')
    return running?.node_id || null
  }, [dagData])

  // running 节点自动聚焦: 数据变化时滚动到 running 节点
  useEffect(() => {
    if (runningNodeRef.current && canvasContainerRef.current) {
      try {
        runningNodeRef.current.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'center',
        })
      } catch {
        // 某些环境不支持 scrollIntoView options,忽略
      }
    }
  }, [dagData, runningNodeId])

  // 计算画布尺寸
  const canvasSize = useMemo(() => {
    if (layout.size === 0) return { width: 800, height: 400, offsetX: 40, offsetY: 40 }
    let maxX = 0
    let maxY = 0
    let minX = 0
    let minY = 0
    layout.forEach((p) => {
      maxX = Math.max(maxX, p.x + NODE_WIDTH)
      maxY = Math.max(maxY, p.y + NODE_HEIGHT)
      minX = Math.min(minX, p.x)
      minY = Math.min(minY, p.y)
    })
    return {
      width: maxX - minX + 80,
      height: maxY - minY + 80,
      offsetX: -minX + 40,
      offsetY: -minY + 40,
    }
  }, [layout])

  return (
    <div
      className="flex flex-col gap-3 rounded-xl p-3"
      style={{
        background: 'var(--bg-card)',
        border: isSelected ? '2px solid var(--accent)' : '1px solid var(--border)',
        minWidth: 480,
        flex: isSelected ? '1 1 0' : '0 0 auto',
        maxWidth: isSelected ? 'none' : 520,
      }}
    >
      {/* DAG 标题栏 */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          🕸 {dagId}
        </span>
        {runningNodeId && (
          <span
            className="px-2 py-0.5 rounded-full text-xs"
            style={{
              background: STATUS_COLORS.running.bg,
              color: STATUS_COLORS.running.text,
              border: `1px solid ${STATUS_COLORS.running.border}`,
            }}
          >
            🔄 运行中
          </span>
        )}
        {!isSelected && (
          <button
            onClick={onSelect}
            className="ml-auto px-2 py-0.5 rounded text-xs"
            style={{
              background: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            聚焦
          </button>
        )}
      </div>

      {/* 执行前审批横幅 (T2.3) */}
      <ApprovalBanner
        dagId={dagId}
        onChanged={() => {
          // 审批状态变化后重新加载 DAG 数据
          apiGet<DAGData>(`/dag/${encodeURIComponent(dagId)}`)
            .then((data) => setDagData(data))
            .catch(() => {})
        }}
      />

      {error && (
        <div
          className="p-3 rounded-lg text-sm"
          style={{
            background: 'rgba(239, 68, 68, 0.1)',
            color: '#EF4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8" style={{ color: 'var(--text-secondary)' }}>
          加载中...
        </div>
      ) : !dagData ? (
        <div
          className="flex flex-col items-center justify-center gap-2 py-12"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="text-5xl">🕸</div>
          <div className="text-sm">DAG 数据为空或尚未创建</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-3">
          {/* 左侧:画布 */}
          <div
            ref={canvasContainerRef}
            className="rounded-xl p-3 overflow-auto"
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              minHeight: 400,
              maxHeight: 560,
            }}
          >
            <div
              style={{
                position: 'relative',
                width: canvasSize.width,
                height: canvasSize.height,
              }}
            >
              {/* SVG 边层 */}
              <svg
                width={canvasSize.width}
                height={canvasSize.height}
                style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
              >
                <defs>
                  <marker
                    id={`arrow-${dagId}`}
                    markerWidth="10"
                    markerHeight="10"
                    refX="9"
                    refY="3"
                    orient="auto"
                    markerUnits="strokeWidth"
                  >
                    <path d="M0,0 L0,6 L9,3 z" fill="#9CA3AF" />
                  </marker>
                </defs>
                {dagData.edges.map((edge) => {
                  const src = layout.get(edge.source_node_id)
                  const tgt = layout.get(edge.target_node_id)
                  if (!src || !tgt) return null
                  const path = computeEdgePath(
                    { x: src.x + canvasSize.offsetX, y: src.y + canvasSize.offsetY },
                    { x: tgt.x + canvasSize.offsetX, y: tgt.y + canvasSize.offsetY }
                  )
                  return (
                    <g key={edge.id}>
                      <path
                        d={path}
                        fill="none"
                        stroke={edge.edge_type === 'condition' ? '#F59E0B' : '#9CA3AF'}
                        strokeWidth={2}
                        strokeDasharray={edge.edge_type === 'condition' ? '5,5' : 'none'}
                        markerEnd={`url(#arrow-${dagId})`}
                      />
                      {edge.condition && (
                        <text
                          x={(src.x + tgt.x) / 2 + canvasSize.offsetX + NODE_WIDTH / 2}
                          y={(src.y + tgt.y) / 2 + canvasSize.offsetY}
                          fill="#6B7280"
                          fontSize="10"
                          textAnchor="middle"
                        >
                          {edge.condition.length > 20
                            ? edge.condition.slice(0, 20) + '...'
                            : edge.condition}
                        </text>
                      )}
                    </g>
                  )
                })}
              </svg>

              {/* 节点层 */}
              {dagData.nodes.map((node) => {
                const pos = layout.get(node.node_id)
                if (!pos) return null
                const color = STATUS_COLORS[node.status] || STATUS_COLORS.pending
                const isSelectedNode = selectedNodeId === node.node_id
                const isRunning = node.status === 'running'
                return (
                  <div
                    key={node.id}
                    ref={isRunning ? runningNodeRef : undefined}
                    onClick={() => setSelectedNodeId(node.node_id)}
                    style={{
                      position: 'absolute',
                      left: pos.x + canvasSize.offsetX,
                      top: pos.y + canvasSize.offsetY,
                      width: NODE_WIDTH,
                      height: NODE_HEIGHT,
                      background: color.bg,
                      border: `2px solid ${isSelectedNode ? 'var(--accent)' : color.border}`,
                      borderRadius: 10,
                      padding: '8px 10px',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      boxShadow: isSelectedNode
                        ? '0 4px 12px rgba(0,0,0,0.15)'
                        : isRunning
                          ? '0 0 0 3px rgba(59, 130, 246, 0.3)'
                          : '0 1px 3px rgba(0,0,0,0.08)',
                      transition: 'box-shadow 0.15s, border-color 0.15s',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontWeight: 600,
                        fontSize: 13,
                        color: color.text,
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      <span>{NODE_TYPE_ICON[node.node_type] || '•'}</span>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {node.title || node.node_id}
                      </span>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: 10,
                        color: color.text,
                        opacity: 0.85,
                      }}
                    >
                      <span>{color.label}</span>
                      {node.model && (
                        <span style={{ fontFamily: 'monospace' }}>{node.model}</span>
                      )}
                    </div>
                    {/* 状态条 */}
                    <div
                      style={{
                        height: 3,
                        borderRadius: 2,
                        background: color.border,
                        opacity: 0.6,
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </div>

          {/* 右侧:节点详情 + worker 对话 */}
          <div
            className="rounded-xl p-3 flex flex-col gap-3"
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              maxHeight: 560,
            }}
          >
            {selectedNode ? (
              <>
                <div>
                  <div
                    className="text-sm font-semibold"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {NODE_TYPE_ICON[selectedNode.node_type] || '•'} {selectedNode.title}
                  </div>
                  <div
                    className="text-xs mt-1"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    #{selectedNode.node_id}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className="px-2 py-0.5 rounded-full text-xs"
                    style={{
                      background:
                        STATUS_COLORS[selectedNode.status]?.bg || '#F3F4F6',
                      color:
                        STATUS_COLORS[selectedNode.status]?.text || '#4B5563',
                      border: `1px solid ${
                        STATUS_COLORS[selectedNode.status]?.border || '#9CA3AF'
                      }`,
                    }}
                  >
                    {STATUS_COLORS[selectedNode.status]?.label || selectedNode.status}
                  </span>
                  {selectedNode.model && (
                    <span
                      className="px-2 py-0.5 rounded-full text-xs"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      🤖 {selectedNode.model}
                    </span>
                  )}
                  {/* 预检通过标记 */}
                  {selectedNode.config?.precheck_passed === true && (
                    <span
                      className="px-2 py-0.5 rounded-full text-xs"
                      style={{
                        background: 'rgba(16, 185, 129, 0.1)',
                        color: '#065F46',
                        border: '1px solid rgba(16, 185, 129, 0.3)',
                      }}
                    >
                      ✓ 已预检
                    </span>
                  )}
                  <button
                    onClick={() => setShowConfigPanel(true)}
                    className="ml-auto px-2 py-0.5 rounded-lg text-xs"
                    style={{
                      background: 'var(--bg-secondary)',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    🔧 配置
                  </button>
                </div>
                {selectedNode.brief && (
                  <div
                    className="text-xs p-2 rounded-lg"
                    style={{
                      background: 'var(--bg-card)',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <div className="font-semibold mb-1">Brief</div>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{selectedNode.brief}</div>
                  </div>
                )}

                {/* Worker 对话区 */}
                <div
                  className="flex-1 flex flex-col gap-2 overflow-y-auto"
                  style={{ minHeight: 120 }}
                >
                  <div
                    className="text-xs font-semibold"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    💬 Worker 对话
                  </div>
                  {workerMessages.map((msg, i) => (
                    <div
                      key={i}
                      className="text-xs p-2 rounded-lg"
                      style={{
                        background:
                          msg.role === 'user'
                            ? 'rgba(59, 130, 246, 0.08)'
                            : msg.role === 'assistant'
                              ? 'rgba(16, 185, 129, 0.08)'
                              : 'var(--bg-secondary)',
                        border: `1px solid ${
                          msg.role === 'user'
                            ? 'rgba(59, 130, 246, 0.2)'
                            : msg.role === 'assistant'
                              ? 'rgba(16, 185, 129, 0.2)'
                              : 'var(--border)'
                        }`,
                        color: 'var(--text-primary)',
                      }}
                    >
                      <div
                        className="font-semibold mb-1"
                        style={{
                          color:
                            msg.role === 'user'
                              ? '#3B82F6'
                              : msg.role === 'assistant'
                                ? '#10B981'
                                : 'var(--text-secondary)',
                        }}
                      >
                        {msg.role === 'user'
                          ? '👤 User'
                          : msg.role === 'assistant'
                            ? '🤖 Assistant'
                            : 'ℹ️ System'}
                      </div>
                      <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div
                className="flex flex-col items-center justify-center flex-1 gap-2"
                style={{ color: 'var(--text-secondary)' }}
              >
                <div className="text-4xl">👆</div>
                <div className="text-sm text-center">点击节点查看详情与 worker 对话</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 节点配置面板 (T2.4) - 浮层 */}
      {showConfigPanel && selectedNode && (
        <div
          className="fixed inset-0 flex items-center justify-center p-4 z-50"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setShowConfigPanel(false)}
        >
          <div
            className="w-full max-w-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <NodeConfigPanel
              dagId={dagId}
              node={selectedNode}
              onClose={() => setShowConfigPanel(false)}
              onPrechecked={() => {
                // 预检成功后刷新 DAG 数据
                apiGet<DAGData>(`/dag/${encodeURIComponent(dagId)}`)
                  .then((data) => setDagData(data))
                  .catch(() => {})
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// =========================================================================
// DAGCanvas 主组件 — DAG 列表 + 多 DAG 并排渲染
// =========================================================================

export default function DAGCanvas() {
  const [dags, setDags] = useState<DAGSummary[]>([])
  const [selectedDagId, setSelectedDagId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 创建 DAG 表单
  const [createOpen, setCreateOpen] = useState(false)
  const [newDagId, setNewDagId] = useState('')
  const [creating, setCreating] = useState(false)

  // SSE 驱动的刷新触发器 (runningTasks 变化时递增,触发 DAGView 重新加载)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // 从全局 store 获取 SSE 状态 (v2.3.0: 多 DAG + 实时事件)
  const { state } = useGlobalState()
  const visibleDagIds = state.visibleDagIds
  const runningTasks = state.runningTasks
  // memoryEvents 作为辅助信号 (链路 2: memory.graph.updated → DAG 实时反映)
  const memoryEvents = state.memoryEvents

  // 加载 DAG 列表
  const loadDags = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<DAGSummary[]>('/dag/list')
      setDags(data || [])
      if (data && data.length > 0 && !selectedDagId) {
        setSelectedDagId(data[0].dag_id)
      }
    } catch (e: any) {
      setError(e?.message || '加载 DAG 列表失败')
    } finally {
      setLoading(false)
    }
  }, [selectedDagId])

  useEffect(() => {
    loadDags()
  }, [])

  // 监听 runningTasks 变化 (SSE 驱动),触发所有 DAGView 重新加载
  // swarm.created/started/completed/failed 事件会更新 runningTasks,
  // dag.node.started/completed 事件也会通过 EVENT_DISPATCH 进入 store,
  // 这里通过 runningTasks 引用变化感知并刷新画布。
  useEffect(() => {
    setRefreshTrigger((t) => t + 1)
  }, [runningTasks])

  // 辅助信号: memoryEvents 变化时也触发 DAG 刷新
  // 链路 2: memory.graph.updated → DAGCanvas 实时反映
  // DAGCanvas 主要订阅 runningTasks,memoryEvents 作为辅助信号确保记忆心跳更新后 DAG 同步刷新
  useEffect(() => {
    if (!memoryEvents || memoryEvents.length === 0) return
    setRefreshTrigger((t) => t + 1)
  }, [memoryEvents])

  // 多 DAG 模式: visibleDagIds 非空时并排渲染
  const multiDagMode = visibleDagIds.length > 0

  // 多 DAG 模式下,默认聚焦第一个可见 DAG
  useEffect(() => {
    if (multiDagMode && !visibleDagIds.includes(selectedDagId || '')) {
      setSelectedDagId(visibleDagIds[0])
    }
  }, [multiDagMode, visibleDagIds, selectedDagId])

  // 创建示例 DAG
  async function handleCreateSample() {
    if (!newDagId.trim()) {
      setError('请填写 DAG ID')
      return
    }
    setCreating(true)
    setError(null)
    try {
      await apiPost('/dag', {
        dag_id: newDagId.trim(),
        nodes: [
          { node_id: 'start', title: '开始', node_type: 'task', status: 'pending', brief: '开始执行任务' },
          { node_id: 'review', title: '审批', node_type: 'approval', status: 'pending', brief: '请审批此计划' },
          { node_id: 'exec', title: '执行', node_type: 'task', status: 'pending', brief: '执行核心任务' },
          { node_id: 'end', title: '结束', node_type: 'task', status: 'pending', brief: '汇总结果' },
        ],
        edges: [
          { source_node_id: 'start', target_node_id: 'review' },
          { source_node_id: 'review', target_node_id: 'exec' },
          { source_node_id: 'exec', target_node_id: 'end' },
        ],
      })
      setCreateOpen(false)
      setNewDagId('')
      await loadDags()
      setSelectedDagId(newDagId.trim())
    } catch (e: any) {
      setError(e?.message || '创建 DAG 失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-4"
      style={{
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border)',
      }}
    >
      {/* 顶部标题 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          🕸 DAG 画布
          {multiDagMode && (
            <span
              className="ml-2 px-2 py-0.5 rounded-full text-xs"
              style={{
                background: 'var(--accent)',
                color: '#fff',
              }}
            >
              多任务并排 ({visibleDagIds.length})
            </span>
          )}
        </h2>
        <button
          onClick={() => setCreateOpen(true)}
          className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          + 新建 DAG
        </button>
      </div>

      {/* SSE 连接状态指示器 (v2.3.0) */}
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{
            background: state.sseConnected ? '#10B981' : '#9CA3AF',
            boxShadow: state.sseConnected ? '0 0 6px #10B981' : 'none',
          }}
        />
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {state.sseConnected ? 'SSE 已连接' : 'SSE 未连接'}
          {runningTasks.length > 0 && ` · ${runningTasks.length} 个运行中任务`}
        </span>
      </div>

      {/* DAG 选择器 (单 DAG 模式) */}
      {!multiDagMode && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            选择 DAG:
          </span>
          {dags.length === 0 ? (
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              暂无 DAG,点击右上角创建
            </span>
          ) : (
            dags.map((d) => (
              <button
                key={d.dag_id}
                onClick={() => setSelectedDagId(d.dag_id)}
                className="px-3 py-1 rounded-lg text-xs transition"
                style={{
                  background:
                    selectedDagId === d.dag_id ? 'var(--accent)' : 'var(--bg-secondary)',
                  color: selectedDagId === d.dag_id ? '#fff' : 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                {d.dag_id} ({d.node_count})
              </button>
            ))
          )}
        </div>
      )}

      {/* 多 DAG 模式: 可见 DAG 标签栏 */}
      {multiDagMode && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            可见 DAG:
          </span>
          {visibleDagIds.map((id) => (
            <button
              key={id}
              onClick={() => setSelectedDagId(id)}
              className="px-3 py-1 rounded-lg text-xs transition"
              style={{
                background:
                  selectedDagId === id ? 'var(--accent)' : 'var(--bg-secondary)',
                color: selectedDagId === id ? '#fff' : 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            >
              {id}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div
          className="p-3 rounded-lg text-sm"
          style={{
            background: 'rgba(239, 68, 68, 0.1)',
            color: '#EF4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* 画布区域 */}
      {loading ? (
        <div className="text-center py-8" style={{ color: 'var(--text-secondary)' }}>
          加载中...
        </div>
      ) : multiDagMode ? (
        // 多 DAG 并排渲染 (横向 flex,可滚动)
        <div
          className="flex gap-4 overflow-x-auto"
          style={{ minHeight: 480, paddingBottom: 8 }}
        >
          {visibleDagIds.map((id) => (
            <DAGView
              key={id}
              dagId={id}
              refreshTrigger={refreshTrigger}
              isSelected={selectedDagId === id}
              onSelect={() => setSelectedDagId(id)}
            />
          ))}
        </div>
      ) : selectedDagId ? (
        // 单 DAG 模式
        <DAGView
          key={selectedDagId}
          dagId={selectedDagId}
          refreshTrigger={refreshTrigger}
          isSelected={true}
          onSelect={() => {}}
        />
      ) : (
        <div
          className="flex flex-col items-center justify-center gap-2 py-12"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="text-5xl">🕸</div>
          <div>选择或创建一个 DAG 以查看画布</div>
        </div>
      )}

      {/* 创建 DAG 对话框 */}
      {createOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center p-4 z-50"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setCreateOpen(false)}
        >
          <div
            className="rounded-2xl p-5 w-full max-w-md flex flex-col gap-3"
            style={{
              background: 'var(--bg-card)',
              boxShadow: 'var(--shadow-xl)',
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
              创建示例 DAG
            </h3>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                DAG ID
              </label>
              <input
                type="text"
                placeholder="例如: dag-demo-1"
                value={newDagId}
                onInput={(e) => setNewDagId((e.target as HTMLInputElement).value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setCreateOpen(false)}
                className="px-4 py-1.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                取消
              </button>
              <button
                onClick={handleCreateSample}
                disabled={creating || !newDagId.trim()}
                className="px-4 py-1.5 rounded-lg text-sm font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--accent)' }}
              >
                {creating ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
