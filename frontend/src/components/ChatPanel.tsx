import { useState, useEffect, useRef } from 'preact/hooks'
import { apiGet, apiPost, apiStream } from '../lib/api'
import type { Conversation, Message } from '../lib/types'

// ===== 工具函数 =====

/** 获取角色头像 emoji,缺省返回友好默认值 */
function getPersonaAvatar(p: any): string {
  return p?.avatar || '🧸'
}

/** 格式化时间为中文相对时间 */
function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const min = Math.floor(diff / 60000)
  const hour = Math.floor(diff / 3600000)
  const day = Math.floor(diff / 86400000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  if (hour < 24) return `${hour} 小时前`
  if (day < 7) return `${day} 天前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ===== Markdown 渲染 =====

/** 转义 HTML 特殊字符 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** 处理行内 Markdown(加粗 / 斜体 / 行内代码) */
function renderInline(text: string): string {
  let r = escapeHtml(text)
  r = r.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')
  r = r.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  r = r.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  return r
}

/** 渲染基本 Markdown 为 HTML 字符串 */
function renderMarkdown(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  let inCode = false
  let codeBuf: string[] = []
  let inList = false

  const closeList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }

  for (const line of lines) {
    // 代码块开始/结束
    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push(`<pre class="md-code-block"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`)
        inCode = false
        codeBuf = []
      } else {
        closeList()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }

    // 列表项
    if (line.trim().startsWith('- ')) {
      if (!inList) {
        out.push('<ul class="md-list">')
        inList = true
      }
      out.push(`<li>${renderInline(line.trim().slice(2))}</li>`)
      continue
    }
    closeList()

    // 引用
    if (line.trim().startsWith('> ')) {
      out.push(`<blockquote class="md-quote">${renderInline(line.trim().slice(2))}</blockquote>`)
      continue
    }

    // 普通段落
    if (line.trim()) {
      out.push(`<p class="md-p">${renderInline(line)}</p>`)
    }
  }

  closeList()
  if (inCode) {
    out.push(`<pre class="md-code-block"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`)
  }
  return out.join('')
}

// ===== 组件 =====

export default function ChatPanel() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentId, setCurrentId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [activePersona, setActivePersona] = useState<any>(null)
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // 加载对话列表
  const loadConversations = async () => {
    try {
      const data = await apiGet<Conversation[]>('/chat/conversations')
      setConversations(data || [])
    } catch (e: any) {
      setError(e?.message || '加载对话失败')
    }
  }

  // 加载当前激活角色 (兜底: 无激活时回退到列表第一个)
  const loadActivePersona = async () => {
    try {
      const data = await apiGet<any>('/persona/active')
      if (data) {
        setActivePersona(data)
        return
      }
    } catch {
      // 暂无激活角色, 尝试列表兜底
    }
    // 兜底: 无激活角色时取列表第一个, 避免创建无 persona 对话
    try {
      const list = await apiGet<any[]>('/persona')
      if (list && list.length > 0) {
        setActivePersona(list[0])
      }
    } catch {
      // 列表也为空, 保持 null (后端有 _DEFAULT_PERSONA 兜底)
    }
  }

  // 加载某对话的消息
  const loadMessages = async (id: number) => {
    setLoading(true)
    try {
      const data = await apiGet<Message[]>(`/chat/conversations/${id}/messages`)
      setMessages(data || [])
    } catch (e: any) {
      setError(e?.message || '加载消息失败')
    } finally {
      setLoading(false)
    }
  }

  // 初始化
  useEffect(() => {
    loadConversations()
    loadActivePersona()
  }, [])

  // 切换对话时加载消息
  useEffect(() => {
    if (currentId !== null) {
      loadMessages(currentId)
    } else {
      setMessages([])
    }
  }, [currentId])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 创建新对话
  const createConversation = async () => {
    try {
      const personaId = activePersona?.id ?? null
      const conv = await apiPost<Conversation>('/chat/conversations', {
        title: `对话 ${new Date().toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`,
        persona_id: personaId,
      })
      setConversations(prev => [conv, ...prev])
      setCurrentId(conv.id)
    } catch (e: any) {
      setError(e?.message || '创建对话失败')
    }
  }

  // 发送消息(SSE 流式)
  const sendMessage = async () => {
    const content = input.trim()
    if (!content || streaming || currentId === null) return

    setInput('')
    setStreaming(true)
    setError('')

    // 乐观添加用户消息 + 空的助手消息
    const tempUserId = `temp-user-${Date.now()}`
    const tempAssistantId = `temp-assistant-${Date.now()}`
    const now = new Date().toISOString()
    setMessages(prev => [
      ...prev,
      { id: tempUserId as any, conversation_id: currentId, role: 'user', content, created_at: now } as Message,
      { id: tempAssistantId as any, conversation_id: currentId, role: 'assistant', content: '', created_at: now } as Message,
    ])

    try {
      await apiStream(
        `/chat/conversations/${currentId}/messages`,
        { content },
        (chunk: string) => {
          // 尝试解析为 JSON 事件
          try {
            const evt = JSON.parse(chunk)
            if (evt.type === 'token' && evt.content) {
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: m.content + evt.content } : m
              ))
            } else if (evt.type === 'error') {
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: `⚠️ ${evt.error || '生成失败'}` } : m
              ))
            } else if (evt.type === 'tool_call') {
              // v2.2.0: 工具调用事件 — 以 Markdown 行内联到助手气泡
              const argsJson = (() => {
                try { return JSON.stringify(evt.arguments, null, 2) } catch { return String(evt.arguments ?? '') }
              })()
              const block = `\n\n🔧 **调用工具** \`${evt.name}\`\n\`\`\`json\n${argsJson}\n\`\`\`\n`
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: m.content + block } : m
              ))
            } else if (evt.type === 'tool_result') {
              // v2.2.0: 工具结果事件
              const icon = evt.success === false ? '❌' : '✅'
              const block = `\n${icon} \`${evt.name}\` 结果:\n\`\`\`\n${evt.result ?? ''}\n\`\`\`\n`
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: m.content + block } : m
              ))
            } else if (evt.type === 'rag_context') {
              // v2.2.0: 知识库上下文事件 (Phase 4 发出,前端先占位渲染)
              const srcList = Array.isArray(evt.sources)
                ? evt.sources.map((s: any) => `- ${s.title ?? ''}(score: ${s.score ?? '-'})`).join('\n')
                : ''
              const block = `\n📚 **知识库引用**\n${srcList}\n`
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: m.content + block } : m
              ))
            } else if (evt.type === 'approval_required') {
              // v2.2.0: 需用户授权的操作 (Phase 5 Browser/CU)
              const block = `\n⚠️ **需授权操作** \`${evt.tool}\` — 请在确认后继续\n`
              setMessages(prev => prev.map(m =>
                String(m.id) === tempAssistantId ? { ...m, content: m.content + block } : m
              ))
            }
            // type === 'done' 时无需额外操作
          } catch {
            // 非 JSON,当作纯文本追加
            setMessages(prev => prev.map(m =>
              String(m.id) === tempAssistantId ? { ...m, content: m.content + chunk } : m
            ))
          }
        },
      )
    } catch (e: any) {
      setMessages(prev => prev.map(m =>
        String(m.id) === tempAssistantId ? { ...m, content: `⚠️ ${e?.message || '连接失败'}` } : m
      ))
    } finally {
      setStreaming(false)
    }
  }

  // 键盘事件:Enter 发送,Shift+Enter 换行
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // 当前对话对象
  const currentConv = conversations.find(c => c.id === currentId)

  return (
    <div className="flex h-full w-full overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      {/* ===== 左侧:对话列表 ===== */}
      <div
        className="flex flex-col shrink-0"
        style={{
          width: '260px',
          background: 'var(--glass-bg)',
          backdropFilter: `blur(var(--glass-blur))`,
          borderRight: '1px solid var(--border)',
        }}
      >
        {/* 新建对话按钮 */}
        <div style={{ padding: 'var(--spacing-md)' }}>
          <button
            onClick={createConversation}
            className="w-full flex items-center justify-center gap-2 transition-all"
            style={{
              padding: '10px var(--spacing-md)',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 'var(--font-sm)',
              fontWeight: 600,
              boxShadow: 'var(--shadow-sm)',
              border: 'none',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent)')}
          >
            <span style={{ fontSize: '18px' }}>✨</span>
            新建对话
          </button>
        </div>

        {/* 对话列表 */}
        <div className="flex-1 overflow-y-auto" style={{ padding: '0 var(--spacing-sm)' }}>
          {conversations.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center"
              style={{ padding: 'var(--spacing-2xl) var(--spacing-md)', color: 'var(--text-secondary)', textAlign: 'center' }}
            >
              <span style={{ fontSize: '40px', marginBottom: 'var(--spacing-sm)' }}>💬</span>
              <p style={{ fontSize: 'var(--font-sm)' }}>还没有对话</p>
              <p style={{ fontSize: 'var(--font-xs)', marginTop: '4px' }}>点击上方按钮开始</p>
            </div>
          ) : (
            conversations.map(conv => (
              <button
                key={conv.id}
                onClick={() => setCurrentId(conv.id)}
                className="w-full text-left transition-all"
                style={{
                  padding: 'var(--spacing-sm) var(--spacing-md)',
                  marginBottom: '4px',
                  borderRadius: 'var(--radius-md)',
                  background: conv.id === currentId ? 'var(--bg-secondary)' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  if (conv.id !== currentId) e.currentTarget.style.background = 'var(--bg-secondary)'
                }}
                onMouseLeave={(e) => {
                  if (conv.id !== currentId) e.currentTarget.style.background = 'transparent'
                }}
              >
                <div
                  style={{
                    fontSize: 'var(--font-sm)',
                    color: 'var(--text-primary)',
                    fontWeight: conv.id === currentId ? 600 : 400,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {conv.title || '未命名对话'}
                </div>
                <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  {formatTime(conv.created_at)}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* ===== 右侧:消息区域 ===== */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* 顶部栏:角色名称 + 对话标题 */}
        <div
          className="flex items-center gap-3 shrink-0"
          style={{
            padding: 'var(--spacing-md) var(--spacing-lg)',
            background: 'var(--glass-bg)',
            backdropFilter: `blur(var(--glass-blur))`,
            borderBottom: '1px solid var(--border)',
          }}
        >
          {activePersona && (
            <div
              className="flex items-center justify-center shrink-0"
              style={{
                width: '36px',
                height: '36px',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-secondary)',
                fontSize: '20px',
              }}
            >
              {getPersonaAvatar(activePersona)}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div style={{ fontSize: 'var(--font-base)', fontWeight: 600, color: 'var(--text-primary)' }}>
              {currentConv?.title || '选择或创建一个对话'}
            </div>
            <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)' }}>
              {activePersona ? `角色: ${activePersona.name}` : '未选择角色'}
            </div>
          </div>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto" style={{ padding: 'var(--spacing-lg)' }}>
          {currentId === null ? (
            // 空状态
            <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--text-secondary)' }}>
              <span style={{ fontSize: '64px', marginBottom: 'var(--spacing-lg)' }}>🌟</span>
              <h2 style={{ fontSize: 'var(--font-xl)', color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                欢迎来到盘古星云
              </h2>
              <p style={{ fontSize: 'var(--font-base)', marginBottom: 'var(--spacing-lg)' }}>
                选择左侧对话或创建新对话开始聊天
              </p>
              <div className="flex gap-3">
                <button
                  onClick={createConversation}
                  className="transition-all"
                  style={{
                    padding: '10px 20px',
                    borderRadius: 'var(--radius-lg)',
                    background: 'var(--accent)',
                    color: '#fff',
                    fontSize: 'var(--font-sm)',
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    boxShadow: 'var(--shadow-md)',
                  }}
                >
                  ✨ 开始新对话
                </button>
              </div>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center h-full">
              <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-base)' }}>加载中...</span>
            </div>
          ) : (
            <div className="flex flex-col gap-4 max-w-3xl mx-auto">
              {messages.map(msg => (
                <MessageBubble key={msg.id} msg={msg} streaming={streaming && msg.id === messages[messages.length - 1]?.id} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* 输入区域 */}
        {currentId !== null && (
          <div
            className="shrink-0"
            style={{
              padding: 'var(--spacing-md) var(--spacing-lg)',
              background: 'var(--glass-bg)',
              backdropFilter: `blur(var(--glass-blur))`,
              borderTop: '1px solid var(--border)',
            }}
          >
            {error && (
              <div style={{ fontSize: 'var(--font-xs)', color: '#e53e3e', marginBottom: 'var(--spacing-xs)' }}>
                {error}
              </div>
            )}
            <div
              className="flex items-end gap-2"
              style={{
                background: 'var(--bg-card)',
                borderRadius: 'var(--radius-xl)',
                padding: 'var(--spacing-sm) var(--spacing-md)',
                border: '1px solid var(--border)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onInput={(e) => setInput((e.target as HTMLTextAreaElement).value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                rows={1}
                disabled={streaming}
                className="flex-1 resize-none outline-none"
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: 'var(--text-primary)',
                  fontSize: 'var(--font-sm)',
                  lineHeight: '1.6',
                  maxHeight: '120px',
                  padding: '6px 0',
                }}
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || streaming}
                className="shrink-0 transition-all"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: 'var(--radius-full)',
                  background: input.trim() && !streaming ? 'var(--accent)' : 'var(--bg-secondary)',
                  border: 'none',
                  cursor: input.trim() && !streaming ? 'pointer' : 'default',
                  fontSize: '18px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {streaming ? '⏳' : '➤'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ===== 消息气泡子组件 =====

function MessageBubble({ msg, streaming }: { msg: Message; streaming: boolean }) {
  const isUser = msg.role === 'user'
  const isEmpty = !msg.content && !isUser

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[80%]"
        style={{
          padding: 'var(--spacing-sm) var(--spacing-md)',
          borderRadius: isUser ? 'var(--radius-xl) var(--radius-xs) var(--radius-xl) var(--radius-xl)' : 'var(--radius-xs) var(--radius-xl) var(--radius-xl) var(--radius-xl)',
          background: isUser ? 'var(--accent)' : 'var(--bg-card)',
          color: isUser ? '#fff' : 'var(--text-primary)',
          boxShadow: 'var(--shadow-sm)',
          border: isUser ? 'none' : '1px solid var(--border)',
        }}
      >
        {isEmpty ? (
          <span className="inline-flex gap-1" style={{ fontSize: 'var(--font-base)' }}>
            <span className="md-dot" style={{ animation: 'md-bounce 1s infinite' }}>●</span>
            <span className="md-dot" style={{ animation: 'md-bounce 1s infinite 0.2s' }}>●</span>
            <span className="md-dot" style={{ animation: 'md-bounce 1s infinite 0.4s' }}>●</span>
          </span>
        ) : isUser ? (
          <div style={{ fontSize: 'var(--font-sm)', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
            {msg.content}
          </div>
        ) : (
          <div
            className="md-body"
            style={{ fontSize: 'var(--font-sm)', lineHeight: '1.7' }}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
          />
        )}
        {streaming && !isEmpty && !isUser && (
          <span style={{ display: 'inline-block', width: '8px', height: '14px', background: 'var(--accent)', marginLeft: '2px', animation: 'md-blink 1s infinite', borderRadius: '1px' }} />
        )}
      </div>
    </div>
  )
}
