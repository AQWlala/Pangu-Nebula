// Wiki 审核收件箱组件 (T2.6)
// - 列出待审核的 Wiki 写回条目
// - 点击条目显示详情 + DiffViewer 预览修改
// - 支持 merge/discard 操作
import { useState, useEffect, useCallback } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'
import DiffViewer from './DiffViewer'

// 审核条目
interface ReviewItem {
  id: number
  wiki_id: number
  title: string
  proposed_content: string
  current_content: string | null
  status: string
  scope: string
  proposed_by: string
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

export default function WikiReviewInbox() {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [actingId, setActingId] = useState<number | null>(null)
  const [scopeFilter, setScopeFilter] = useState<string>('')

  // 加载待审核列表
  const loadItems = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path = scopeFilter
        ? `/wiki-review/list?scope=${encodeURIComponent(scopeFilter)}`
        : '/wiki-review/list'
      const data = await apiGet<ReviewItem[]>(path)
      setItems(data || [])
    } catch (e: any) {
      setError(e?.message || '加载审核列表失败')
    } finally {
      setLoading(false)
    }
  }, [scopeFilter])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  // 获取选中的条目
  const selectedItem = items.find((i) => i.id === selectedId) || null

  // merge/discard 操作
  async function handleAction(
    item: ReviewItem,
    action: 'merge' | 'discard'
  ) {
    setActingId(item.id)
    try {
      await apiPost(`/wiki-review/${item.id}/${action}`, {
        review_note: action === 'discard' ? '已驳回' : '已合并',
      })
      // 操作后刷新列表
      if (selectedId === item.id) setSelectedId(null)
      await loadItems()
    } catch (e: any) {
      setError(e?.message || `${action} 操作失败`)
    } finally {
      setActingId(null)
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
          📥 审核收件箱
        </h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="scope 过滤(可选)"
            value={scopeFilter}
            onInput={(e) =>
              setScopeFilter((e.target as HTMLInputElement).value)
            }
            className="px-3 py-1.5 rounded-lg text-sm"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              width: 160,
            }}
          />
          <button
            onClick={loadItems}
            className="px-3 py-1.5 rounded-lg text-sm text-white"
            style={{ background: 'var(--accent)' }}
          >
            ↻ 刷新
          </button>
        </div>
      </div>

      {error && (
        <div
          className="p-3 rounded-lg text-sm"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            color: '#EF4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">
        {/* 左栏: 列表 */}
        <div
          className="flex flex-col gap-2 p-3 rounded-xl overflow-hidden"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            maxHeight: 600,
          }}
        >
          <div
            className="text-xs font-semibold px-1 pb-2 border-b"
            style={{
              color: 'var(--text-secondary)',
              borderColor: 'var(--border)',
            }}
          >
            待审核 ({items.length})
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div
                className="text-center py-6 text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                加载中...
              </div>
            ) : items.length === 0 ? (
              <div
                className="text-center py-6 text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                暂无待审核条目
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                {items.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    className="text-left px-2.5 py-2 rounded-lg transition"
                    style={{
                      background:
                        selectedId === item.id
                          ? 'var(--bg-secondary)'
                          : 'transparent',
                      border:
                        selectedId === item.id
                          ? '1px solid var(--accent)'
                          : '1px solid transparent',
                    }}
                  >
                    <div
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {item.title}
                    </div>
                    <div
                      className="text-xs mt-0.5 flex items-center gap-2"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      <span>wiki #{item.wiki_id}</span>
                      <span>·</span>
                      <span>{item.scope}</span>
                    </div>
                    {item.created_at && (
                      <div
                        className="text-xs mt-0.5"
                        style={{
                          color: 'var(--text-secondary)',
                          opacity: 0.7,
                        }}
                      >
                        {new Date(item.created_at).toLocaleString('zh-CN')}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 右栏: 详情 + Diff */}
        <div className="flex flex-col gap-3" style={{ maxHeight: 600 }}>
          {selectedItem ? (
            <>
              {/* 条目信息 */}
              <div
                className="rounded-xl p-3 flex flex-col gap-2"
                style={{
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                }}
              >
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <div
                      className="text-base font-semibold"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {selectedItem.title}
                    </div>
                    <div
                      className="text-xs mt-0.5"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      wiki #{selectedItem.wiki_id} · scope:{' '}
                      {selectedItem.scope} · 提交者:{' '}
                      {selectedItem.proposed_by}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleAction(selectedItem, 'merge')}
                      disabled={actingId === selectedItem.id}
                      className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
                      style={{ background: '#10B981' }}
                    >
                      {actingId === selectedItem.id ? '...' : '✓ 合并'}
                    </button>
                    <button
                      onClick={() => handleAction(selectedItem, 'discard')}
                      disabled={actingId === selectedItem.id}
                      className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
                      style={{ background: '#EF4444' }}
                    >
                      {actingId === selectedItem.id ? '...' : '✗ 丢弃'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Diff 预览 */}
              <DiffViewer itemId={selectedItem.id} />
            </>
          ) : (
            <div
              className="flex flex-col items-center justify-center flex-1 gap-2 rounded-xl p-6"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              <div className="text-5xl">📝</div>
              <div className="text-sm text-center">
                选择左侧条目查看 diff 预览
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
