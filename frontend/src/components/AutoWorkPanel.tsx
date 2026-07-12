import { useState, useEffect } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

interface AutoWorkTask {
  id: number
  title: string
  description: string
  status: string
  priority: number
  assigned_to: string | null
  config: Record<string, any>
  result: string | null
  created_at: string | null
}

interface KanbanData {
  groups: {
    pending: AutoWorkTask[]
    running: AutoWorkTask[]
    completed: AutoWorkTask[]
  }
  counts: Record<string, number>
  total: number
}

const COLUMNS: { key: 'pending' | 'running' | 'completed'; label: string; color: string; icon: string }[] = [
  { key: 'pending', label: '待处理', color: '#718096', icon: '⏳' },
  { key: 'running', label: '进行中', color: '#3182ce', icon: '🔄' },
  { key: 'completed', label: '已完成', color: '#38a169', icon: '✅' },
]

function priorityBadge(p: number): string {
  if (p >= 8) return '🔴 高'
  if (p >= 4) return '🟡 中'
  return '🟢 低'
}

export default function AutoWorkPanel() {
  const [kanban, setKanban] = useState<KanbanData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actingId, setActingId] = useState<number | null>(null)

  // 创建表单
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)

  const loadKanban = async () => {
    try {
      const data = await apiGet<KanbanData>('/autowork/kanban')
      setKanban(data)
    } catch (e: any) {
      setError(e?.message || '加载看板失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadKanban()
  }, [])

  const handleCreate = async () => {
    if (!title.trim()) {
      setError('请填写任务标题')
      return
    }
    setCreating(true)
    setError('')
    try {
      await apiPost('/autowork', { title: title.trim(), description: description.trim() })
      setTitle('')
      setDescription('')
      await loadKanban()
    } catch (e: any) {
      setError(e?.message || '创建任务失败')
    } finally {
      setCreating(false)
    }
  }

  const handleAction = async (task: AutoWorkTask, action: 'claim' | 'complete' | 'pause') => {
    setActingId(task.id)
    try {
      if (action === 'claim') {
        await apiPost(`/autowork/${task.id}/claim`, { assigned_to: 'agent' })
      } else if (action === 'complete') {
        await apiPost(`/autowork/${task.id}/complete`, { result: 'done' })
      } else if (action === 'pause') {
        await apiPost(`/autowork/${task.id}/pause`)
      }
      await loadKanban()
    } catch (e: any) {
      setError(e?.message || '操作失败')
    } finally {
      setActingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-gray-500">加载中...</span>
      </div>
    )
  }

  return (
    <div className="h-full w-full overflow-y-auto p-6 bg-gray-50">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-800">🤖 AutoWork 无人值守</h2>
        <p className="text-sm text-gray-500 mt-1">任务自动认领、执行与完成</p>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-600 text-sm border border-red-200">
          ⚠️ {error}
        </div>
      )}

      {/* 创建任务表单 */}
      <div className="bg-white rounded-xl p-4 mb-6 shadow-sm border border-gray-200">
        <h3 className="text-base font-semibold text-gray-700 mb-3">✨ 创建新任务</h3>
        <div className="flex gap-3 mb-2">
          <input
            type="text"
            value={title}
            onInput={(e) => setTitle((e.target as HTMLInputElement).value)}
            placeholder="任务标题..."
            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-sm outline-none focus:border-blue-400"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !title.trim()}
            className="px-4 py-2 rounded-lg bg-blue-500 text-white text-sm font-semibold disabled:bg-gray-300 hover:bg-blue-600 transition-colors"
          >
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
        <textarea
          value={description}
          onInput={(e) => setDescription((e.target as HTMLTextAreaElement).value)}
          placeholder="任务描述(可选)..."
          rows={2}
          className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm outline-none focus:border-blue-400 resize-y"
        />
      </div>

      {/* 看板视图 */}
      <div className="grid grid-cols-3 gap-4">
        {COLUMNS.map((col) => {
          const tasks = kanban?.groups?.[col.key] ?? []
          return (
            <div key={col.key} className="bg-gray-100 rounded-xl p-3 min-h-[300px]">
              <div className="flex items-center justify-between mb-3 px-1">
                <span className="text-sm font-semibold text-gray-700">
                  {col.icon} {col.label}
                </span>
                <span
                  className="text-xs font-bold px-2 py-0.5 rounded-full text-white"
                  style={{ background: col.color }}
                >
                  {tasks.length}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {tasks.length === 0 ? (
                  <p className="text-center text-gray-400 text-xs py-8">暂无任务</p>
                ) : (
                  tasks.map((task) => (
                    <div
                      key={task.id}
                      className="bg-white rounded-lg p-3 shadow-sm border border-gray-200"
                    >
                      <div className="flex items-start justify-between mb-1">
                        <span className="text-sm font-semibold text-gray-800 flex-1">
                          {task.title}
                        </span>
                        <span className="text-xs text-gray-500 ml-2">
                          {priorityBadge(task.priority)}
                        </span>
                      </div>
                      {task.description && (
                        <p className="text-xs text-gray-500 mb-2 line-clamp-2">
                          {task.description}
                        </p>
                      )}
                      {task.assigned_to && (
                        <p className="text-xs text-blue-500 mb-2">
                          👤 {task.assigned_to}
                        </p>
                      )}
                      {/* 操作按钮 */}
                      <div className="flex gap-1 mt-2">
                        {task.status === 'pending' && (
                          <button
                            onClick={() => handleAction(task, 'claim')}
                            disabled={actingId === task.id}
                            className="px-2 py-1 rounded text-xs bg-blue-100 text-blue-600 hover:bg-blue-200 disabled:opacity-50 transition-colors"
                          >
                            认领
                          </button>
                        )}
                        {task.status === 'running' && (
                          <>
                            <button
                              onClick={() => handleAction(task, 'complete')}
                              disabled={actingId === task.id}
                              className="px-2 py-1 rounded text-xs bg-green-100 text-green-600 hover:bg-green-200 disabled:opacity-50 transition-colors"
                            >
                              完成
                            </button>
                            <button
                              onClick={() => handleAction(task, 'pause')}
                              disabled={actingId === task.id}
                              className="px-2 py-1 rounded text-xs bg-yellow-100 text-yellow-600 hover:bg-yellow-200 disabled:opacity-50 transition-colors"
                            >
                              暂停
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
