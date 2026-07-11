// 技能市场组件
// 技能卡片网格 + 详情展开 + 执行 + 新建/编辑/删除
import { useState, useEffect, useMemo } from 'preact/hooks'
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api'
import type { Skill } from '../lib/types'

// 扩展技能类型(后端返回的额外字段)
interface SkillDetail extends Skill {
  source?: string
  path?: string
  tags?: string[]
  content?: string
}

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

  // 启用状态本地镜像(乐观更新)
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

  // 加载技能列表
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

  useEffect(() => {
    loadSkills()
  }, [])

  // 过滤后的技能
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

  // 切换启用状态
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

  // 展开并加载详情
  async function expandSkill(s: SkillDetail) {
    if (expanded === s.name) {
      setExpanded(null)
      return
    }
    setExpanded(s.name)
    setExecInput('')
    setExecResult(null)
    // 加载详情以获取 content
    try {
      const detail = await apiGet<SkillDetail>(`/skills/${s.name}`)
      if (detail) {
        // 更新对应技能的 content
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
    // 先尝试获取 content
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

      {/* 主体: 卡片网格 */}
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
          {filtered.map((s) => {
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
                  onClick={() => expandSkill(s)}
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
                    onClick={() => toggleEnabled(s)}
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
                    <button
                      onClick={() => openEdit(s)}
                      className="px-2 py-1 rounded-md text-xs"
                      style={{
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      编辑
                    </button>
                    <button
                      onClick={() => removeSkill(s)}
                      className="px-2 py-1 rounded-md text-xs text-white"
                      style={{ background: '#EF4444' }}
                    >
                      删除
                    </button>
                  </div>
                </div>

                {/* 展开详情: 执行区 */}
                {isExpanded && (
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
          })}
        </div>
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
