// Wiki 浏览器组件
// 左栏: Wiki 页面列表 + 右栏: 页面内容(HTML) + 编辑模式
import { useState, useEffect, useMemo } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

// Wiki 页面类型(本地定义,后端 GET /wiki/pages 返回)
interface WikiPage {
  id: number
  title: string
  content?: string // Markdown 源文
  html_content?: string // 渲染后 HTML
  tags?: string[]
  status?: string
  source_conversation_id?: number | null
  created_at?: string
  updated_at?: string
}

// 极简 Markdown → HTML(用于编辑预览)
function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  html = html.replace(/```([\s\S]*?)```/g, (_m, c) => `<pre>${c}</pre>`)
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

export default function WikiBrowser() {
  const [pages, setPages] = useState<WikiPage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 搜索
  const [search, setSearch] = useState('')

  // 当前选中
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<WikiPage | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // 编辑模式
  const [editMode, setEditMode] = useState(false)
  const [editContent, setEditContent] = useState('')

  // 编译对话框
  const [compileOpen, setCompileOpen] = useState(false)
  const [convId, setConvId] = useState('')
  const [compileTitle, setCompileTitle] = useState('')
  const [compiling, setCompiling] = useState(false)

  // 加载列表
  async function loadPages() {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<WikiPage[] | { items?: WikiPage[] }>('/wiki/pages')
      const list = Array.isArray(data) ? data : data?.items || []
      // 按创建时间倒序
      list.sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0
        return tb - ta
      })
      setPages(list)
      if (list.length > 0 && selectedId == null) {
        setSelectedId(list[0].id)
      }
    } catch (e: any) {
      setError(e?.message || '加载 Wiki 失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPages()
  }, [])

  // 加载详情
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setEditMode(false)
    apiGet<WikiPage>(`/wiki/pages/${selectedId}`)
      .then((d) => {
        if (!cancelled) setDetail(d)
      })
      .catch(() => {
        if (!cancelled) setDetail(null)
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // 过滤列表
  const filtered = useMemo(() => {
    if (!search) return pages
    const q = search.toLowerCase()
    return pages.filter((p) => (p.title || '').toLowerCase().includes(q))
  }, [pages, search])

  // 进入编辑模式
  function enterEdit() {
    if (!detail) return
    setEditContent(detail.content || '')
    setEditMode(true)
  }

  // 保存编辑(用 POST /wiki 编译接口不需要,这里用创建/更新)
  // 由于任务只要求 apiGet/apiPost,这里使用 POST /wiki 创建新版本
  async function saveEdit() {
    if (!detail) return
    try {
      await apiPost('/wiki', {
        title: detail.title,
        content: editContent,
        html_content: renderMarkdown(editContent),
        tags: detail.tags || [],
        source_conversation_id: detail.source_conversation_id || null,
      })
      setEditMode(false)
      await loadPages()
    } catch (e: any) {
      alert(e?.message || '保存失败')
    }
  }

  // 编译对话为 Wiki
  async function compileFromConversation() {
    const id = parseInt(convId, 10)
    if (!id) {
      alert('请输入有效的对话 ID')
      return
    }
    setCompiling(true)
    try {
      const result = await apiPost<WikiPage>('/wiki/compile', {
        conversation_id: id,
        title: compileTitle || undefined,
      })
      setCompileOpen(false)
      setConvId('')
      setCompileTitle('')
      await loadPages()
      if (result?.id != null) setSelectedId(result.id)
    } catch (e: any) {
      alert(e?.message || '编译失败')
    } finally {
      setCompiling(false)
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
          📖 Wiki 浏览器
        </h2>
        <button
          onClick={() => setCompileOpen(true)}
          className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          ⚙ 从对话编译
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-4" style={{ minHeight: 480 }}>
        {/* 左栏: 列表 */}
        <div
          className="flex flex-col gap-2 p-3 rounded-xl overflow-hidden"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <input
            type="text"
            placeholder="🔍 搜索 Wiki 页面"
            value={search}
            onInput={(e) => setSearch((e.target as HTMLInputElement).value)}
            className="px-2 py-1.5 rounded-lg text-sm"
            style={{
              background: 'var(--bg-card)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          />
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
                暂无 Wiki 页面
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                {filtered.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className="text-left px-2.5 py-2 rounded-lg transition"
                    style={{
                      background:
                        selectedId === p.id ? 'var(--bg-secondary)' : 'transparent',
                      border:
                        selectedId === p.id
                          ? '1px solid var(--accent)'
                          : '1px solid transparent',
                    }}
                  >
                    <div
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {p.title || `#${p.id}`}
                    </div>
                    <div
                      className="text-xs mt-0.5"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {p.created_at
                        ? new Date(p.created_at).toLocaleDateString('zh-CN')
                        : '—'}
                      {p.status ? ` · ${p.status}` : ''}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 右栏: 内容 */}
        <div
          className="flex flex-col gap-3 p-4 rounded-xl overflow-y-auto"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          {detailLoading ? (
            <div className="text-center py-6" style={{ color: 'var(--text-secondary)' }}>
              加载中...
            </div>
          ) : !detail ? (
            <div
              className="flex flex-col items-center justify-center gap-2 flex-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              <div className="text-5xl">📚</div>
              <div>选择左侧页面查看内容</div>
            </div>
          ) : editMode ? (
            // 编辑模式
            <>
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                  ✏ 编辑: {detail.title}
                </h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditMode(false)}
                    className="px-3 py-1 rounded-lg text-sm"
                    style={{
                      background: 'var(--bg-card)',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    取消
                  </button>
                  <button
                    onClick={saveEdit}
                    className="px-3 py-1 rounded-lg text-sm font-medium text-white"
                    style={{ background: 'var(--accent)' }}
                  >
                    保存
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1" style={{ minHeight: 360 }}>
                <textarea
                  value={editContent}
                  onInput={(e) => setEditContent((e.target as HTMLTextAreaElement).value)}
                  className="p-3 rounded-lg text-sm font-mono h-full resize-none"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                  }}
                />
                <div
                  className="p-3 rounded-lg overflow-y-auto markdown-body"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                    fontSize: '14px',
                    lineHeight: 1.7,
                  }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(editContent) }}
                />
              </div>
            </>
          ) : (
            // 查看模式
            <>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {detail.title || `#${detail.id}`}
                  </h3>
                  <div
                    className="flex items-center gap-2 mt-1 text-xs flex-wrap"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {detail.created_at && (
                      <span>
                        创建于 {new Date(detail.created_at).toLocaleString('zh-CN')}
                      </span>
                    )}
                    {detail.status && (
                      <span
                        className="px-2 py-0.5 rounded-full"
                        style={{ background: 'var(--bg-secondary)' }}
                      >
                        {detail.status}
                      </span>
                    )}
                    {(detail.tags || []).map((t) => (
                      <span key={t}>#{t}</span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={enterEdit}
                  className="px-3 py-1 rounded-lg text-sm"
                  style={{
                    background: 'var(--bg-secondary)',
                    color: 'var(--text-primary)',
                  }}
                >
                  ✏ 编辑
                </button>
              </div>
              <div
                className="rounded-lg p-4 markdown-body flex-1"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: '15px',
                  lineHeight: 1.8,
                }}
                dangerouslySetInnerHTML={{
                  __html:
                    detail.html_content ||
                    renderMarkdown(detail.content || '') ||
                    '<p style="color:var(--text-secondary)">此页面暂无内容</p>',
                }}
              />
            </>
          )}
        </div>
      </div>

      {/* 编译对话框 */}
      {compileOpen && (
        <div
          className="fixed inset-0 flex items-center justify-center p-4 z-50"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setCompileOpen(false)}
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
              从对话编译 Wiki
            </h3>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                对话 ID
              </label>
              <input
                type="number"
                placeholder="例如: 12"
                value={convId}
                onInput={(e) => setConvId((e.target as HTMLInputElement).value)}
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
                标题(可选)
              </label>
              <input
                type="text"
                placeholder="留空使用对话标题"
                value={compileTitle}
                onInput={(e) => setCompileTitle((e.target as HTMLInputElement).value)}
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
                onClick={() => setCompileOpen(false)}
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
                onClick={compileFromConversation}
                disabled={compiling}
                className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
                style={{ background: 'var(--accent)' }}
              >
                {compiling ? '编译中...' : '开始编译'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
