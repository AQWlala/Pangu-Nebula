// v2.2.0 Phase 4 — 知识库面板
// 功能:
// 1. 知识库状态展示 (存储类型 / chunk 数)
// 2. 文档导入 (调用 /api/kb/import)
// 3. 检索测试 (调用 /api/kb/search)
// 4. 文档列表 (调用 /api/kb/documents)
//
// 注意: 此面板复用 v2.1.14 已有的 KB API,不重复造轮子。
// v2.2.0 的增量是 LanceDB 后端 + RAG 接入对话(由 KnowledgeService 处理)。
import { useState, useEffect, useCallback } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

// 知识库状态 (来自 KnowledgeService.get_status)
interface KBStatus {
  store_type: string // "lance" | "chroma"
  chunk_count: number
  persist_dir: string
}

// 文档列表项 (匹配 /api/kb/documents 返回格式)
interface KBDoc {
  id: string
  title: string
  type: string
  scope: string
}

// 检索结果
interface KBSearchResult {
  doc_id: string
  title: string
  chunk_text: string
  score: number
  source_method: string
  scope: string
  tags?: string[]
}

export default function KnowledgePanel() {
  const [status, setStatus] = useState<KBStatus | null>(null)
  const [docs, setDocs] = useState<KBDoc[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 导入表单
  const [importTitle, setImportTitle] = useState('')
  const [importContent, setImportContent] = useState('')
  const [importing, setImporting] = useState(false)

  // 检索测试
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KBSearchResult[]>([])
  const [searching, setSearching] = useState(false)

  // 加载状态 + 文档列表
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // 知识库状态 (由 KnowledgeService 提供, 通过自定义端点获取)
      // 注意: 此端点在 P3 后续会补上, 目前先容错
      try {
        const st = await apiGet<KBStatus>('/api/kb/status')
        setStatus(st)
      } catch {
        setStatus(null)
      }
      // 文档列表
      const data = await apiGet<{ documents: KBDoc[] }>(
        '/api/kb/documents'
      )
      const list = data.documents || []
      setDocs(list)
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 导入文档
  async function handleImport() {
    if (!importTitle.trim() || !importContent.trim()) {
      setError('标题和内容不能为空')
      return
    }
    setImporting(true)
    setError(null)
    try {
      await apiPost('/api/kb/import', {
        title: importTitle.trim(),
        content: importContent,
        type: 'note',
        scope: 'private',
        tags: [],
        categories: [],
      })
      setImportTitle('')
      setImportContent('')
      await loadData()
    } catch (e: any) {
      setError(e?.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // 检索测试
  async function handleSearch() {
    if (!query.trim()) {
      setError('查询不能为空')
      return
    }
    setSearching(true)
    setError(null)
    try {
      const data = await apiGet<{ results: KBSearchResult[] }>(
        `/api/kb/search?query=${encodeURIComponent(query)}&scope=private&top_k=5`
      )
      setResults(data.results || [])
    } catch (e: any) {
      setError(e?.message || '检索失败')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* 标题 + 状态 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          📚 知识库
        </h2>
        {status && (
          <div
            className="text-xs px-2 py-1 rounded-lg"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            {status.store_type === 'lance' ? '🚀 LanceDB' : '📦 ChromaDB'} ·{' '}
            {status.chunk_count} chunks
          </div>
        )}
      </div>

      {error && (
        <div
          className="text-xs px-3 py-2 rounded-lg"
          style={{ background: 'rgba(239,68,68,0.08)', color: '#EF4444' }}
        >
          {error}
        </div>
      )}

      {/* 文档导入 */}
      <div
        className="rounded-xl p-3 flex flex-col gap-2"
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
        }}
      >
        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          📥 导入文档
        </div>
        <input
          value={importTitle}
          onInput={(e) => setImportTitle((e.target as HTMLInputElement).value)}
          placeholder="文档标题..."
          className="px-2 py-1.5 rounded-lg text-sm"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
        <textarea
          value={importContent}
          onInput={(e) => setImportContent((e.target as HTMLTextAreaElement).value)}
          placeholder="文档内容 (Markdown 纯文本)..."
          rows={4}
          className="px-2 py-1.5 rounded-lg text-sm resize-y"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
        <button
          onClick={handleImport}
          disabled={importing || !importTitle.trim() || !importContent.trim()}
          className="px-3 py-1.5 rounded-lg text-sm font-semibold text-white disabled:opacity-50 self-start"
          style={{ background: '#3B82F6' }}
        >
          {importing ? '导入中...' : '导入'}
        </button>
      </div>

      {/* 检索测试 */}
      <div
        className="rounded-xl p-3 flex flex-col gap-2"
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
        }}
      >
        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          🔍 检索测试
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
            placeholder="输入查询文本..."
            className="flex-1 px-2 py-1.5 rounded-lg text-sm"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch()
            }}
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
            style={{ background: '#10B981' }}
          >
            {searching ? '检索中...' : '检索'}
          </button>
        </div>
        {results.length > 0 && (
          <div className="flex flex-col gap-2 mt-1">
            {results.map((r, i) => (
              <div
                key={`${r.doc_id}-${i}`}
                className="p-2 rounded-lg text-xs"
                style={{
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {r.title || r.doc_id}
                  </span>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    score: {r.score.toFixed(3)} · {r.source_method}
                  </span>
                </div>
                <div style={{ color: 'var(--text-secondary)' }}>
                  {r.chunk_text.slice(0, 200)}
                  {r.chunk_text.length > 200 ? '...' : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 文档列表 */}
      <div
        className="rounded-xl p-3 flex flex-col gap-2"
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
        }}
      >
        <div className="flex justify-between items-center">
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            📋 文档列表 ({docs.length})
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="text-xs px-2 py-1 rounded-lg"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            {loading ? '刷新中...' : '↻ 刷新'}
          </button>
        </div>
        {docs.length === 0 && !loading ? (
          <div className="text-xs text-center py-4" style={{ color: 'var(--text-secondary)' }}>
            暂无文档,请先导入
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {docs.map((d) => (
              <div
                key={d.id}
                className="p-2 rounded-lg text-xs flex justify-between items-center"
                style={{
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <span style={{ color: 'var(--text-primary)' }}>
                  {d.title || d.id}
                </span>
                <span
                  className="px-1.5 py-0.5 rounded text-[10px]"
                  style={{
                    background: 'var(--bg-card)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {d.scope}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
