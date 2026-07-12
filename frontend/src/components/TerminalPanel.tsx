// 终端面板组件 (T5.7)
// - 显示终端输出区域(黑色背景,绿色文字,等宽字体)
// - 命令输入框
// - 会话管理(创建/关闭)
// - 自动滚动到底部
// - 支持 mock 模式提示
import { useState, useEffect, useRef, useCallback } from 'preact/hooks'
import { apiGet, apiPost, apiDelete } from '../lib/api'

interface TerminalSession {
  session_id: string
  mock: boolean
  shell: string
  cols: number
  rows: number
}

interface SessionListItem {
  session_id: string
  mock: boolean
  shell: string
  cols: number
  rows: number
  created_at?: number
}

export default function TerminalPanel() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isMock, setIsMock] = useState(false)
  const [outputLines, setOutputLines] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [status, setStatus] = useState<{ available: boolean; mode: string; active_sessions: number } | null>(null)
  const [shell, setShell] = useState('powershell')

  const outputRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const pollTimer = useRef<number | null>(null)

  // 自动滚动到底部
  const scrollToBottom = useCallback(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [outputLines, scrollToBottom])

  // 加载状态与会话列表
  const loadStatus = useCallback(async () => {
    try {
      const data = await apiGet<{ available: boolean; mode: string; active_sessions: number }>('/terminal/status')
      setStatus(data)
    } catch {
      // 后端可能未启动
    }
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const data = await apiGet<SessionListItem[]>('/terminal/sessions')
      setSessions(data || [])
    } catch {
      // 静默
    }
  }, [])

  useEffect(() => {
    loadStatus()
    loadSessions()
  }, [loadStatus, loadSessions])

  // 轮询读取终端输出
  useEffect(() => {
    if (!sessionId) {
      if (pollTimer.current) {
        clearInterval(pollTimer.current)
        pollTimer.current = null
      }
      return
    }
    // 立即读一次
    readOutput()
    // 每 800ms 轮询一次
    pollTimer.current = window.setInterval(readOutput, 800)
    return () => {
      if (pollTimer.current) {
        clearInterval(pollTimer.current)
        pollTimer.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // 创建会话
  async function createSession() {
    setLoading(true)
    setError(null)
    try {
      const data = await apiPost<TerminalSession>('/terminal/session', {
        shell,
        cols: 80,
        rows: 24,
      })
      setSessionId(data.session_id)
      setIsMock(data.mock)
      setOutputLines([
        `┌─ 终端会话已创建 ─────────────────────────┐`,
        `│ session: ${data.session_id}`,
        `│ shell: ${data.shell}`,
        `│ mode: ${data.mock ? 'mock (无 PTY 依赖)' : 'real PTY'}`,
        `└──────────────────────────────────────────┘`,
        '',
      ])
      await loadStatus()
      await loadSessions()
      // 自动聚焦输入框
      setTimeout(() => inputRef.current?.focus(), 100)
    } catch (e: any) {
      setError(e?.message || '创建会话失败')
    } finally {
      setLoading(false)
    }
  }

  // 关闭会话
  async function closeSession() {
    if (!sessionId) return
    setLoading(true)
    try {
      await apiDelete(`/terminal/${sessionId}`)
      setOutputLines((prev) => [...prev, '', '[会话已关闭]'])
      setSessionId(null)
      setIsMock(false)
      await loadStatus()
      await loadSessions()
    } catch (e: any) {
      setError(e?.message || '关闭会话失败')
    } finally {
      setLoading(false)
    }
  }

  // 读取输出
  async function readOutput() {
    if (!sessionId) return
    try {
      const data = await apiGet<{ data: string; mock: boolean }>(`/terminal/${sessionId}/read?timeout=0.3`)
      if (data?.data) {
        // 按换行符拆分,追加到输出
        const lines = data.data.split('\n')
        setOutputLines((prev) => [...prev, ...lines])
      }
    } catch {
      // 读取失败时静默(可能是会话已关闭)
    }
  }

  // 发送命令
  async function sendCommand() {
    if (!sessionId || !input) return
    const cmd = input
    setInput('')
    // 在输出区显示用户输入
    setOutputLines((prev) => [...prev, `> ${cmd}`])
    try {
      const data = await apiPost<{ mock: boolean; output?: string; written?: number }>(
        `/terminal/${sessionId}/write`,
        { data: cmd + '\n' },
      )
      if (data?.mock && data.output) {
        // mock 模式直接显示返回的占位输出
        setOutputLines((prev) => [...prev, data.output])
      }
    } catch (e: any) {
      setOutputLines((prev) => [...prev, `[错误] ${e?.message || '发送失败'}`])
    }
  }

  // 切换到指定会话
  async function switchSession(sid: string) {
    setSessionId(sid)
    setOutputLines([`[切换到会话: ${sid}]`, ''])
  }

  // 处理键盘事件: Enter 发送, Ctrl+L 清屏
  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      sendCommand()
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault()
      setOutputLines([])
    }
  }

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border)',
      }}
    >
      {/* 顶部: 标题 + 状态 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          🖥️ 终端模式
        </h2>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {status && (
            <>
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: status.available ? '#28C840' : '#FFBD2E',
                }}
              />
              <span>{status.available ? 'real PTY' : 'mock 模式'}</span>
              <span>·</span>
              <span>{status.active_sessions} 个活跃会话</span>
            </>
          )}
        </div>
      </div>

      {/* 控制条: shell 选择 + 创建/关闭会话 */}
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={shell}
          onChange={(e) => setShell((e.target as HTMLSelectElement).value)}
          disabled={!!sessionId}
          className="px-3 py-1.5 rounded-lg text-sm"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <option value="powershell">PowerShell</option>
          <option value="cmd">CMD</option>
          <option value="bash">Bash</option>
          <option value="sh">SH</option>
        </select>
        {!sessionId ? (
          <button
            onClick={createSession}
            disabled={loading}
            className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
            style={{ background: 'var(--accent)' }}
          >
            {loading ? '创建中...' : '+ 新建会话'}
          </button>
        ) : (
          <button
            onClick={closeSession}
            disabled={loading}
            className="px-4 py-1.5 rounded-lg text-sm font-medium text-white"
            style={{ background: '#EF4444' }}
          >
            {loading ? '关闭中...' : '关闭会话'}
          </button>
        )}
        {isMock && (
          <span
            className="px-2 py-0.5 rounded-full text-xs"
            style={{ background: 'rgba(255,189,46,0.2)', color: '#FFBD2E' }}
          >
            mock 模式
          </span>
        )}
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: 'rgba(239,68,68,0.1)', color: '#EF4444' }}
        >
          {error}
        </div>
      )}

      {/* 终端输出区 */}
      <div
        ref={outputRef}
        className="rounded-lg p-3 font-mono text-sm overflow-auto"
        style={{
          background: '#0A0A0A',
          color: '#28C840',
          minHeight: 320,
          maxHeight: 480,
          border: '1px solid #1F1F1F',
          boxShadow: 'inset 0 0 12px rgba(0,0,0,0.5)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          lineHeight: 1.4,
        }}
      >
        {outputLines.length === 0 ? (
          <div style={{ color: '#5A5A5A' }}>
            {'// 终端输出将显示在这里'}
            <br />
            {'// 点击「新建会话」开始'}
          </div>
        ) : (
          outputLines.map((line, i) => (
            <div key={i} style={{ minHeight: '1.4em' }}>
              {line || '\u00A0'}
            </div>
          ))
        )}
      </div>

      {/* 输入框 */}
      <div className="flex items-center gap-2">
        <span
          className="font-mono text-sm flex-shrink-0"
          style={{ color: sessionId ? '#28C840' : 'var(--text-secondary)' }}
        >
          {sessionId ? '$' : '›'}
        </span>
        <input
          ref={inputRef}
          type="text"
          value={input}
          disabled={!sessionId}
          onInput={(e) => setInput((e.target as HTMLInputElement).value)}
          onKeyDown={handleKeyDown}
          placeholder={sessionId ? '输入命令并按 Enter 执行 (Ctrl+L 清屏)' : '请先创建终端会话'}
          className="flex-1 px-3 py-1.5 rounded-lg text-sm font-mono"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            fontFamily: 'monospace',
          }}
        />
        <button
          onClick={sendCommand}
          disabled={!sessionId || !input}
          className="px-3 py-1.5 rounded-lg text-sm font-medium text-white"
          style={{
            background: sessionId && input ? 'var(--accent)' : 'var(--bg-secondary)',
            color: sessionId && input ? '#fff' : 'var(--text-secondary)',
          }}
        >
          发送
        </button>
      </div>

      {/* 活跃会话列表 */}
      {sessions.length > 0 && (
        <div className="flex flex-col gap-1 mt-1">
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            活跃会话:
          </div>
          <div className="flex flex-wrap gap-1">
            {sessions.map((s) => (
              <button
                key={s.session_id}
                onClick={() => switchSession(s.session_id)}
                className="px-2 py-0.5 rounded text-xs font-mono"
                style={{
                  background:
                    s.session_id === sessionId ? 'var(--accent)' : 'var(--bg-secondary)',
                  color: s.session_id === sessionId ? '#fff' : 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
                title={`${s.shell} · ${s.mock ? 'mock' : 'real'} · ${s.cols}x${s.rows}`}
              >
                {s.session_id.slice(0, 12)}
                {s.mock ? ' (mock)' : ''}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
