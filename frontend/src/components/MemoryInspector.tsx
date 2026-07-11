// 记忆浏览器组件
// 左栏: 记忆列表(按层级分组) + 右栏: 记忆详情(含反向链接)
import { useState, useEffect, useMemo } from 'preact/hooks'
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api'
import type { Memory } from '../lib/types'

// 扩展记忆类型(后端返回的额外字段)
interface MemoryDetail extends Memory {
  html_content?: string
  importance?: number
  updated_at?: string
}

// 层级标签
const LAYER_ORDER = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5']
const LAYER_LABELS: Record<string, string> = {
  L0: 'L0 感官',
  L1: 'L1 事件',
  L2: 'L2 情感',
  L3: 'L3 概念',
  L4: 'L4 程序',
  L5: 'L5 自我',
}
const LAYER_COLORS: Record<string, string> = {
  L0: '#9CA3AF',
  L1: '#FF8C42',
  L2: '#FF6B8A',
  L3: '#52C41A',
  L4: '#3B82F6',
  L5: '#8B5CF6',
}

// 极简 Markdown 渲染(支持标题/加粗/斜体/代码/链接/列表)
function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 代码块
  html = html.replace(/```([\s\S]*?)```/g, (_m, c) => `<pre class="md-pre">${c}</pre>`)
  // 标题
  html = html.replace(/^######\s+(.*)$/gm, '<h6>$1</h6>')
  html = html.replace(/^#####\s+(.*)$/gm, '<h5>$1</h5>')
  html = html.replace(/^####\s+(.*)$/gm, '<h4>$1</h4>')
  html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>')
  html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>')
  html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>')
  // 加粗 / 斜体 / 行内代码 / 链接
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
  // 无序列表
  html = html.replace(/^[\-\*]\s+(.*)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
  // 段落(连续空行分段)
  html = html
    .split(/\n{2,}/)
    .map((b) => (b.startsWith('<') ? b : `<p>${b.replace(/\n/g, '<br/>')}</p>`))
    .join('')
  return html
}

export default function MemoryInspector() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 过滤
  const [search, setSearch] = useState('')
  const [layerFilter, setLayerFilter] = useState<string>('all')

  // 当前选中
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<MemoryDetail | null>(null)
  const [backlinks, setBacklinks] = useState<Memory[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  // 新建/编辑表单
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<{ layer: string; title: string; content: string; tags: string }>({
    layer: 'L1',
    title: '',
    content: '',
    tags: '',
  })
  const [saving, setSaving] = useState(false)

  // 折叠状态(每个层级)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  // 加载列表
  async function loadList() {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<Memory[] | { items?: Memory[]; data?: Memory[] }>('/memory')
      const list = Array.isArray(data) ? data : data?.items || data?.data || []
      setMemories(list)
      if (list.length > 0 && selectedId == null) {
        setSelectedId(list[0].id)
      }
    } catch (e: any) {
      setError(e?.message || '加载记忆失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadList()
  }, [])

  // 加载详情 + 反向链接
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      setBacklinks([])
      return
    }
    let cancelled = false
    setDetailLoading(true)
    Promise.all([
      apiGet<MemoryDetail>(`/memory/${selectedId}`).catch(() => null),
      apiGet<Memory[] | { items?: Memory[] }>(`/memory/${selectedId}/backlinks`).catch(() => []),
    ])
      .then(([d, bl]) => {
        if (cancelled) return
        setDetail(d)
        setBacklinks(Array.isArray(bl) ? bl : bl?.items || [])
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // 过滤后的列表
  const filtered = useMemo(() => {
    return memories.filter((m) => {
      if (layerFilter !== 'all' && m.layer !== layerFilter) return false
      if (search) {
        const q = search.toLowerCase()
        if (
          !(m.title || '').toLowerCase().includes(q) &&
          !(m.tags || []).some((t) => t.toLowerCase().includes(q))
        )
          return false
      }
      return true
    })
  }, [memories, search, layerFilter])

  // 按层级分组
  const grouped = useMemo(() => {
    const g: Record<string, Memory[]> = {}
    LAYER_ORDER.forEach((l) => (g[l] = []))
    filtered.forEach((m) => {
      const key = m.layer || 'L0'
      if (!g[key]) g[key] = []
      g[key].push(m)
    })
    return g
  }, [filtered])

  // 打开新建表单
  function openCreate() {
    setForm({ layer: 'L1', title: '', content: '', tags: '' })
    setCreating(true)
    setEditing(false)
  }

  // 打开编辑表单
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

  // 保存(新建或编辑)
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
      if (editing && selectedId != null) {
        await apiPut(`/memory/${selectedId}`, {
          layer: form.layer,
          title: form.title,
          html_content: form.content,
          tags,
        })
      } else {
        const created = await apiPost<MemoryDetail>('/memory', {
          layer: form.layer,
          title: form.title,
          content: form.content,
          html_content: form.content,
          tags,
        })
        if (created?.id != null) setSelectedId(created.id)
      }
      setEditing(false)
      setCreating(false)
      await loadList()
    } catch (e: any) {
      alert(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 删除
  async function remove() {
    if (selectedId == null) return
    if (!confirm('确定删除这条记忆吗?')) return
    try {
      await apiDelete(`/memory/${selectedId}`)
      setSelectedId(null)
      setDetail(null)
      await loadList()
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
          📚 记忆浏览器
        </h2>
        <button
          onClick={openCreate}
          className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          + 新建记忆
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[320px_1fr] gap-4" style={{ minHeight: 480 }}>
        {/* 左栏: 列表 */}
        <div
          className="flex flex-col gap-2 p-3 rounded-xl overflow-hidden"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="🔍 搜索标题/标签"
              value={search}
              onInput={(e) => setSearch((e.target as HTMLInputElement).value)}
              className="px-2 py-1.5 rounded-lg text-sm flex-1"
              style={{
                background: 'var(--bg-card)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            />
            <select
              value={layerFilter}
              onChange={(e) => setLayerFilter((e.target as HTMLSelectElement).value)}
              className="px-2 py-1.5 rounded-lg text-sm"
              style={{
                background: 'var(--bg-card)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            >
              <option value="all">全部</option>
              {LAYER_ORDER.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto" style={{ maxHeight: 520 }}>
            {loading ? (
              <div className="text-center py-6 text-sm" style={{ color: 'var(--text-secondary)' }}>
                加载中...
              </div>
            ) : error ? (
              <div className="text-center py-6 text-sm" style={{ color: '#EF4444' }}>
                {error}
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-6 text-sm" style={{ color: 'var(--text-secondary)' }}>
                暂无记忆
              </div>
            ) : (
              LAYER_ORDER.filter((l) => (grouped[l] || []).length > 0).map((layer) => (
                <div key={layer} className="mb-2">
                  <button
                    onClick={() => setCollapsed((c) => ({ ...c, [layer]: !c[layer] }))}
                    className="flex items-center gap-1.5 w-full px-2 py-1 text-xs font-semibold"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    <span>{collapsed[layer] ? '▶' : '▼'}</span>
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full"
                      style={{ background: LAYER_COLORS[layer] }}
                    />
                    <span>
                      {LAYER_LABELS[layer]} ({grouped[layer].length})
                    </span>
                  </button>
                  {!collapsed[layer] && (
                    <div className="flex flex-col gap-1 mt-1">
                      {grouped[layer].map((m) => (
                        <button
                          key={m.id}
                          onClick={() => setSelectedId(m.id)}
                          className="text-left px-2.5 py-2 rounded-lg transition"
                          style={{
                            background:
                              selectedId === m.id ? 'var(--bg-secondary)' : 'transparent',
                            border:
                              selectedId === m.id
                                ? '1px solid var(--accent)'
                                : '1px solid transparent',
                          }}
                        >
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: 'var(--text-primary)' }}
                          >
                            {m.title || `#${m.id}`}
                          </div>
                          <div
                            className="flex items-center gap-2 mt-0.5 text-xs"
                            style={{ color: 'var(--text-secondary)' }}
                          >
                            {(m.tags || []).slice(0, 3).map((t) => (
                              <span key={t}>#{t}</span>
                            ))}
                            {m.created_at && (
                              <span className="ml-auto">
                                {new Date(m.created_at).toLocaleDateString('zh-CN')}
                              </span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* 右栏: 详情 */}
        <div
          className="flex flex-col gap-3 p-4 rounded-xl overflow-y-auto"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
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
                  rows={10}
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
          ) : detailLoading ? (
            <div className="text-center py-6" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : !detail ? (
            <div
              className="flex flex-col items-center justify-center gap-2 flex-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">📖</div>
              <div>选择左侧记忆查看详情</div>
            </div>
          ) : (
            <>
              {/* 标题 + 层级 + 标签 */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {detail.title || `#${detail.id}`}
                  </h3>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium text-white"
                      style={{
                        background: LAYER_COLORS[detail.layer || 'L0'] || LAYER_COLORS.L0,
                      }}
                    >
                      {LAYER_LABELS[detail.layer || 'L0'] || detail.layer}
                    </span>
                    {(detail.tags || []).map((t) => (
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
              </div>

              {/* 内容 */}
              <div
                className="rounded-lg p-3 markdown-body"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  lineHeight: 1.7,
                }}
                dangerouslySetInnerHTML={{
                  __html:
                    detail.html_content ||
                    renderMarkdown(detail.content || ''),
                }}
              />

              {/* 反向链接 */}
              <div className="mt-2">
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
                        onClick={() => setSelectedId(bl.id)}
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
    </div>
  )
}
