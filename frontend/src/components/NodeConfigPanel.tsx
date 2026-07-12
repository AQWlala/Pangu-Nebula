// 节点配置面板组件 (T2.4)
// - per-node model 选择
// - brief 编辑
// - 预检 API 调用,预检通过才执行
import { useState, useEffect, useCallback } from 'preact/hooks'
import { apiPost } from '../lib/api'

// DAG 节点类型(与 DAGCanvas 保持一致)
interface DAGNode {
  id: number
  dag_id: string
  node_id: string
  title: string
  node_type: string
  status: string
  model: string | null
  brief: string | null
  config: Record<string, any>
  result: string | null
  created_at: string | null
  updated_at: string | null
}

// 预检结果
interface PrecheckResult {
  dag_id: string
  node_id: string
  passed: boolean
  issues: string[]
  node: DAGNode
}

// 可选 model 列表(简单 mock,实际可从 /providers 获取)
const COMMON_MODELS = [
  { value: '', label: '(使用默认)' },
  { value: 'gpt-4', label: 'GPT-4 (OpenAI)' },
  { value: 'gpt-4o', label: 'GPT-4o (OpenAI)' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus (Anthropic)' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet (Anthropic)' },
  { value: 'gemini-pro', label: 'Gemini Pro (Google)' },
  { value: 'deepseek-chat', label: 'DeepSeek Chat' },
  { value: 'qwen-max', label: 'Qwen Max (Alibaba)' },
]

interface NodeConfigPanelProps {
  /** DAG ID */
  dagId: string
  /** 选中的节点 */
  node: DAGNode | null
  /** 关闭回调 */
  onClose: () => void
  /** 预检成功后回调(刷新 DAG 数据) */
  onPrechecked?: (result: PrecheckResult) => void
}

export default function NodeConfigPanel({
  dagId,
  node,
  onClose,
  onPrechecked,
}: NodeConfigPanelProps) {
  const [model, setModel] = useState('')
  const [brief, setBrief] = useState('')
  const [acting, setActing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PrecheckResult | null>(null)

  // 当节点变化时,同步 model/brief
  const syncFromNode = useCallback(() => {
    if (node) {
      setModel(node.model || '')
      setBrief(node.brief || '')
      setResult(null)
      setError(null)
    }
  }, [node])

  useEffect(() => {
    syncFromNode()
  }, [syncFromNode])

  // 执行预检
  async function handlePrecheck() {
    if (!node) return
    setActing(true)
    setError(null)
    setResult(null)
    try {
      const data = await apiPost<PrecheckResult>(
        `/dag/${encodeURIComponent(dagId)}/node/${encodeURIComponent(node.node_id)}/precheck`,
        {
          // model 为空字符串时不传(让后端用节点原值)
          model: model.trim() || null,
          brief: brief || null,
        }
      )
      setResult(data)
      if (data.passed) {
        onPrechecked?.(data)
      }
    } catch (e: any) {
      setError(e?.message || '预检失败')
    } finally {
      setActing(false)
    }
  }

  // 不渲染:无节点
  if (!node) return null

  const isPrecheckPassed =
    (result?.passed === true) || (node.config?.precheck_passed === true)

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2">
        <div>
          <div
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            🔧 节点配置
          </div>
          <div
            className="text-xs mt-0.5"
            style={{ color: 'var(--text-secondary)' }}
          >
            {node.title} (#{node.node_id})
          </div>
        </div>
        <button
          onClick={onClose}
          className="px-2 py-1 rounded-lg text-xs"
          style={{
            background: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          ✕ 关闭
        </button>
      </div>

      {/* Model 选择 */}
      <div className="flex flex-col gap-1">
        <label
          className="text-xs font-semibold"
          style={{ color: 'var(--text-secondary)' }}
        >
          🤖 Model
        </label>
        <select
          value={model}
          onChange={(e) =>
            setModel((e.target as HTMLSelectElement).value)
          }
          disabled={acting}
          className="px-3 py-2 rounded-lg text-sm"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          {COMMON_MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        {model && (
          <div
            className="text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            当前选择:{' '}
            <code style={{ fontFamily: 'monospace' }}>{model}</code>
          </div>
        )}
      </div>

      {/* Brief 编辑 */}
      <div className="flex flex-col gap-1">
        <label
          className="text-xs font-semibold"
          style={{ color: 'var(--text-secondary)' }}
        >
          📝 Brief Override
        </label>
        <textarea
          value={brief}
          onInput={(e) => setBrief((e.target as HTMLTextAreaElement).value)}
          placeholder="为此节点编写执行说明..."
          rows={4}
          disabled={acting}
          className="px-3 py-2 rounded-lg text-sm resize-y"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
        <div
          className="text-xs flex justify-between"
          style={{ color: 'var(--text-secondary)' }}
        >
          <span>{brief.length} / 2000 字符</span>
          {brief.length > 2000 && (
            <span style={{ color: '#EF4444' }}>超出长度限制</span>
          )}
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          className="p-2 rounded-lg text-xs"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            color: '#EF4444',
            border: '1px solid rgba(239, 68, 68, 0.3)',
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* 预检结果 */}
      {result && (
        <div
          className="p-3 rounded-lg flex flex-col gap-1"
          style={{
            background: result.passed
              ? 'rgba(16, 185, 129, 0.08)'
              : 'rgba(239, 68, 68, 0.08)',
            border: `1px solid ${
              result.passed
                ? 'rgba(16, 185, 129, 0.3)'
                : 'rgba(239, 68, 68, 0.3)'
            }`,
          }}
        >
          <div
            className="text-xs font-semibold flex items-center gap-2"
            style={{
              color: result.passed ? '#065F46' : '#991B1B',
            }}
          >
            {result.passed ? '✓ 预检通过' : '✗ 预检失败'}
          </div>
          {result.issues.length > 0 && (
            <ul
              className="text-xs ml-4"
              style={{ color: '#991B1B', listStyle: 'disc' }}
            >
              {result.issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
          {result.passed && (
            <div
              className="text-xs"
              style={{ color: '#065F46' }}
            >
              该节点已通过预检,可执行
            </div>
          )}
        </div>
      )}

      {/* 操作按钮 */}
      <div className="flex gap-2 justify-end">
        <button
          onClick={handlePrecheck}
          disabled={acting || brief.length > 2000}
          className="px-4 py-1.5 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {acting ? '预检中...' : '🔍 执行预检'}
        </button>
      </div>

      {/* 当前状态指示 */}
      <div
        className="text-xs flex items-center gap-1"
        style={{ color: 'var(--text-secondary)' }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isPrecheckPassed ? '#10B981' : '#9CA3AF',
            display: 'inline-block',
          }}
        />
        {isPrecheckPassed
          ? '该节点已通过预检'
          : '该节点尚未通过预检'}
      </div>
    </div>
  )
}
