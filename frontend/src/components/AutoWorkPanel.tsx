import { useState, useEffect } from 'preact/hooks'
import { apiGet, apiPost, apiDelete } from '../lib/api'

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

// v2.3.0 Phase 3-D: 定时任务 (scheduler) 类型
interface SchedulerJobItem {
  id: number
  name: string
  cron_expr: string
  action: Record<string, any>
  enabled: boolean
  created_at?: string | null
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

  // v2.3.0 Phase 3-D: 定时任务 (scheduler) 生命周期管理
  const [schedulerJobs, setSchedulerJobs] = useState<SchedulerJobItem[]>([])
  const [schedulerLoading, setSchedulerLoading] = useState(false)
  const [schedulerActingId, setSchedulerActingId] = useState<number | null>(null)

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

  // v2.3.0 Phase 3-D: 加载定时任务列表
  const loadSchedulerJobs = async () => {
    setSchedulerLoading(true)
    try {
      const data = await apiGet<SchedulerJobItem[]>('/scheduler/jobs')
      setSchedulerJobs(Array.isArray(data) ? data : [])
    } catch (e: any) {
      // scheduler 为可选模块, 失败时静默
      setSchedulerJobs([])
    } finally {
      setSchedulerLoading(false)
    }
  }

  // v2.3.0 Phase 3-D: 定时任务生命周期操作
  const handleSchedulerAction = async (
    job: SchedulerJobItem,
    action: 'cancel' | 'pause' | 'resume' | 'delete'
  ) => {
    setSchedulerActingId(job.id)
    try {
      if (action === 'delete') {
        await apiDelete(`/scheduler/jobs/${job.id}`)
      } else {
        await apiPost(`/scheduler/jobs/${job.id}/${action}`)
      }
      await loadSchedulerJobs()
    } catch (e: any) {
      setError(e?.message || `任务${action}操作失败`)
    } finally {
      setSchedulerActingId(null)
    }
  }

  useEffect(() => {
    loadKanban()
    loadSchedulerJobs()
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

      {/* v2.3.0 Phase 3-D: 定时任务 (scheduler) 生命周期管理 */}
      <div className="bg-white rounded-xl p-4 mt-6 shadow-sm border border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold text-gray-700">⏰ 定时任务管理</h3>
            <p className="text-xs text-gray-500 mt-0.5">生命周期: 取消 / 删除 / 暂停 / 恢复</p>
          </div>
          <button
            onClick={loadSchedulerJobs}
            disabled={schedulerLoading}
            className="px-3 py-1 rounded-lg bg-gray-100 text-gray-700 text-xs hover:bg-gray-200 disabled:opacity-50 transition-colors"
          >
            {schedulerLoading ? '刷新中...' : '🔄 刷新'}
          </button>
        </div>

        {schedulerLoading && schedulerJobs.length === 0 ? (
          <p className="text-center text-gray-400 text-xs py-6">加载中...</p>
        ) : schedulerJobs.length === 0 ? (
          <p className="text-center text-gray-400 text-xs py-6">暂无定时任务</p>
        ) : (
          <div className="flex flex-col gap-2">
            {schedulerJobs.map((job) => {
              const acting = schedulerActingId === job.id
              return (
                <div
                  key={job.id}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: job.enabled ? '#38a169' : '#d1d5db' }}
                      />
                      <span className="text-sm font-semibold text-gray-800 truncate">
                        #{job.id} {job.name}
                      </span>
                      <span
                        className="text-xs px-1.5 py-0.5 rounded-full"
                        style={{
                          background: job.enabled ? '#ebf8ff' : '#f7fafc',
                          color: job.enabled ? '#3182ce' : '#718096',
                        }}
                      >
                        {job.enabled ? '已启用' : '已暂停'}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      ⏱ {job.cron_expr}
                      {job.action?.type ? ` · ${job.action.type}` : ''}
                    </div>
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    {/* 启用时: 可暂停/取消/删除; 暂停时: 可恢复/删除 */}
                    {job.enabled ? (
                      <button
                        onClick={() => handleSchedulerAction(job, 'pause')}
                        disabled={acting}
                        title="暂停"
                        className="px-2 py-1 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200 disabled:opacity-50 transition-colors"
                      >
                        暂停
                      </button>
                    ) : (
                      <button
                        onClick={() => handleSchedulerAction(job, 'resume')}
                        disabled={acting}
                        title="恢复"
                        className="px-2 py-1 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-50 transition-colors"
                      >
                        恢复
                      </button>
                    )}
                    <button
                      onClick={() => handleSchedulerAction(job, 'cancel')}
                      disabled={acting}
                      title="取消运行中任务"
                      className="px-2 py-1 rounded text-xs bg-orange-100 text-orange-700 hover:bg-orange-200 disabled:opacity-50 transition-colors"
                    >
                      停止
                    </button>
                    <button
                      onClick={() => handleSchedulerAction(job, 'delete')}
                      disabled={acting}
                      title="删除任务"
                      className="px-2 py-1 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-50 transition-colors"
                    >
                      删除
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
