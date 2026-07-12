// DAG 执行前审批横幅组件 (T2.3)
// - 当 DAG 计划就绪(plan_ready)时显示审批横幅
// - 提供 approve/reject 操作
// - reject 后可调用 reset-planning 回退到规划状态
import { useState, useEffect, useCallback } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

// 审批状态接口
interface ApprovalStatus {
  dag_id: string
  plan_ready: boolean
  overall_status: string // pending / approved / rejected / no_approval_needed
  pending_approvals: Array<{
    node_id: string
    title: string
    node_type: string
    status: string
  }>
  approved_count: number
  pending_count: number
  rejected_count: number
  non_approval_pending_count: number
}

interface ApprovalBannerProps {
  /** DAG ID,为空时不显示 */
  dagId: string | null
  /** 状态变化回调(批准/驳回/重置后触发) */
  onChanged?: () => void
}

export default function ApprovalBanner({ dagId, onChanged }: ApprovalBannerProps) {
  const [status, setStatus] = useState<ApprovalStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [acting, setActing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  // 加载审批状态
  const loadStatus = useCallback(async () => {
    if (!dagId) {
      setStatus(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await apiGet<ApprovalStatus>(
        `/dag/${encodeURIComponent(dagId)}/approval-status`
      )
      setStatus(data)
    } catch (e: any) {
      // 静默失败:横幅不阻塞主流程
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [dagId])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  // approve 操作
  async function handleApprove() {
    if (!dagId) return
    setActing(true)
    setError(null)
    try {
      await apiPost(`/dag/${encodeURIComponent(dagId)}/approve`, {})
      await loadStatus()
      onChanged?.()
    } catch (e: any) {
      setError(e?.message || '审批通过失败')
    } finally {
      setActing(false)
    }
  }

  // reject 操作
  async function handleReject() {
    if (!dagId) return
    if (!rejectReason.trim()) {
      setError('请填写驳回原因')
      return
    }
    setActing(true)
    setError(null)
    try {
      await apiPost(`/dag/${encodeURIComponent(dagId)}/reject`, {
        reason: rejectReason.trim(),
      })
      setRejectOpen(false)
      setRejectReason('')
      await loadStatus()
      onChanged?.()
    } catch (e: any) {
      setError(e?.message || '驳回失败')
    } finally {
      setActing(false)
    }
  }

  // 回退到规划状态
  async function handleResetPlanning() {
    if (!dagId) return
    setActing(true)
    setError(null)
    try {
      await apiPost(`/dag/${encodeURIComponent(dagId)}/reset-planning`, {})
      await loadStatus()
      onChanged?.()
    } catch (e: any) {
      setError(e?.message || '回退到规划失败')
    } finally {
      setActing(false)
    }
  }

  // 不显示的情况:无 dagId / 加载中 / 无需审批 / 已批准且无 rejected
  if (!dagId || loading || !status) return null
  if (status.overall_status === 'no_approval_needed') return null
  if (status.overall_status === 'approved' && status.rejected_count === 0) return null

  // 颜色与文案
  const isPending = status.overall_status === 'pending'
  const isRejected = status.overall_status === 'rejected'

  const bgColor = isPending
    ? 'rgba(59, 130, 246, 0.08)'
    : 'rgba(239, 68, 68, 0.08)'
  const borderColor = isPending ? 'rgba(59, 130, 246, 0.3)' : 'rgba(239, 68, 68, 0.3)'
  const textColor = isPending ? '#1E40AF' : '#991B1B'
  const icon = isPending ? '🔔' : '⚠️'

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{
        background: bgColor,
        border: `1px solid ${borderColor}`,
        color: textColor,
      }}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm flex items-center gap-2">
            <span>{icon}</span>
            {isPending ? (
              <span>
                DAG 计划就绪,等待审批 ({status.pending_count} 个待审批节点)
              </span>
            ) : (
              <span>DAG 已驳回,可回退到规划状态重新设计</span>
            )}
          </div>
          {status.pending_approvals.length > 0 && (
            <div className="text-xs mt-1 opacity-80">
              待审批节点:{' '}
              {status.pending_approvals
                .map((n) => `${n.title || n.node_id}`)
                .join(' / ')}
            </div>
          )}
          {isRejected && status.rejected_count > 0 && (
            <div className="text-xs mt-1 opacity-80">
              已驳回节点: {status.rejected_count} · 已批准节点:{' '}
              {status.approved_count}
            </div>
          )}
          {error && (
            <div className="text-xs mt-1" style={{ color: '#EF4444' }}>
              {error}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {isPending && (
            <>
              <button
                onClick={handleApprove}
                disabled={acting}
                className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
                style={{ background: '#10B981' }}
              >
                {acting ? '处理中...' : '✓ 批准执行'}
              </button>
              <button
                onClick={() => setRejectOpen(true)}
                disabled={acting}
                className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
                style={{ background: '#EF4444' }}
              >
                ✗ 驳回
              </button>
            </>
          )}
          {isRejected && (
            <button
              onClick={handleResetPlanning}
              disabled={acting}
              className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
              style={{ background: '#3B82F6' }}
            >
              {acting ? '处理中...' : '↻ 回退到规划'}
            </button>
          )}
        </div>
      </div>

      {/* 驳回原因对话框 */}
      {rejectOpen && (
        <div
          className="mt-2 p-3 rounded-lg"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
          }}
        >
          <div
            className="text-xs font-semibold mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            驳回原因
          </div>
          <textarea
            value={rejectReason}
            onInput={(e) =>
              setRejectReason((e.target as HTMLTextAreaElement).value)
            }
            placeholder="请说明驳回原因,用于改进规划..."
            rows={2}
            className="w-full px-2 py-1.5 rounded-lg text-sm resize-y"
            style={{
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          />
          <div className="flex gap-2 justify-end mt-2">
            <button
              onClick={() => {
                setRejectOpen(false)
                setRejectReason('')
                setError(null)
              }}
              disabled={acting}
              className="px-3 py-1 rounded-lg text-xs"
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
            >
              取消
            </button>
            <button
              onClick={handleReject}
              disabled={acting || !rejectReason.trim()}
              className="px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
              style={{ background: '#EF4444' }}
            >
              {acting ? '提交中...' : '确认驳回'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
