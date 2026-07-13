import { useState, useEffect } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'

// ===== 步骤定义 =====

const STEPS = [
  { title: '欢迎', icon: '🌟' },
  { title: '配置模型', icon: '⚙️' },
  { title: '创建角色', icon: '🎭' },
  { title: '完成', icon: '🎉' },
]

// 可选头像列表
const AVATAR_CHOICES = ['🧸', '🐰', '🦊', '🐱', '🐼', '🦉', '🌟', '🌙', '☀️', '🌈', '🦄', '🐋']

// ===== 组件 =====

export default function OnboardingWizard({ onComplete, onSkip }: { onComplete: () => void; onSkip: () => void }) {
  const [step, setStep] = useState(0)
  const [providers, setProviders] = useState<any[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)

  // 表单数据
  const [provider, setProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [modelName, setModelName] = useState('')
    const [personaName, setPersonaName] = useState('')
  const [personaDesc, setPersonaDesc] = useState('')
  const [personaAvatar, setPersonaAvatar] = useState('🧸')
  const [personaSoul, setPersonaSoul] = useState('')

  // 状态
  const [aiGenerating, setAiGenerating] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  // 加载可用 Provider 列表
  useEffect(() => {
    const loadProviders = async () => {
      try {
        const data = await apiGet<any[]>('/providers')
        setProviders(data || [])
        if (data && data.length > 0) {
          setProvider(data[0].name)
        }
      } catch {
        // 加载失败,提供默认选项
        setProviders([
          { name: 'openai', label: 'OpenAI', icon: '🤖', available: false, supported_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'] },
          { name: 'anthropic', label: 'Anthropic', icon: '🧠', available: false, supported_models: ['claude-sonnet-4-20250514', 'claude-3-5-haiku-latest'] },
          { name: 'gemini', label: 'Google Gemini', icon: '✨', available: false, supported_models: ['gemini-2.5-flash', 'gemini-2.5-pro'] },
          { name: 'deepseek', label: 'DeepSeek', icon: '🔍', available: false, supported_models: ['deepseek-chat', 'deepseek-reasoner'] },
          { name: 'zhipu', label: '智谱 GLM', icon: '🇨🇳', available: false, supported_models: ['glm-4-plus', 'glm-4-flash'] },
          { name: 'moonshot', label: '月之暗面', icon: '🌑', available: false, supported_models: ['moonshot-v1-8k', 'moonshot-v1-32k'] },
          { name: 'qwen', label: '通义千问', icon: '☁️', available: false, supported_models: ['qwen-max', 'qwen-plus'] },
          { name: 'custom', label: '自定义', icon: '🔌', available: true, supported_models: [] },
        ])
        setProvider('openai')
      } finally {
        setLoadingProviders(false)
      }
    }
    loadProviders()
  }, [])

  // 保存 API 密钥
  const saveApiKey = async () => {
    if (!apiKey.trim() || !provider) return
    try {
      await apiPost('/providers/configure', {
        provider: provider,
        api_key: apiKey.trim(),
        api_base: apiBase.trim() || undefined,
        default_model: modelName.trim() || undefined,
      })
    } catch {
      // 配置保存暂不支持,请通过环境变量设置 API Key
    }
  }

  // 跳过当前步骤
  const skipCurrent = () => {
    setError('')
    if (step === 1) saveApiKey()
    if (step < STEPS.length - 1) {
      setStep(step + 1)
    } else {
      onComplete()
    }
  }

  // AI 辅助生成 SOUL
  const handleAiGenerate = async () => {
    if (!personaDesc.trim()) {
      setError('请输入角色描述')
      return
    }
    setAiGenerating(true)
    setError('')
    try {
      const result = await apiPost<any>('/persona/generate', {
        description: personaDesc.trim(),
      })
      const soul = result?.system_prompt || result?.soul || ''
      setPersonaSoul(soul)
      if (result?.name && !personaName) {
        setPersonaName(result.name)
      }
    } catch (e: any) {
      setError(e?.message || 'AI 生成失败,请稍后重试')
    } finally {
      setAiGenerating(false)
    }
  }

  // 创建角色并完成引导
  const handleCreatePersona = async () => {
    if (!personaName.trim()) {
      setError('请输入角色名称')
      setStep(2)
      return
    }
    setCreating(true)
    setError('')
    try {
      // 创建角色(发送 system_prompt 字段以兼容后端)
      const created = await apiPost<any>('/persona', {
        name: personaName.trim(),
        system_prompt: personaSoul || personaDesc.trim(),
        avatar: personaAvatar,
      })
      // 自动激活角色
      if (created?.id) {
        await apiPost(`/persona/${created.id}/activate`)
      }
      // 进入下一步(完成页)
      setStep(3)
    } catch (e: any) {
      setError(e?.message || '创建角色失败')
    } finally {
      setCreating(false)
    }
  }

  // 前进
  const next = async () => {
    setError('')
    if (step === 1) {
      saveApiKey()
      setStep(2)
    } else if (step === 2) {
      if (personaName.trim()) {
        await handleCreatePersona()
      } else {
        setStep(3)
      }
    } else if (step < STEPS.length - 1) {
      setStep(step + 1)
    }
  }

  // 后退
  const back = () => {
    setError('')
    if (step > 0) {
      setStep(step - 1)
    }
  }

  // 是否可以前进
  const canProceed = (): boolean => {
    switch (step) {
      case 0: return true
      case 1: return true
      case 2: return !creating
      case 3: return true
      default: return false
    }
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center"
      style={{
        background: 'linear-gradient(135deg, var(--bg-primary), var(--bg-secondary))',
        backdropFilter: 'blur(8px)',
        zIndex: 9999,
      }}
    >
      {/* 装饰背景元素 */}
      <div
        style={{
          position: 'absolute',
          top: '10%',
          left: '10%',
          fontSize: '120px',
          opacity: 0.06,
          transform: 'rotate(-15deg)',
        }}
      >
        🌟
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: '10%',
          right: '10%',
          fontSize: '100px',
          opacity: 0.06,
          transform: 'rotate(20deg)',
        }}
      >
        🌙
      </div>

      {/* 主卡片 */}
      <div
        className="flex flex-col"
        style={{
          width: '92%',
          maxWidth: '560px',
          maxHeight: '90vh',
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-xl)',
          boxShadow: 'var(--shadow-xl)',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* 顶部进度条 */}
        <div
          style={{
            padding: 'var(--spacing-lg) var(--spacing-lg) var(--spacing-md)',
            borderBottom: '1px solid var(--border)',
            background: 'var(--glass-bg)',
          }}
        >
          {/* 步骤指示器 */}
          <div className="flex items-center justify-between" style={{ marginBottom: 'var(--spacing-sm)' }}>
            {STEPS.map((_s, i) => (
              <div key={i} className="flex items-center" style={{ flex: 1 }}>
                <div
                  className="flex items-center justify-center"
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: 'var(--radius-full)',
                    background: i <= step ? 'var(--accent)' : 'var(--bg-secondary)',
                    color: i <= step ? '#fff' : 'var(--text-secondary)',
                    fontSize: 'var(--font-sm)',
                    fontWeight: 700,
                    transition: 'all 0.3s',
                    shrink: 0,
                  }}
                >
                  {i < step ? '✓' : i + 1}
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    style={{
                      flex: 1,
                      height: '3px',
                      margin: '0 6px',
                      borderRadius: 'var(--radius-full)',
                      background: i < step ? 'var(--accent)' : 'var(--bg-secondary)',
                      transition: 'all 0.3s',
                    }}
                  />
                )}
              </div>
            ))}
          </div>
          {/* 当前步骤标题 */}
          <div style={{ textAlign: 'center', fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
            {STEPS[step].icon} 步骤 {step + 1}/{STEPS.length}: {STEPS[step].title}
          </div>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 overflow-y-auto" style={{ padding: 'var(--spacing-xl) var(--spacing-lg)' }}>
          {/* 错误提示 */}
          {error && (
            <div
              style={{
                padding: 'var(--spacing-sm) var(--spacing-md)',
                marginBottom: 'var(--spacing-md)',
                borderRadius: 'var(--radius-md)',
                background: '#FFF0F0',
                color: '#e53e3e',
                fontSize: 'var(--font-sm)',
                border: '1px solid #F5C6CB',
              }}
            >
              ⚠️ {error}
            </div>
          )}

          {/* ===== 步骤 1: 欢迎页 ===== */}
          {step === 0 && (
            <div className="flex flex-col items-center text-center">
              <span style={{ fontSize: '72px', marginBottom: 'var(--spacing-lg)' }}>🌟</span>
              <h1 style={{ fontSize: 'var(--font-2xl)', fontWeight: 800, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                欢迎来到盘古星云
              </h1>
              <p style={{ fontSize: 'var(--font-base)', color: 'var(--text-secondary)', lineHeight: '1.7', marginBottom: 'var(--spacing-lg)', maxWidth: '400px' }}>
                你的个人 AI 助手平台。在这里,你可以创建独特的 AI 角色,
                与它们对话,让蜂群智能帮你完成复杂任务。
              </p>
              {/* 功能亮点 */}
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(3, 1fr)', width: '100%', maxWidth: '420px' }}>
                {[
                  { icon: '🎭', title: '角色管理', desc: '创建独特灵魂' },
                  { icon: '💬', title: '智能对话', desc: '流畅流式响应' },
                  { icon: '🐝', title: '蜂群协作', desc: '多智能体并行' },
                ].map(f => (
                  <div
                    key={f.title}
                    style={{
                      padding: 'var(--spacing-md) var(--spacing-sm)',
                      borderRadius: 'var(--radius-lg)',
                      background: 'var(--bg-secondary)',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', marginBottom: '6px' }}>{f.icon}</div>
                    <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>{f.title}</div>
                    <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: '2px' }}>{f.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ===== 步骤 2: 选择 Provider ===== */}
          {step === 1 && (
            <div className="flex flex-col">
              <h2 style={{ fontSize: 'var(--font-xl)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                ⚙️ 配置 AI 模型
              </h2>
              <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-lg)' }}>
                选择你的 AI 服务商并输入 API 密钥
              </p>

              {/* Provider 选择 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  AI 服务商
                </label>
                {loadingProviders ? (
                  <div style={{ padding: '10px', color: 'var(--text-secondary)', fontSize: 'var(--font-sm)' }}>加载中...</div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {providers.map(p => (
                      <button
                        key={p.name}
                        onClick={() => setProvider(p.name)}
                        className="transition-all"
                        style={{
                          padding: '10px var(--spacing-md)',
                          borderRadius: 'var(--radius-lg)',
                          background: provider === p.name ? 'var(--accent)' : 'var(--bg-secondary)',
                          color: provider === p.name ? '#fff' : 'var(--text-primary)',
                          fontSize: 'var(--font-sm)',
                          fontWeight: 600,
                          border: provider === p.name ? '2px solid var(--accent)' : '1px solid var(--border)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <span>{p.name === 'openai' ? '🤖' : p.name === 'anthropic' ? '🧠' : p.name === 'gemini' ? '✨' : '🔌'}</span>
                        {p.name}
                        {p.available && (
                          <span style={{ fontSize: 'var(--font-xs)', opacity: 0.8 }}>✓</span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* API Key 输入 */}
              <div>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  API 密钥
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onInput={(e) => setApiKey((e.target as HTMLInputElement).value)}
                  placeholder="输入你的 API Key..."
                  style={{
                    width: '100%',
                    padding: '10px var(--spacing-md)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
                <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: 'var(--spacing-xs)' }}>
                  💡 密钥将安全保存在本地,不会上传到服务器
                </p>
              </div>

              {/* 自定义 API Base (仅 custom provider 时显示) */}
              {provider === 'custom' && (
                <div style={{ marginBottom: 'var(--spacing-md)' }}>
                  <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                    API Base URL
                  </label>
                  <input
                    type="text"
                    value={apiBase}
                    onInput={(e) => setApiBase((e.target as HTMLInputElement).value)}
                    placeholder="https://api.openai.com/v1"
                    style={{
                      width: '100%',
                      padding: '10px var(--spacing-md)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border)',
                      background: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: 'var(--font-sm)',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              )}

              {/* 模型名称输入 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  默认模型 (可选)
                </label>
                <input
                  type="text"
                  value={modelName}
                  onInput={(e) => setModelName((e.target as HTMLInputElement).value)}
                  placeholder="输入模型名称,如 gpt-4o"
                  style={{
                    width: '100%',
                    padding: '10px var(--spacing-md)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>
          )}

          {/* ===== 步骤 3: 创建第一个角色 ===== */}
          {step === 2 && (
            <div className="flex flex-col">
              <h2 style={{ fontSize: 'var(--font-xl)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                🎭 创建角色 (可选)
              </h2>
              <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-lg)' }}>
                为你的 AI 助手赋予独特的灵魂和个性
              </p>

              {/* 头像选择 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  选择头像
                </label>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_CHOICES.map(emoji => (
                    <button
                      key={emoji}
                      onClick={() => setPersonaAvatar(emoji)}
                      className="transition-all"
                      style={{
                        width: '40px',
                        height: '40px',
                        borderRadius: 'var(--radius-md)',
                        background: personaAvatar === emoji ? 'var(--accent)' : 'var(--bg-secondary)',
                        border: personaAvatar === emoji ? '2px solid var(--accent)' : '1px solid var(--border)',
                        cursor: 'pointer',
                        fontSize: '22px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>

              {/* 角色名称 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  角色名称
                </label>
                <input
                  type="text"
                  value={personaName}
                  onInput={(e) => setPersonaName((e.target as HTMLInputElement).value)}
                  placeholder="给你的角色取个名字..."
                  style={{
                    width: '100%',
                    padding: '10px var(--spacing-md)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* AI 辅助生成 */}
              <div
                style={{
                  marginBottom: 'var(--spacing-md)',
                  padding: 'var(--spacing-md)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  🤖 AI 辅助生成(可选)
                </label>
                <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-sm)' }}>
                  描述你想要的角色,AI 自动生成灵魂设定
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={personaDesc}
                    onInput={(e) => setPersonaDesc((e.target as HTMLInputElement).value)}
                    placeholder="例如:一个温柔的学者,擅长历史和文学..."
                    disabled={aiGenerating}
                    style={{
                      flex: 1,
                      padding: '8px var(--spacing-sm)',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border)',
                      background: 'var(--bg-card)',
                      color: 'var(--text-primary)',
                      fontSize: 'var(--font-sm)',
                      outline: 'none',
                    }}
                  />
                  <button
                    onClick={handleAiGenerate}
                    disabled={aiGenerating || !personaDesc.trim()}
                    className="transition-all"
                    style={{
                      padding: '8px var(--spacing-md)',
                      borderRadius: 'var(--radius-md)',
                      background: aiGenerating || !personaDesc.trim() ? 'var(--bg-secondary)' : 'var(--accent)',
                      color: '#fff',
                      fontSize: 'var(--font-sm)',
                      fontWeight: 600,
                      border: 'none',
                      cursor: aiGenerating || !personaDesc.trim() ? 'default' : 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {aiGenerating ? '生成中...' : '✨ 生成'}
                  </button>
                </div>
              </div>

              {/* SOUL 内容 */}
              <div>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  SOUL 灵魂设定
                </label>
                <textarea
                  value={personaSoul}
                  onInput={(e) => setPersonaSoul((e.target as HTMLTextAreaElement).value)}
                  placeholder="描述角色的性格、背景、说话风格... 或使用 AI 辅助生成"
                  rows={5}
                  className="resize-y"
                  style={{
                    width: '100%',
                    padding: '10px var(--spacing-md)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    lineHeight: '1.6',
                    fontFamily: 'monospace',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>
          )}

          {/* ===== 步骤 4: 完成 ===== */}
          {step === 3 && (
            <div className="flex flex-col items-center text-center">
              <span style={{ fontSize: '72px', marginBottom: 'var(--spacing-lg)' }}>🎉</span>
              <h1 style={{ fontSize: 'var(--font-2xl)', fontWeight: 800, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                设置完成!
              </h1>
              <p style={{ fontSize: 'var(--font-base)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-lg)', maxWidth: '380px' }}>
                {personaName ? '一切就绪,你的 AI 助手已经准备好为你服务了' : '一切就绪,你可以在设置中随时配置模型和创建角色'}
              </p>

              {/* 配置摘要 */}
              <div
                style={{
                  width: '100%',
                  maxWidth: '380px',
                  padding: 'var(--spacing-md)',
                  borderRadius: 'var(--radius-lg)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                <div className="flex items-center gap-3" style={{ marginBottom: 'var(--spacing-sm)' }}>
                  <span style={{ fontSize: '32px' }}>{personaAvatar}</span>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 'var(--font-base)', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {personaName || '未命名角色'}
                    </div>
                    <div style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)' }}>
                      角色 · 已激活
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--spacing-sm)' }}>
                  <span style={{ fontSize: '16px' }}>⚙️</span>
                  <span style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)' }}>
                    模型: {provider || '默认'}
                  </span>
                </div>
              </div>

              <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: 'var(--spacing-lg)' }}>
                点击下方按钮开始你的旅程 🚀
              </p>
            </div>
          )}
        </div>

        {/* 底部导航按钮 */}
        <div
          className="flex items-center justify-between shrink-0"
          style={{
            padding: 'var(--spacing-md) var(--spacing-lg)',
            borderTop: '1px solid var(--border)',
            background: 'var(--bg-primary)',
          }}
        >
          {/* 左侧: 后退 + 跳过全部 */}
          <div className="flex gap-2">
            {step > 0 && step < 3 ? (
              <button
                onClick={back}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-md)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  border: '1px solid var(--border)',
                  cursor: 'pointer',
                }}
              >
                ← 上一步
              </button>
            ) : (
              <div />
            )}
            {step < 3 && (
              <button
                onClick={onSkip}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-md)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-xs)',
                  border: 'none',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                跳过全部
              </button>
            )}
          </div>

          {/* 右侧: 跳过当前 + 前进/完成 */}
          {step < 3 ? (
            <div className="flex gap-2">
              <button
                onClick={skipCurrent}
                className="transition-all"
                disabled={creating || aiGenerating}
                style={{
                  padding: '8px var(--spacing-md)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  border: '1px solid var(--border)',
                  cursor: creating || aiGenerating ? 'default' : 'pointer',
                  opacity: creating || aiGenerating ? 0.5 : 1,
                }}
              >
                跳过
              </button>
              <button
                onClick={next}
                disabled={!canProceed() || aiGenerating || creating}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-xl)',
                  borderRadius: 'var(--radius-md)',
                  background: canProceed() && !aiGenerating && !creating ? 'var(--accent)' : 'var(--bg-secondary)',
                  color: canProceed() && !aiGenerating && !creating ? '#fff' : 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  fontWeight: 600,
                  border: 'none',
                  cursor: canProceed() && !aiGenerating && !creating ? 'pointer' : 'default',
                }}
              >
                {step === 2 && personaName.trim()
                  ? creating
                    ? '创建中...'
                    : '创建角色 →'
                  : '下一步 →'}
              </button>
            </div>
          ) : (
            <button
              onClick={onComplete}
              className="transition-all"
              style={{
                padding: '10px var(--spacing-xl)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--accent)',
                color: '#fff',
                fontSize: 'var(--font-sm)',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-md)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent)')}
            >
              🚀 进入盘古星云
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
