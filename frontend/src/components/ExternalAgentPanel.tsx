// 外部 Agent 管理面板 (T3.6)
// 功能:
// 1. 已注册 Agent 列表(含能力查看)
// 2. 启用/禁用 Agent
// 3. 调用日志查看
// 4. 注册新 Agent(支持 claude_code/codex/gemini_cli/generic)
import { useState, useEffect, useMemo } from 'preact/hooks'
import { apiGet, apiPost, apiDelete } from '../lib/api'

// 外部 Agent 类型
interface ExternalAgent {
  id: number
  name: string
  agent_type: string  // generic/claude_code/codex/gemini_cli
  endpoint: string | null
  capabilities: string[]
  auth_token: string | null
  enabled: boolean
  last_called: string | null
  call_count: number
  created_at: string | null
}

// 调用日志类型
interface ACPCallLog {
  id: number
  agent_id: number
  action: string  // call_memory/call_swarm/call_skill
  request: string | null
  response: string | null
  status: string  // ok/error
  duration_ms: number
  created_at: string | null
}

// Agent 类型图标
const TYPE_ICONS: Record<string, string> = {
  claude_code: '🤖',
  codex: '💻',
  gemini_cli: '✨',
  generic: '🔌',
}

// Agent 类型颜色
const TYPE_COLORS: Record<string, string> = {
  claude_code: '#FF8C42',
  codex: '#3B82F6',
  gemini_cli: '#8B5CF6',
  generic: '#6B7280',
}

// Agent 类型中文标签
const TYPE_LABELS: Record<string, string> = {
  claude_code: 'Claude Code',
  codex: 'Codex CLI',
  gemini_cli: 'Gemini CLI',
  generic: '通用',
}

// 能力图标
const CAPABILITY_ICONS: Record<string, string> = {
  memory: '🧠',
  swarm: '🐝',
  skills: '⚡',
}

// 格式化时间
function formatTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

// 截断长文本
function truncate(s: string | null, max = 120): string {
  if (!s) return '—'
  return s.length > max ? s.slice(0, max) + '…' : s
}

// 解析日志 request/response 为可读 JSON
function prettyJson(s: string | null): string {
  if (!s) return '—'
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

export default function ExternalAgentPanel() {
  const [agents, setAgents] = useState<ExternalAgent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 仅显示启用的
  const [enabledOnly, setEnabledOnly] = useState(false)

  // 选中的 Agent(用于查看日志)
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [logs, setLogs] = useState<ACPCallLog[]>([])
  const [logsLoading, setLogsLoading] = useState(false)

  // 展开的 Agent(用于查看能力详情)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // 注册表单
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<{
    name: string
    agent_type: 'claude_code' | 'codex' | 'gemini_cli' | 'generic'
    endpoint: string
    capabilities: string
    auth_token: string
  }>({
    name: '',
    agent_type: 'claude_code',
    endpoint: '',
    capabilities: 'memory, swarm, skills',
    auth_token: '',
  })
  const [saving, setSaving] = useState(false)

  // 加载 Agent 列表
  async function loadAgents() {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<ExternalAgent[]>('/acp/agents?enabled_only=' + (enabledOnly ? 'true' : 'false'))
      setAgents(Array.isArray(data) ? data : [])
    } catch (e: any) {
      setError(e?.message || '加载 Agent 列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAgents()
  }, [enabledOnly])

  // 切换启用状态
  async function toggleEnabled(agent: ExternalAgent) {
    const action = agent.enabled ? 'disable' : 'enable'
    try {
      await apiPost(`/acp/agents/${agent.id}/${action}`)
      // 更新本地状态
      setAgents((prev) =>
        prev.map((a) =>
          a.id === agent.id ? { ...a, enabled: !a.enabled } : a,
        ),
      )
    } catch (e: any) {
      alert(e?.message || `${action} 失败`)
    }
  }

  // 删除 Agent
  async function removeAgent(agent: ExternalAgent) {
    if (!confirm(`确定删除 Agent「${agent.name}」吗?`)) return
    try {
      await apiDelete(`/acp/agents/${agent.id}`)
      if (selectedAgentId === agent.id) setSelectedAgentId(null)
      if (expandedId === agent.id) setExpandedId(null)
      await loadAgents()
    } catch (e: any) {
      alert(e?.message || '删除失败')
    }
  }

  // 加载日志
  async function loadLogs(agentId: number) {
    setLogsLoading(true)
    try {
      const data = await apiGet<ACPCallLog[]>(`/acp/logs?agent_id=${agentId}&limit=50`)
      setLogs(Array.isArray(data) ? data : [])
    } catch (e: any) {
      setLogs([])
      alert(e?.message || '加载日志失败')
    } finally {
      setLogsLoading(false)
    }
  }

  // 选中 Agent 查看日志
  function selectAgent(agentId: number) {
    if (selectedAgentId === agentId) {
      setSelectedAgentId(null)
      setLogs([])
      return
    }
    setSelectedAgentId(agentId)
    loadLogs(agentId)
  }

  // 展开/收起能力详情
  function toggleExpand(agentId: number) {
    setExpandedId(expandedId === agentId ? null : agentId)
  }

  // 保存新 Agent
  async function save() {
    if (!form.name.trim()) {
      alert('请输入 Agent 名称')
      return
    }
    setSaving(true)
    try {
      const caps = form.capabilities
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean)
      await apiPost('/acp/agents', {
        name: form.name,
        agent_type: form.agent_type,
        endpoint: form.endpoint || null,
        capabilities: caps,
        auth_token: form.auth_token || null,
      })
      setFormOpen(false)
      setForm({
        name: '',
        agent_type: 'claude_code',
        endpoint: '',
        capabilities: 'memory, swarm, skills',
        auth_token: '',
      })
      await loadAgents()
    } catch (e: any) {
      alert(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 打开注册表单(预设类型)
  function openCreate(presetType?: 'claude_code' | 'codex' | 'gemini_cli') {
    const type = presetType || 'claude_code'
    const defaultNames: Record<string, string> = {
      claude_code: 'Claude Code',
      codex: 'Codex CLI',
      gemini_cli: 'Gemini CLI',
    }
    const defaultEndpoints: Record<string, string> = {
      claude_code: 'cli://claude-code',
      codex: 'cli://codex',
      gemini_cli: 'cli://gemini',
    }
    setForm({
      name: defaultNames[type] || '',
      agent_type: type,
      endpoint: defaultEndpoints[type] || '',
      capabilities: 'memory, swarm, skills',
      auth_token: '',
    })
    setFormOpen(true)
  }

  // 统计信息
  const stats = useMemo(() => {
    const total = agents.length
    const enabled = agents.filter((a) => a.enabled).length
    const totalCalls = agents.reduce((sum, a) => sum + (a.call_count || 0), 0)
    return { total, enabled, disabled: total - enabled, totalCalls }
  }, [agents])

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-4"
      style={{
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border)',
      }}
    >
      {/* 顶部标题 + 操作 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
            🔌 外部 Agent 管理
          </h2>
          {/* 统计 */}
          <div className="flex gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>共 {stats.total}</span>
            <span>·</span>
            <span style={{ color: 'var(--accent)' }}>启用 {stats.enabled}</span>
            <span>·</span>
            <span>禁用 {stats.disabled}</span>
            <span>·</span>
            <span>调用 {stats.totalCalls} 次</span>
          </div>
        </div>
        <div className="flex gap-2">
          {/* 启用过滤 */}
          <button
            onClick={() => setEnabledOnly(!enabledOnly)}
            className="px-3 py-1.5 rounded-lg text-sm flex items-center gap-1.5"
            style={{
              background: enabledOnly ? 'var(--accent)' : 'var(--bg-primary)',
              color: enabledOnly ? '#FFFFFF' : 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            {enabledOnly ? '✓ ' : ''}仅启用
          </button>
          <button
            onClick={() => loadAgents()}
            className="px-3 py-1.5 rounded-lg text-sm"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            🔄 刷新
          </button>
          <button
            onClick={() => openCreate()}
            className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
            style={{ background: 'var(--accent)' }}
          >
            + 注册 Agent
          </button>
        </div>
      </div>

      {/* 快速注册预设 */}
      <div className="flex gap-2 flex-wrap">
        <span className="text-xs flex items-center" style={{ color: 'var(--text-secondary)' }}>
          快速注册:
        </span>
        {(['claude_code', 'codex', 'gemini_cli'] as const).map((t) => (
          <button
            key={t}
            onClick={() => openCreate(t)}
            className="px-2.5 py-1 rounded-md text-xs flex items-center gap-1"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: `1px solid ${TYPE_COLORS[t]}`,
            }}
          >
            <span>{TYPE_ICONS[t]}</span>
            <span>{TYPE_LABELS[t]}</span>
          </button>
        ))}
      </div>

      {/* Agent 列表 */}
      {loading ? (
        <div className="text-center py-10" style={{ color: 'var(--text-secondary)' }}>
          加载中...
        </div>
      ) : error ? (
        <div className="text-center py-10" style={{ color: '#EF4444' }}>
          {error}
        </div>
      ) : agents.length === 0 ? (
        <div
          className="flex flex-col items-center gap-2 py-10"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="text-5xl">🪄</div>
          <div>暂无外部 Agent</div>
          <div className="text-xs">点击「注册 Agent」或上方快速注册按钮添加</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {agents.map((agent) => {
            const isExpanded = expandedId === agent.id
            const isSelected = selectedAgentId === agent.id
            const typeColor = TYPE_COLORS[agent.agent_type] || TYPE_COLORS.generic
            return (
              <div
                key={agent.id}
                className="rounded-xl p-4 flex flex-col gap-2"
                style={{
                  background: 'var(--bg-primary)',
                  border: isSelected
                    ? `2px solid ${typeColor}`
                    : '1px solid var(--border)',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                {/* 卡片头部 */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <div
                      className="flex items-center justify-center w-10 h-10 rounded-lg text-xl flex-shrink-0"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      {TYPE_ICONS[agent.agent_type] || TYPE_ICONS.generic}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div
                        className="font-semibold text-sm truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {agent.name}
                      </div>
                      <div
                        className="text-xs truncate"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {agent.endpoint || '无端点'} · 调用 {agent.call_count} 次
                      </div>
                    </div>
                  </div>
                  <span
                    className="px-2 py-0.5 rounded-full text-xs font-medium text-white flex-shrink-0"
                    style={{ background: typeColor }}
                  >
                    {TYPE_LABELS[agent.agent_type] || agent.agent_type}
                  </span>
                </div>

                {/* 能力标签 */}
                <div className="flex flex-wrap gap-1">
                  {(agent.capabilities || []).map((cap) => (
                    <span
                      key={cap}
                      className="px-1.5 py-0.5 rounded text-xs flex items-center gap-0.5"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <span>{CAPABILITY_ICONS[cap] || '•'}</span>
                      <span>{cap}</span>
                    </span>
                  ))}
                </div>

                {/* 操作按钮 */}
                <div className="flex items-center justify-between gap-2 mt-1">
                  <button
                    onClick={() => toggleEnabled(agent)}
                    className="flex items-center gap-1.5 text-xs"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    <span
                      className="inline-block w-9 h-5 rounded-full relative transition"
                      style={{
                        background: agent.enabled ? 'var(--accent)' : '#D1D5DB',
                      }}
                    >
                      <span
                        className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
                        style={{ left: agent.enabled ? '18px' : '2px' }}
                      />
                    </span>
                    <span>{agent.enabled ? '已启用' : '已禁用'}</span>
                  </button>
                  <div className="flex gap-1">
                    <button
                      onClick={() => toggleExpand(agent.id)}
                      className="px-2 py-1 rounded-md text-xs"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {isExpanded ? '收起' : '详情'}
                    </button>
                    <button
                      onClick={() => selectAgent(agent.id)}
                      className="px-2 py-1 rounded-md text-xs"
                      style={{
                        background: isSelected ? typeColor : 'var(--bg-secondary)',
                        color: isSelected ? '#FFFFFF' : 'var(--text-primary)',
                      }}
                    >
                      日志
                    </button>
                    <button
                      onClick={() => removeAgent(agent)}
                      className="px-2 py-1 rounded-md text-xs text-white"
                      style={{ background: '#EF4444' }}
                    >
                      删除
                    </button>
                  </div>
                </div>

                {/* 展开详情 */}
                {isExpanded && (
                  <div
                    className="mt-2 p-3 rounded-lg flex flex-col gap-1.5 text-xs"
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>ID:</span>
                      <span style={{ color: 'var(--text-primary)' }}>{agent.id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>类型:</span>
                      <span style={{ color: 'var(--text-primary)' }}>{agent.agent_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>端点:</span>
                      <span style={{ color: 'var(--text-primary)' }} className="truncate ml-2">
                        {agent.endpoint || '—'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>认证:</span>
                      <span style={{ color: agent.auth_token ? 'var(--accent)' : 'var(--text-secondary)' }}>
                        {agent.auth_token ? '已设置' : '开放模式'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>调用次数:</span>
                      <span style={{ color: 'var(--text-primary)' }}>{agent.call_count}</span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>最后调用:</span>
                      <span style={{ color: 'var(--text-primary)' }}>
                        {formatTime(agent.last_called)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span style={{ color: 'var(--text-secondary)' }}>创建时间:</span>
                      <span style={{ color: 'var(--text-primary)' }}>
                        {formatTime(agent.created_at)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 调用日志面板 */}
      {selectedAgentId !== null && (
        <div
          className="rounded-xl p-4 flex flex-col gap-2"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              📋 调用日志 (Agent #{selectedAgentId})
            </h3>
            <div className="flex gap-2">
              <button
                onClick={() => loadLogs(selectedAgentId)}
                disabled={logsLoading}
                className="px-2 py-1 rounded-md text-xs"
                style={{
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-primary)',
                }}
              >
                {logsLoading ? '加载中...' : '🔄 刷新'}
              </button>
              <button
                onClick={() => {
                  setSelectedAgentId(null)
                  setLogs([])
                }}
                className="px-2 py-1 rounded-md text-xs"
                style={{
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-primary)',
                }}
              >
                ✕ 关闭
              </button>
            </div>
          </div>
          {logs.length === 0 ? (
            <div className="text-center py-6 text-xs" style={{ color: 'var(--text-secondary)' }}>
              {logsLoading ? '加载中...' : '暂无调用日志'}
            </div>
          ) : (
            <div className="flex flex-col gap-2 max-h-96 overflow-y-auto">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="rounded-lg p-2.5 flex flex-col gap-1 text-xs"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="px-1.5 py-0.5 rounded text-xs font-medium"
                        style={{
                          background:
                            log.status === 'ok' ? 'rgba(82,196,26,0.15)' : 'rgba(239,68,68,0.15)',
                          color: log.status === 'ok' ? '#52C41A' : '#EF4444',
                        }}
                      >
                        {log.status}
                      </span>
                      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {log.action}
                      </span>
                    </div>
                    <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                      <span>{log.duration_ms}ms</span>
                      <span>·</span>
                      <span>{formatTime(log.created_at)}</span>
                    </div>
                  </div>
                  <details className="mt-1">
                    <summary
                      className="cursor-pointer"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      请求 / 响应
                    </summary>
                    <div className="mt-1 flex flex-col gap-1">
                      <div>
                        <div style={{ color: 'var(--text-secondary)' }}>请求:</div>
                        <pre
                          className="p-1.5 rounded text-xs overflow-x-auto whitespace-pre-wrap break-words"
                          style={{
                            background: 'var(--bg-primary)',
                            color: 'var(--text-primary)',
                          }}
                        >
                          {prettyJson(log.request)}
                        </pre>
                      </div>
                      <div>
                        <div style={{ color: 'var(--text-secondary)' }}>响应:</div>
                        <pre
                          className="p-1.5 rounded text-xs overflow-x-auto whitespace-pre-wrap break-words"
                          style={{
                            background: 'var(--bg-primary)',
                            color: 'var(--text-primary)',
                          }}
                        >
                          {truncate(log.response, 500)}
                        </pre>
                      </div>
                    </div>
                  </details>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 注册表单浮层 */}
      {formOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center p-4 z-50"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setFormOpen(false)}
        >
          <div
            className="rounded-2xl p-5 w-full max-w-lg flex flex-col gap-3"
            style={{
              background: 'var(--bg-card)',
              boxShadow: 'var(--shadow-xl)',
              border: '1px solid var(--border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
              注册外部 Agent
            </h3>

            {/* 类型选择 */}
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Agent 类型
              </label>
              <div className="flex gap-2 flex-wrap">
                {(['claude_code', 'codex', 'gemini_cli', 'generic'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() =>
                      setForm({
                        ...form,
                        agent_type: t,
                        endpoint:
                          t === 'claude_code'
                            ? 'cli://claude-code'
                            : t === 'codex'
                            ? 'cli://codex'
                            : t === 'gemini_cli'
                            ? 'cli://gemini'
                            : form.endpoint,
                        name:
                          form.name === 'Claude Code' ||
                          form.name === 'Codex CLI' ||
                          form.name === 'Gemini CLI'
                            ? TYPE_LABELS[t]
                            : form.name,
                      })
                    }
                    className="px-3 py-1.5 rounded-lg text-sm flex items-center gap-1"
                    style={{
                      background:
                        form.agent_type === t ? TYPE_COLORS[t] : 'var(--bg-primary)',
                      color: form.agent_type === t ? '#FFFFFF' : 'var(--text-primary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <span>{TYPE_ICONS[t]}</span>
                    <span>{TYPE_LABELS[t]}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                名称
              </label>
              <input
                type="text"
                value={form.name}
                onInput={(e) => setForm({ ...form, name: (e.target as HTMLInputElement).value })}
                className="px-3 py-2 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                端点(可选)
              </label>
              <input
                type="text"
                value={form.endpoint}
                onInput={(e) =>
                  setForm({ ...form, endpoint: (e.target as HTMLInputElement).value })
                }
                placeholder="cli://claude-code"
                className="px-3 py-2 rounded-lg text-sm font-mono"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                能力(逗号分隔)
              </label>
              <input
                type="text"
                value={form.capabilities}
                onInput={(e) =>
                  setForm({ ...form, capabilities: (e.target as HTMLInputElement).value })
                }
                className="px-3 py-2 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                认证 Token(可选,留空则开放模式)
              </label>
              <input
                type="password"
                value={form.auth_token}
                onInput={(e) =>
                  setForm({ ...form, auth_token: (e.target as HTMLInputElement).value })
                }
                className="px-3 py-2 rounded-lg text-sm font-mono"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setFormOpen(false)}
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
                onClick={save}
                disabled={saving}
                className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
                style={{ background: 'var(--accent)' }}
              >
                {saving ? '保存中...' : '注册'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
