// 技能市场组件 (v2.3.0 Phase 3-C)
// 四 tab: 内置 / 社区 / 已安装 / MCP
// - 内置: 列出内置技能 + enabled toggle (乐观更新 + 后端持久化)
// - 社区: 搜索框 + 结果列表 + 一键安装按钮
// - 已安装: 已安装技能列表 + enabled toggle + 卸载/编辑/执行 (保留原有功能)
// - MCP: 市场搜索 + 已连接服务器 + 健康检查/安全审计/断开
// 通过 useGlobalState() 监听 skill.enabled.toggled / mcp.connected / mcp.disconnected 事件
import { useState, useEffect, useMemo } from 'preact/hooks'
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api'
import { useGlobalState } from '../lib/store'
import type { Skill } from '../lib/types'

// 扩展技能类型(后端返回的额外字段)
interface SkillDetail extends Skill {
  source?: string
  path?: string
  tags?: string[]
  content?: string
}

// 社区技能搜索结果
interface CommunitySkill {
  name: string
  description?: string
  source?: string
  url?: string
  install_type?: string
  stars?: number
}

// 社区源
interface CommunitySource {
  id: string
  name: string
  url: string
}

// MCP 服务器 (来自 /mcp/servers)
interface McpServer {
  name: string
  command?: string
  args?: string[]
  connected?: boolean
  server_info?: any
  transport?: string
}

// MCP 市场搜索结果
interface McpMarketServer {
  name: string
  description?: string
  transport?: string
  stars?: number
  url?: string
}

type TabKey = 'builtin' | 'community' | 'installed' | 'mcp'

// 类型标签颜色
const TYPE_COLORS: Record<string, string> = {
  prompt: '#FF8C42',
  python: '#3B82F6',
}

// 类型图标
const TYPE_ICONS: Record<string, string> = {
  prompt: '💬',
  python: '🐍',
}

// 推断技能类型
function inferType(s: SkillDetail): 'prompt' | 'python' {
  const source = (s.source || '').toLowerCase()
  const path = (s.path || '').toLowerCase()
  const skillType = (s.skill_type || '').toLowerCase()
  if (source.includes('python') || path.endsWith('.py') || skillType === 'python') return 'python'
  return 'prompt'
}

// 卡片图标
function skillIcon(s: SkillDetail): string {
  return TYPE_ICONS[inferType(s)] || '⚡'
}

export default function SkillMarketplace() {
  // v2.3.1: 改用 selector 模式订阅, 避免全组件树重渲染
  const skillsMcp = useGlobalState((s) => s.skillsMcp)

  // 当前 tab
  const [tab, setTab] = useState<TabKey>('installed')

  // ===== 已安装 tab: 原有技能列表功能 =====
  const [skills, setSkills] = useState<SkillDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 过滤
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | 'prompt' | 'python'>('all')

  // 展开的技能名 + 执行输入 + 结果
  const [expanded, setExpanded] = useState<string | null>(null)
  const [execInput, setExecInput] = useState('')
  const [execResult, setExecResult] = useState<string | null>(null)
  const [executing, setExecuting] = useState(false)

  // 启用状态本地镜像(乐观更新) — 用于已安装 + 内置 tab
  const [enabledMap, setEnabledMap] = useState<Record<string, boolean>>({})

  // 新建/编辑表单
  const [formOpen, setFormOpen] = useState(false)
  const [editingName, setEditingName] = useState<string | null>(null)
  const [form, setForm] = useState<{ name: string; description: string; type: 'prompt' | 'python'; content: string; tags: string }>({
    name: '',
    description: '',
    type: 'prompt',
    content: '',
    tags: '',
  })
  const [saving, setSaving] = useState(false)

  // ===== 内置 tab =====
  const [builtinSkills, setBuiltinSkills] = useState<SkillDetail[]>([])
  const [builtinLoading, setBuiltinLoading] = useState(false)

  // ===== 社区 tab =====
  const [communityQuery, setCommunityQuery] = useState('')
  const [communityResults, setCommunityResults] = useState<CommunitySkill[]>([])
  const [communitySearching, setCommunitySearching] = useState(false)
  const [communitySources, setCommunitySources] = useState<CommunitySource[]>([])
  const [installingName, setInstallingName] = useState<string | null>(null)
  const [installMsg, setInstallMsg] = useState<string | null>(null)

  // ===== MCP tab =====
  const [mcpServers, setMcpServers] = useState<McpServer[]>([])
  const [mcpLoading, setMcpLoading] = useState(false)
  const [mcpMarketQuery, setMcpMarketQuery] = useState('')
  const [mcpMarketResults, setMcpMarketResults] = useState<McpMarketServer[]>([])
  const [mcpMarketSearching, setMcpMarketSearching] = useState(false)
  // 连接表单
  const [connectForm, setConnectForm] = useState<{
    name: string
    command: string
    args: string
    transport: 'stdio' | 'sse'
  }>({ name: '', command: '', args: '', transport: 'stdio' })
  const [connecting, setConnecting] = useState(false)
  // 健康检查 / 安全审计结果 (按 server name 索引)
  const [healthMap, setHealthMap] = useState<Record<string, any>>({})
  const [auditMap, setAuditMap] = useState<Record<string, any>>({})

  // 加载已安装技能列表
  async function loadSkills() {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<SkillDetail[] | { items?: SkillDetail[] }>('/skills')
      const list = Array.isArray(data) ? data : data?.items || []
      setSkills(list)
      const emap: Record<string, boolean> = {}
      list.forEach((s) => {
        emap[s.name] = s.enabled !== false
      })
      setEnabledMap(emap)
    } catch (e: any) {
      setError(e?.message || '加载技能失败')
    } finally {
      setLoading(false)
    }
  }

  // 加载内置技能
  async function loadBuiltin() {
    setBuiltinLoading(true)
    try {
      const data = await apiGet<{ count: number; skills: SkillDetail[] }>(
        '/skill-market/builtin',
      )
      const list = data?.skills || []
      setBuiltinSkills(list)
      // 合并到 enabledMap
      setEnabledMap((prev) => {
        const next = { ...prev }
        list.forEach((s) => {
          if (!(s.name in next)) next[s.name] = s.enabled !== false
        })
        return next
      })
    } catch (e: any) {
      // 静默, 内置 tab 不阻塞
      setBuiltinSkills([])
    } finally {
      setBuiltinLoading(false)
    }
  }

  // 加载社区源
  async function loadSources() {
    try {
      const data = await apiGet<{ count: number; sources: CommunitySource[] }>(
        '/skill-market/sources',
      )
      setCommunitySources(data?.sources || [])
    } catch {
      // 静默
    }
  }

  // 加载 MCP 服务器
  async function loadMcpServers() {
    setMcpLoading(true)
    try {
      const data = await apiGet<McpServer[]>('/mcp/servers')
      setMcpServers(Array.isArray(data) ? data : [])
    } catch {
      setMcpServers([])
    } finally {
      setMcpLoading(false)
    }
  }

  useEffect(() => {
    loadSkills()
    loadSources()
  }, [])

  // tab 切换时按需加载
  useEffect(() => {
    if (tab === 'builtin' && builtinSkills.length === 0) {
      loadBuiltin()
    }
    if (tab === 'mcp') {
      loadMcpServers()
    }
  }, [tab])

  // 监听全局 skillsMcp state (SSE 事件驱动) — 同步 enabledMap + mcpServers
  // 当其他客户端/进程触发 skill.enabled.toggled / mcp.connected / mcp.disconnected 时,
  // store 的 reducer 已更新 skillsMcp, 这里同步到本地镜像。
  useEffect(() => {
    const gSkills = skillsMcp.skills || {}
    setEnabledMap((prev) => {
      const next = { ...prev }
      let changed = false
      Object.keys(gSkills).forEach((k) => {
        if (gSkills[k]?.enabled !== undefined && next[k] !== gSkills[k].enabled) {
          next[k] = gSkills[k].enabled
          changed = true
        }
      })
      return changed ? next : prev
    })
    // MCP 服务器变化时刷新列表
    if (tab === 'mcp') {
      loadMcpServers()
    }
  }, [skillsMcp])

  // 过滤后的技能 (已安装 tab)
  const filtered = useMemo(() => {
    return skills.filter((s) => {
      if (typeFilter !== 'all' && inferType(s) !== typeFilter) return false
      if (search) {
        const q = search.toLowerCase()
        if (
          !(s.name || '').toLowerCase().includes(q) &&
          !(s.description || '').toLowerCase().includes(q)
        )
          return false
      }
      return true
    })
  }, [skills, search, typeFilter])

  // 切换启用状态 (已安装 tab — 走 PUT /skills/{name})
  async function toggleEnabled(s: SkillDetail) {
    const next = !enabledMap[s.name]
    setEnabledMap((m) => ({ ...m, [s.name]: next }))
    try {
      await apiPut(`/skills/${s.name}`, { enabled: next })
    } catch {
      // 回滚
      setEnabledMap((m) => ({ ...m, [s.name]: !next }))
    }
  }

  // 切换内置技能启用状态 (内置 tab — 走 PUT /skill-market/builtin/{name}/toggle)
  async function toggleBuiltinEnabled(s: SkillDetail) {
    const next = !enabledMap[s.name]
    setEnabledMap((m) => ({ ...m, [s.name]: next }))
    try {
      await apiPut(`/skill-market/builtin/${s.name}/toggle`, { enabled: next })
    } catch {
      // 回滚
      setEnabledMap((m) => ({ ...m, [s.name]: !next }))
    }
  }

  // 展开并加载详情
  async function expandSkill(s: SkillDetail) {
    if (expanded === s.name) {
      setExpanded(null)
      return
    }
    setExpanded(s.name)
    setExecInput('')
    setExecResult(null)
    try {
      const detail = await apiGet<SkillDetail>(`/skills/${s.name}`)
      if (detail) {
        setSkills((prev) =>
          prev.map((x) =>
            x.name === s.name ? { ...x, ...detail, content: detail.content } : x,
          ),
        )
      }
    } catch {
      // 详情加载失败时静默
    }
  }

  // 执行技能
  async function executeSkill(s: SkillDetail) {
    setExecuting(true)
    setExecResult(null)
    try {
      const result = await apiPost<{ prompt?: string; output?: string; rendered?: string }>(
        `/skills/${s.name}/execute`,
        { input: execInput },
      )
      const text =
        result?.prompt || result?.rendered || result?.output || JSON.stringify(result, null, 2)
      setExecResult(text)
    } catch (e: any) {
      setExecResult(`❌ 执行失败: ${e?.message || '未知错误'}`)
    } finally {
      setExecuting(false)
    }
  }

  // 打开新建表单
  function openCreate() {
    setForm({ name: '', description: '', type: 'prompt', content: '', tags: '' })
    setEditingName(null)
    setFormOpen(true)
  }

  // 打开编辑表单
  async function openEdit(s: SkillDetail) {
    setEditingName(s.name)
    let content = s.content || ''
    try {
      const detail = await apiGet<SkillDetail>(`/skills/${s.name}`)
      content = detail?.content || content
    } catch {
      // 忽略
    }
    setForm({
      name: s.name,
      description: s.description || '',
      type: inferType(s),
      content,
      tags: (s.tags || []).join(', '),
    })
    setFormOpen(true)
  }

  // 保存技能
  async function save() {
    if (!form.name.trim()) {
      alert('请输入技能名称')
      return
    }
    setSaving(true)
    try {
      const tags = form.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      if (editingName) {
        await apiPut(`/skills/${editingName}`, {
          description: form.description,
          prompt_template: form.content,
          tags,
        })
      } else {
        await apiPost('/skills', {
          name: form.name,
          description: form.description,
          prompt_template: form.content,
          tags,
        })
      }
      setFormOpen(false)
      await loadSkills()
    } catch (e: any) {
      alert(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 删除技能
  async function removeSkill(s: SkillDetail) {
    if (!confirm(`确定删除技能「${s.name}」吗?`)) return
    try {
      await apiDelete(`/skills/${s.name}`)
      if (expanded === s.name) setExpanded(null)
      await loadSkills()
    } catch (e: any) {
      alert(e?.message || '删除失败')
    }
  }

  // 社区搜索
  async function searchCommunity() {
    setCommunitySearching(true)
    setInstallMsg(null)
    try {
      const data = await apiGet<{ count: number; skills: CommunitySkill[] }>(
        `/skill-market/community/search?q=${encodeURIComponent(communityQuery)}`,
      )
      setCommunityResults(data?.skills || [])
    } catch (e: any) {
      setCommunityResults([])
      setInstallMsg(`❌ 搜索失败: ${e?.message || '未知错误'}`)
    } finally {
      setCommunitySearching(false)
    }
  }

  // 安装社区技能
  async function installCommunitySkill(s: CommunitySkill) {
    if (!s.url) {
      setInstallMsg('❌ 该技能没有可安装的 URL')
      return
    }
    setInstallingName(s.name)
    setInstallMsg(null)
    try {
      const result = await apiPost<{ success: boolean; path?: string; error?: string }>(
        '/skill-market/community/install',
        { skill_url: s.url, install_type: s.install_type || 'git', name: s.name },
      )
      if (result?.success) {
        setInstallMsg(`✅ 安装成功: ${s.name}${result.path ? ` → ${result.path}` : ''}`)
        await loadSkills()
      } else {
        setInstallMsg(`⚠️ ${result?.error || '安装未完成 (社区功能为占位实现)'}`)
      }
    } catch (e: any) {
      setInstallMsg(`❌ 安装失败: ${e?.message || '未知错误'}`)
    } finally {
      setInstallingName(null)
    }
  }

  // ===== MCP 操作 =====

  // 搜索 MCP 市场
  async function searchMcpMarket() {
    setMcpMarketSearching(true)
    try {
      const data = await apiGet<{ count: number; servers: McpMarketServer[] }>(
        `/mcp/marketplace/search?q=${encodeURIComponent(mcpMarketQuery)}`,
      )
      setMcpMarketResults(data?.servers || [])
    } catch {
      setMcpMarketResults([])
    } finally {
      setMcpMarketSearching(false)
    }
  }

  // 连接 MCP 服务器
  async function connectMcp() {
    if (!connectForm.name.trim() || !connectForm.command.trim()) {
      alert('请填写服务器名称和命令')
      return
    }
    setConnecting(true)
    try {
      const args = connectForm.args
        .split(' ')
        .map((a) => a.trim())
        .filter(Boolean)
      await apiPost('/mcp/servers', {
        name: connectForm.name,
        command: connectForm.command,
        args,
        transport: connectForm.transport,
      })
      setConnectForm({ name: '', command: '', args: '', transport: 'stdio' })
      await loadMcpServers()
    } catch (e: any) {
      alert(e?.message || '连接失败')
    } finally {
      setConnecting(false)
    }
  }

  // 断开 MCP 服务器
  async function disconnectMcp(name: string) {
    if (!confirm(`确定断开 MCP 服务器「${name}」吗?`)) return
    try {
      await apiDelete(`/mcp/servers/${name}`)
      await loadMcpServers()
    } catch (e: any) {
      alert(e?.message || '断开失败')
    }
  }

  // 健康检查
  async function checkHealth(name: string) {
    try {
      const data = await apiGet<{ healthy: boolean; server_id: string }>(
        `/mcp/servers/${name}/health`,
      )
      setHealthMap((m) => ({ ...m, [name]: data }))
    } catch (e: any) {
      setHealthMap((m) => ({ ...m, [name]: { healthy: false, error: e?.message } }))
    }
  }

  // 安全审计
  async function runAudit(name: string) {
    try {
      const data = await apiGet<{ safe: boolean; warnings: string[] }>(
        `/mcp/servers/${name}/security-audit`,
      )
      setAuditMap((m) => ({ ...m, [name]: data }))
    } catch (e: any) {
      setAuditMap((m) => ({ ...m, [name]: { safe: false, warnings: [e?.message] } }))
    }
  }

  // 技能卡片渲染 (复用于 内置 + 已安装 tab)
  function renderSkillCard(
    s: SkillDetail,
    opts: {
      onToggle: (s: SkillDetail) => void
      onEdit?: (s: SkillDetail) => void
      onRemove?: (s: SkillDetail) => void
      showExecute?: boolean
    },
  ) {
    const type = inferType(s)
    const isExpanded = expanded === s.name
    return (
      <div
        key={s.name}
        className="rounded-xl p-4 flex flex-col gap-2"
        style={{
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        {/* 卡片头部 */}
        <div
          className="flex items-start justify-between gap-2 cursor-pointer"
          onClick={() => opts.showExecute && expandSkill(s)}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div
              className="flex items-center justify-center w-10 h-10 rounded-lg text-xl flex-shrink-0"
              style={{ background: 'var(--bg-secondary)' }}
            >
              {skillIcon(s)}
            </div>
            <div className="min-w-0 flex-1">
              <div
                className="font-semibold text-sm truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {s.name}
              </div>
              <div
                className="text-xs truncate"
                style={{ color: 'var(--text-secondary)' }}
              >
                {s.description || '暂无描述'}
              </div>
            </div>
          </div>
          <span
            className="px-2 py-0.5 rounded-full text-xs font-medium text-white flex-shrink-0"
            style={{ background: TYPE_COLORS[type] }}
          >
            {type === 'prompt' ? '提示词' : 'Python'}
          </span>
        </div>

        {/* 标签 */}
        {(s.tags || []).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {(s.tags ?? []).slice(0, 4).map((t) => (
              <span
                key={t}
                className="px-1.5 py-0.5 rounded text-xs"
                style={{
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)',
                }}
              >
                #{t}
              </span>
            ))}
          </div>
        )}

        {/* 卡片底部操作 */}
        <div className="flex items-center justify-between gap-2 mt-1">
          <button
            onClick={() => opts.onToggle(s)}
            className="flex items-center gap-1.5 text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span
              className="inline-block w-9 h-5 rounded-full relative transition"
              style={{
                background: enabledMap[s.name] ? 'var(--accent)' : '#D1D5DB',
              }}
            >
              <span
                className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
                style={{ left: enabledMap[s.name] ? '18px' : '2px' }}
              />
            </span>
            <span>{enabledMap[s.name] ? '已启用' : '已禁用'}</span>
          </button>
          <div className="flex gap-1">
            {opts.onEdit && (
              <button
                onClick={() => opts.onEdit!(s)}
                className="px-2 py-1 rounded-md text-xs"
                style={{
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-primary)',
                }}
              >
                编辑
              </button>
            )}
            {opts.onRemove && (
              <button
                onClick={() => opts.onRemove!(s)}
                className="px-2 py-1 rounded-md text-xs text-white"
                style={{ background: '#EF4444' }}
              >
                删除
              </button>
            )}
          </div>
        </div>

        {/* 展开详情: 执行区 (仅已安装 tab) */}
        {isExpanded && opts.showExecute && (
          <div
            className="mt-2 p-3 rounded-lg flex flex-col gap-2"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
            }}
          >
            <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              ▶ 执行技能
            </div>
            <textarea
              placeholder="输入变量/输入内容..."
              value={execInput}
              onInput={(e) =>
                setExecInput((e.target as HTMLTextAreaElement).value)
              }
              rows={3}
              className="px-2 py-1.5 rounded-md text-sm font-mono w-full"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            />
            <button
              onClick={() => executeSkill(s)}
              disabled={executing}
              className="px-3 py-1 rounded-md text-sm font-medium text-white self-start"
              style={{ background: 'var(--accent)' }}
            >
              {executing ? '执行中...' : '执行'}
            </button>
            {execResult != null && (
              <div>
                <div
                  className="text-xs mb-1"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  执行结果:
                </div>
                <pre
                  className="p-2 rounded-md text-xs overflow-x-auto whitespace-pre-wrap break-words"
                  style={{
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                    maxHeight: 200,
                  }}
                >
                  {execResult}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    )
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
      {/* 顶部 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          ⚡ 技能市场
        </h2>
        <button
          onClick={openCreate}
          className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          + 新建技能
        </button>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--bg-primary)' }}>
        {([
          ['installed', '已安装'],
          ['builtin', '内置'],
          ['community', '社区'],
          ['mcp', 'MCP'],
        ] as [TabKey, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className="px-3 py-1 rounded-md text-sm transition flex-1"
            style={{
              background: tab === key ? 'var(--accent)' : 'transparent',
              color: tab === key ? '#FFFFFF' : 'var(--text-secondary)',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ===== 已安装 tab ===== */}
      {tab === 'installed' && (
        <>
          {/* 搜索 + 类型过滤 */}
          <div className="flex gap-2 flex-wrap">
            <input
              type="text"
              placeholder="🔍 搜索技能名称或描述..."
              value={search}
              onInput={(e) => setSearch((e.target as HTMLInputElement).value)}
              className="px-3 py-1.5 rounded-lg text-sm flex-1 min-w-[200px]"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            />
            <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--bg-primary)' }}>
              {(['all', 'prompt', 'python'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className="px-3 py-1 rounded-md text-sm transition"
                  style={{
                    background: typeFilter === t ? 'var(--accent)' : 'transparent',
                    color: typeFilter === t ? '#FFFFFF' : 'var(--text-secondary)',
                  }}
                >
                  {t === 'all' ? '全部' : t === 'prompt' ? '提示词' : 'Python'}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="text-center py-10" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : error ? (
            <div className="text-center py-10" style={{ color: '#EF4444' }}>
              {error}
            </div>
          ) : filtered.length === 0 ? (
            <div
              className="flex flex-col items-center gap-2 py-10"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">🪄</div>
              <div>暂无技能</div>
              <div className="text-xs">点击「新建技能」创建你的第一个技能</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filtered.map((s) =>
                renderSkillCard(s, {
                  onToggle: toggleEnabled,
                  onEdit: openEdit,
                  onRemove: removeSkill,
                  showExecute: true,
                }),
              )}
            </div>
          )}
        </>
      )}

      {/* ===== 内置 tab ===== */}
      {tab === 'builtin' && (
        <>
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            内置技能来自 <code>server/skills/*.md</code>,启用状态持久化到数据库并发布{' '}
            <code>skill.enabled.toggled</code> 事件。
          </div>
          {builtinLoading ? (
            <div className="text-center py-10" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : builtinSkills.length === 0 ? (
            <div
              className="flex flex-col items-center gap-2 py-10"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">📦</div>
              <div>暂无内置技能</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {builtinSkills.map((s) =>
                renderSkillCard(s, {
                  onToggle: toggleBuiltinEnabled,
                  showExecute: false,
                }),
              )}
            </div>
          )}
        </>
      )}

      {/* ===== 社区 tab ===== */}
      {tab === 'community' && (
        <>
          {/* 社区源 chips */}
          {communitySources.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {communitySources.map((src) => (
                <span
                  key={src.id}
                  className="px-2 py-0.5 rounded-full text-xs"
                  style={{
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-secondary)',
                  }}
                  title={src.url}
                >
                  {src.name}
                </span>
              ))}
            </div>
          )}
          {/* 搜索框 */}
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="🔍 搜索社区技能 (agentskills.io / Claude marketplace / Smithery)..."
              value={communityQuery}
              onInput={(e) => setCommunityQuery((e.target as HTMLInputElement).value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') searchCommunity()
              }}
              className="px-3 py-1.5 rounded-lg text-sm flex-1"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            />
            <button
              onClick={searchCommunity}
              disabled={communitySearching}
              className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
              style={{ background: 'var(--accent)' }}
            >
              {communitySearching ? '搜索中...' : '搜索'}
            </button>
          </div>

          {installMsg && (
            <div
              className="text-xs px-3 py-2 rounded-md"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            >
              {installMsg}
            </div>
          )}

          {/* 搜索结果 */}
          {communityResults.length === 0 ? (
            <div
              className="flex flex-col items-center gap-2 py-10"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">🌐</div>
              <div>输入关键词搜索社区技能</div>
              <div className="text-xs">社区注册表当前为占位实现 (返回空结果)</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {communityResults.map((s) => (
                <div
                  key={s.name}
                  className="rounded-xl p-4 flex flex-col gap-2"
                  style={{
                    background: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="flex items-center justify-center w-10 h-10 rounded-lg text-xl flex-shrink-0"
                      style={{ background: 'var(--bg-secondary)' }}
                    >
                      🌐
                    </div>
                    <div className="min-w-0 flex-1">
                      <div
                        className="font-semibold text-sm truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {s.name}
                      </div>
                      <div
                        className="text-xs truncate"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {s.description || '暂无描述'}
                      </div>
                    </div>
                    {s.source && (
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium text-white flex-shrink-0"
                        style={{ background: '#8B5CF6' }}
                      >
                        {s.source}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1">
                    <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {s.install_type || 'git'}
                      {s.stars != null && ` · ⭐ ${s.stars}`}
                    </span>
                    <button
                      onClick={() => installCommunitySkill(s)}
                      disabled={installingName === s.name}
                      className="px-3 py-1 rounded-md text-xs font-medium text-white"
                      style={{ background: 'var(--accent)' }}
                    >
                      {installingName === s.name ? '安装中...' : '一键安装'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ===== MCP tab ===== */}
      {tab === 'mcp' && (
        <>
          {/* MCP 市场搜索 */}
          <div
            className="rounded-xl p-4 flex flex-col gap-2"
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              🔌 MCP 市场 (Smithery 索引)
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="🔍 搜索 MCP 服务器..."
                value={mcpMarketQuery}
                onInput={(e) => setMcpMarketQuery((e.target as HTMLInputElement).value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') searchMcpMarket()
                }}
                className="px-3 py-1.5 rounded-lg text-sm flex-1"
                style={{
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
              <button
                onClick={searchMcpMarket}
                disabled={mcpMarketSearching}
                className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
                style={{ background: 'var(--accent)' }}
              >
                {mcpMarketSearching ? '搜索中...' : '搜索'}
              </button>
            </div>
            {mcpMarketResults.length > 0 && (
              <div className="flex flex-col gap-1 mt-1">
                {mcpMarketResults.map((srv) => (
                  <div
                    key={srv.name}
                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm"
                    style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
                  >
                    <div className="min-w-0 flex-1">
                      <span style={{ color: 'var(--text-primary)' }}>{srv.name}</span>
                      <span
                        className="ml-2 text-xs"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {srv.description || ''}
                      </span>
                    </div>
                    <span
                      className="px-2 py-0.5 rounded-full text-xs flex-shrink-0"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {srv.transport || 'stdio'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 连接新 MCP 服务器 */}
          <div
            className="rounded-xl p-4 flex flex-col gap-2"
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              ➕ 连接 MCP 服务器
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="服务器名称"
                value={connectForm.name}
                onInput={(e) =>
                  setConnectForm({ ...connectForm, name: (e.target as HTMLInputElement).value })
                }
                className="px-3 py-1.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
              <input
                type="text"
                placeholder="命令 (如 npx -y @modelcontextprotocol/server-filesystem)"
                value={connectForm.command}
                onInput={(e) =>
                  setConnectForm({ ...connectForm, command: (e.target as HTMLInputElement).value })
                }
                className="px-3 py-1.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
              <input
                type="text"
                placeholder="参数 (空格分隔)"
                value={connectForm.args}
                onInput={(e) =>
                  setConnectForm({ ...connectForm, args: (e.target as HTMLInputElement).value })
                }
                className="px-3 py-1.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
              <select
                value={connectForm.transport}
                onChange={(e) =>
                  setConnectForm({
                    ...connectForm,
                    transport: (e.target as HTMLSelectElement).value as 'stdio' | 'sse',
                  })
                }
                className="px-3 py-1.5 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <option value="stdio">stdio (子进程)</option>
                <option value="sse">sse (HTTP+SSE, 占位)</option>
              </select>
            </div>
            <button
              onClick={connectMcp}
              disabled={connecting}
              className="px-4 py-1.5 rounded-lg text-sm font-medium text-white self-start"
              style={{ background: 'var(--accent)' }}
            >
              {connecting ? '连接中...' : '连接'}
            </button>
          </div>

          {/* 已连接 MCP 服务器 */}
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            🔗 已连接服务器
            {/* SSE 实时状态徽章 */}
            {Object.keys(skillsMcp.mcpServers || {}).length > 0 && (
              <span
                className="ml-2 px-2 py-0.5 rounded-full text-xs"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
              >
                SSE: {Object.keys(skillsMcp.mcpServers).length}
              </span>
            )}
          </div>
          {mcpLoading ? (
            <div className="text-center py-6" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : mcpServers.length === 0 ? (
            <div
              className="flex flex-col items-center gap-2 py-6"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-4xl">🔌</div>
              <div>暂无已连接的 MCP 服务器</div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {mcpServers.map((srv) => {
                const health = healthMap[srv.name]
                const audit = auditMap[srv.name]
                return (
                  <div
                    key={srv.name}
                    className="rounded-xl p-3 flex flex-col gap-2"
                    style={{
                      background: 'var(--bg-primary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <span
                          className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            background: srv.connected ? '#10B981' : '#EF4444',
                          }}
                        />
                        <span
                          className="font-semibold text-sm truncate"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {srv.name}
                        </span>
                        <span
                          className="px-2 py-0.5 rounded-full text-xs flex-shrink-0"
                          style={{
                            background: 'var(--bg-secondary)',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {srv.transport || 'stdio'}
                        </span>
                      </div>
                      <button
                        onClick={() => disconnectMcp(srv.name)}
                        className="px-2 py-1 rounded-md text-xs text-white flex-shrink-0"
                        style={{ background: '#EF4444' }}
                      >
                        断开
                      </button>
                    </div>
                    <div className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
                      {(srv.args || []).length > 0
                        ? `${srv.command} ${srv.args!.join(' ')}`
                        : srv.command || ''}
                    </div>
                    {/* 操作按钮 */}
                    <div className="flex gap-1 flex-wrap">
                      <button
                        onClick={() => checkHealth(srv.name)}
                        className="px-2 py-1 rounded-md text-xs"
                        style={{
                          background: 'var(--bg-secondary)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        健康检查
                      </button>
                      <button
                        onClick={() => runAudit(srv.name)}
                        className="px-2 py-1 rounded-md text-xs"
                        style={{
                          background: 'var(--bg-secondary)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        安全审计
                      </button>
                    </div>
                    {/* 健康检查结果 */}
                    {health && (
                      <div
                        className="text-xs px-2 py-1 rounded-md"
                        style={{
                          background: 'var(--bg-card)',
                          color: health.healthy ? '#10B981' : '#EF4444',
                          border: '1px solid var(--border)',
                        }}
                      >
                        {health.healthy ? '✅ 健康' : '❌ 异常'}
                        {health.error ? ` — ${health.error}` : ''}
                      </div>
                    )}
                    {/* 安全审计结果 */}
                    {audit && (
                      <div
                        className="text-xs px-2 py-1 rounded-md"
                        style={{
                          background: 'var(--bg-card)',
                          color: audit.safe ? '#10B981' : '#F59E0B',
                          border: '1px solid var(--border)',
                        }}
                      >
                        {audit.safe ? '✅ 安全' : '⚠️ 存在风险'}
                        {audit.warnings && audit.warnings.length > 0
                          ? ` — ${audit.warnings.join('; ')}`
                          : audit.safe
                            ? ''
                            : ' — 无详细警告'}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* 新建/编辑表单浮层 */}
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
              {editingName ? '编辑技能' : '新建技能'}
            </h3>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                名称
              </label>
              <input
                type="text"
                value={form.name}
                disabled={!!editingName}
                onInput={(e) => setForm({ ...form, name: (e.target as HTMLInputElement).value })}
                className="px-3 py-2 rounded-lg text-sm disabled:opacity-50"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                描述
              </label>
              <input
                type="text"
                value={form.description}
                onInput={(e) =>
                  setForm({ ...form, description: (e.target as HTMLInputElement).value })
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
                类型
              </label>
              <select
                value={form.type}
                onChange={(e) =>
                  setForm({ ...form, type: (e.target as HTMLSelectElement).value as 'prompt' | 'python' })
                }
                className="px-3 py-2 rounded-lg text-sm"
                style={{
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <option value="prompt">提示词(prompt)</option>
                <option value="python">Python 脚本</option>
              </select>
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
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                内容(提示词模板或 Python 代码)
              </label>
              <textarea
                value={form.content}
                onInput={(e) => setForm({ ...form, content: (e.target as HTMLTextAreaElement).value })}
                rows={8}
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
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
