import { useState, useEffect, useRef } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

// ===== 工具函数 =====

/** 获取蜂群任务的目标描述(兼容 goal / description 两种字段名) */
function getSwarmGoal(s: any): string {
  return s?.description ?? s?.goal ?? ''
}

/** 获取蜂群任务的进度百分比 */
function getSwarmProgress(s: any): number {
  // 如果后端直接提供了 progress 字段,直接使用
  if (typeof s?.progress === 'number') return s.progress
  // 根据状态推断
  const status = s?.status || 'pending'
  if (status === 'completed') return 100
  if (status === 'pending' || status === 'cancelled' || status === 'failed') return 0
  // 根据 workers 完成情况计算
  const workers = s?.workers ?? []
  if (workers.length === 0) return 5 // 运行中但还没有 worker
  const completed = workers.filter((w: any) => w.status === 'completed').length
  return Math.round((completed / workers.length) * 100)
}

/** 获取状态标签信息 */
function getStatusInfo(status: string): { label: string; color: string; bg: string; icon: string } {
  switch (status) {
    case 'completed':
      return { label: '已完成', color: '#38A169', bg: '#C6F6D5', icon: '✅' }
    case 'running':
    case 'decomposing':
      return { label: '运行中', color: 'var(--accent)', bg: 'var(--bg-secondary)', icon: '🔄' }
    case 'failed':
    case 'cancelled':
      return { label: status === 'cancelled' ? '已取消' : '失败', color: '#e53e3e', bg: '#FED7D7', icon: '❌' }
    case 'pending':
    default:
      return { label: '等待中', color: 'var(--text-secondary)', bg: 'var(--bg-secondary)', icon: '⏳' }
  }
}

/** 获取子任务状态图标 */
function getSubtaskIcon(subtask: any, workers: any[]): string {
  const subtaskWorkers = workers.filter(w => w.subtask_id === subtask.id)
  if (subtaskWorkers.length === 0) return '○'
  const completed = subtaskWorkers.filter(w => w.status === 'completed').length
  if (completed === subtaskWorkers.length) return '✅'
  if (completed > 0) return '🔄'
  return '⏳'
}

/** 格式化时间 */
function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const min = Math.floor(diff / 60000)
  const hour = Math.floor(diff / 3600000)
  const day = Math.floor(diff / 86400000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  if (hour < 24) return `${hour} 小时前`
  if (day < 7) return `${day} 天前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ===== 组件 =====

export default function SwarmProgress() {
  const [swarms, setSwarms] = useState<any[]>([])
  const [personas, setPersonas] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')

  // 创建表单
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [personaId, setPersonaId] = useState<number | ''>('')
  const [creating, setCreating] = useState(false)

  const pollRef = useRef<number | null>(null)

  // 加载蜂群任务列表
  const loadSwarms = async () => {
    try {
      const data = await apiGet<any[]>('/swarm')
      setSwarms(data || [])
    } catch (e: any) {
      // 静默失败,避免轮询时频繁报错
    } finally {
      setLoading(false)
    }
  }

  // 加载角色列表(用于下拉选择)
  const loadPersonas = async () => {
    try {
      const data = await apiGet<any[]>('/persona')
      setPersonas(data || [])
      if (data && data.length > 0 && personaId === '') {
        setPersonaId(data[0].id)
      }
    } catch {
      // 忽略
    }
  }

  // 初始化加载
  useEffect(() => {
    loadSwarms()
    loadPersonas()
  }, [])

  // 轮询:每 3 秒刷新运行中的任务
  useEffect(() => {
    const hasRunning = swarms.some(s => {
      const st = s?.status || 'pending'
      return st === 'running' || st === 'decomposing' || st === 'pending'
    })
    if (hasRunning) {
      pollRef.current = window.setTimeout(() => {
        loadSwarms()
      }, 3000)
    }
    return () => {
      if (pollRef.current !== null) {
        clearTimeout(pollRef.current)
        pollRef.current = null
      }
    }
  }, [swarms])

  // 切换展开/折叠
  const toggleExpand = (id: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        // 展开时加载详细信息(包含 workers)
        loadSwarmDetail(id)
      }
      return next
    })
  }

  // 加载单个蜂群详情(包含 workers)
  const loadSwarmDetail = async (id: number) => {
    try {
      const detail = await apiGet<any>(`/swarm/${id}`)
      if (detail) {
        setSwarms(prev => prev.map(s => (s.id === id ? detail : s)))
      }
    } catch {
      // 忽略
    }
  }

  // 创建蜂群任务
  const handleCreate = async () => {
    if (!title.trim() || !desc.trim() || personaId === '') {
      setError('请填写标题、描述并选择角色')
      return
    }
    setCreating(true)
    setError('')
    try {
      // 后端 SwarmCreate 需要 persona_id, goal, title
      const created = await apiPost<any>('/swarm', {
        title: title.trim(),
        goal: desc.trim(),
        persona_id: personaId,
      })
      setSwarms(prev => [created, ...prev])
      setTitle('')
      setDesc('')
      // 自动展开新创建的任务
      if (created?.id) {
        setExpanded(prev => new Set(prev).add(created.id))
      }
    } catch (e: any) {
      setError(e?.message || '创建蜂群任务失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="h-full w-full overflow-y-auto" style={{ background: 'var(--bg-primary)', padding: 'var(--spacing-lg)' }}>
      {/* 顶部标题 */}
      <div style={{ marginBottom: 'var(--spacing-lg)' }}>
        <h2 style={{ fontSize: 'var(--font-xl)', fontWeight: 700, color: 'var(--text-primary)' }}>
          🐝 蜂群任务
        </h2>
        <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: '4px' }}>
          创建多智能体协作任务,蜂群将自动分解、执行并验证
        </p>
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          style={{
            padding: 'var(--spacing-sm) var(--spacing-md)',
            marginBottom: 'var(--spacing-md)',
            borderRadius: 'var(--radius-md)',
            background: '#FFF0F0',
            color: '#e53e3e',
            fontSize: 'var(--font-sm)',
            border: '1px solid #F5C6CB',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* ===== 创建蜂群任务表单 ===== */}
      <div
        style={{
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-xl)',
          padding: 'var(--spacing-lg)',
          marginBottom: 'var(--spacing-lg)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <h3 style={{ fontSize: 'var(--font-base)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 'var(--spacing-md)' }}>
          ✨ 创建新任务
        </h3>

        <div className="grid gap-3" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 'var(--spacing-sm)' }}>
          {/* 标题 */}
          <input
            type="text"
            value={title}
            onInput={(e) => setTitle((e.target as HTMLInputElement).value)}
            placeholder="任务标题..."
            style={{
              padding: '10px var(--spacing-md)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border)',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: 'var(--font-sm)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          {/* 角色选择 */}
          <select
            value={personaId}
            onChange={(e) => setPersonaId(Number((e.target as HTMLSelectElement).value))}
            style={{
              padding: '10px var(--spacing-md)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border)',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: 'var(--font-sm)',
              outline: 'none',
              cursor: 'pointer',
              boxSizing: 'border-box',
            }}
          >
            <option value="">选择角色...</option>
            {personas.map(p => (
              <option key={p.id} value={p.id}>
                {p.avatar || '🧸'} {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* 描述 */}
        <textarea
          value={desc}
          onInput={(e) => setDesc((e.target as HTMLTextAreaElement).value)}
          placeholder="描述任务目标,蜂群将自动分解为子任务..."
          rows={2}
          className="resize-y"
          style={{
            width: '100%',
            padding: '10px var(--spacing-md)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)',
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            fontSize: 'var(--font-sm)',
            outline: 'none',
            boxSizing: 'border-box',
            marginBottom: 'var(--spacing-sm)',
          }}
        />

        {/* 创建按钮 */}
        <button
          onClick={handleCreate}
          disabled={creating || !title.trim() || !desc.trim() || personaId === ''}
          className="transition-all"
          style={{
            padding: '10px var(--spacing-lg)',
            borderRadius: 'var(--radius-md)',
            background: creating || !title.trim() || !desc.trim() || personaId === '' ? 'var(--bg-secondary)' : 'var(--accent)',
            color: creating || !title.trim() || !desc.trim() || personaId === '' ? 'var(--text-secondary)' : '#fff',
            fontSize: 'var(--font-sm)',
            fontWeight: 600,
            border: 'none',
            cursor: creating || !title.trim() || !desc.trim() || personaId === '' ? 'default' : 'pointer',
          }}
        >
          {creating ? '创建中...' : '🐝 创建蜂群任务'}
        </button>
      </div>

      {/* ===== 蜂群任务列表 ===== */}
      {loading ? (
        <div className="flex items-center justify-center" style={{ padding: 'var(--spacing-3xl)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-base)' }}>加载中...</span>
        </div>
      ) : swarms.length === 0 ? (
        // 空状态
        <div
          className="flex flex-col items-center justify-center"
          style={{
            padding: 'var(--spacing-3xl)',
            color: 'var(--text-secondary)',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius-xl)',
            border: '1px solid var(--border)',
          }}
        >
          <span style={{ fontSize: '64px', marginBottom: 'var(--spacing-md)' }}>🐝</span>
          <h3 style={{ fontSize: 'var(--font-lg)', color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
            还没有蜂群任务
          </h3>
          <p style={{ fontSize: 'var(--font-sm)' }}>
            在上方创建你的第一个蜂群任务,让多智能体帮你完成复杂工作
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {swarms.map(swarm => (
            <SwarmTaskCard
              key={swarm.id}
              swarm={swarm}
              expanded={expanded.has(swarm.id)}
              onToggle={() => toggleExpand(swarm.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ===== 蜂群任务卡片子组件 =====

function SwarmTaskCard({ swarm, expanded, onToggle }: { swarm: any; expanded: boolean; onToggle: () => void }) {
  const status = swarm?.status || 'pending'
  const statusInfo = getStatusInfo(status)
  const progress = getSwarmProgress(swarm)
  const subtasks = swarm?.subtasks ?? []
  const workers = swarm?.workers ?? []
  const goal = getSwarmGoal(swarm)

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-xl)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-sm)',
        overflow: 'hidden',
      }}
    >
      {/* 卡片头部(可点击展开) */}
      <div
        onClick={onToggle}
        className="transition-all"
        style={{
          padding: 'var(--spacing-md) var(--spacing-lg)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--spacing-md)',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-secondary)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {/* 展开/折叠图标 */}
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)', transition: 'transform 0.2s', transform: expanded ? 'rotate(90deg)' : 'rotate(0)' }}>
          ▶
        </span>

        {/* 标题 + 描述 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 'var(--font-base)', fontWeight: 600, color: 'var(--text-primary)' }}>
              {swarm.title || goal.slice(0, 50) || '未命名任务'}
            </span>
            {/* 状态标签 */}
            <span
              style={{
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: statusInfo.bg,
                color: statusInfo.color,
                fontSize: 'var(--font-xs)',
                fontWeight: 600,
                whiteSpace: 'nowrap',
              }}
            >
              {statusInfo.icon} {statusInfo.label}
            </span>
          </div>
          {goal && (
            <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {goal}
            </div>
          )}
        </div>

        {/* 进度百分比 */}
        <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
          {progress}%
        </div>
      </div>

      {/* 进度条 */}
      <div style={{ padding: '0 var(--spacing-lg)', marginBottom: 'var(--spacing-sm)' }}>
        <div
          style={{
            height: '6px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--bg-secondary)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${progress}%`,
              borderRadius: 'var(--radius-full)',
              background: status === 'completed' ? '#38A169' : 'var(--accent)',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
      </div>

      {/* 展开内容:子任务列表 */}
      {expanded && (
        <div
          style={{
            padding: 'var(--spacing-md) var(--spacing-lg)',
            borderTop: '1px solid var(--border)',
            background: 'var(--bg-primary)',
          }}
        >
          {subtasks.length === 0 ? (
            <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', textAlign: 'center', padding: 'var(--spacing-md)' }}>
              {status === 'decomposing' ? '🔄 正在分解任务...' : '暂无子任务'}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              <div style={{ fontSize: 'var(--font-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 'var(--spacing-xs)' }}>
                子任务 ({subtasks.length})
              </div>
              {subtasks.map((st: any, idx: number) => {
                const icon = getSubtaskIcon(st, workers)
                const subtaskWorkers = workers.filter((w: any) => w.subtask_id === st.id)
                const completedWorkers = subtaskWorkers.filter((w: any) => w.status === 'completed').length
                return (
                  <div
                    key={st.id || idx}
                    className="flex items-center gap-2"
                    style={{
                      padding: 'var(--spacing-sm) var(--spacing-md)',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <span style={{ fontSize: '14px' }}>{icon}</span>
                    <span style={{ fontSize: 'var(--font-sm)', color: 'var(--text-primary)', flex: 1 }}>
                      {st.title || st.id}
                    </span>
                    {subtaskWorkers.length > 0 && (
                      <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)' }}>
                        {completedWorkers}/{subtaskWorkers.length} workers
                      </span>
                    )}
                  </div>
                )
              })}

              {/* 任务结果 */}
              {swarm.result && (
                <div
                  style={{
                    marginTop: 'var(--spacing-sm)',
                    padding: 'var(--spacing-sm) var(--spacing-md)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                  }}
                >
                  <div style={{ fontSize: 'var(--font-xs)', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    📋 任务结果
                  </div>
                  <pre style={{ fontSize: 'var(--font-xs)', color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontFamily: 'monospace' }}>
                    {swarm.result}
                  </pre>
                </div>
              )}

              {/* 创建时间 */}
              <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: 'var(--spacing-xs)' }}>
                创建于 {formatTime(swarm.created_at)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
