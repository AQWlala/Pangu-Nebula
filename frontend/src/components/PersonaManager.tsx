import { useState, useEffect } from 'preact/hooks'
import { apiGet, apiPost, apiPut, apiDelete } from '../lib/api'
import type { Persona } from '../lib/types'

// ===== 工具函数 =====

/** 获取角色 SOUL 内容(兼容 soul / system_prompt 两种字段名) */
function getPersonaSoul(p: any): string {
  return p?.soul ?? p?.system_prompt ?? ''
}

/** 获取角色头像 emoji,缺省返回友好默认值 */
function getPersonaAvatar(p: any): string {
  return p?.avatar || '🧸'
}

/** 截取摘要 */
function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '...'
}

/** 可选头像列表 */
const AVATAR_CHOICES = ['🧸', '🐰', '🦊', '🐱', '🐼', '🦉', '🌟', '🌙', '☀️', '🌈', '🦄', '🐋']

/** 关系类型元数据 (颜色/中文标签) */
const RELATION_META: Record<string, { label: string; color: string; emoji: string }> = {
  complement: { label: '互补', color: '#3182ce', emoji: '🧩' },
  assist: { label: '协助', color: '#38a169', emoji: '🤝' },
  delegate: { label: '委派', color: '#805ad5', emoji: '📤' },
}

// ===== 表单数据类型 =====

interface FormData {
  id: number | null
  name: string
  soul: string
  avatar: string
  role: string
  goal: string
  backstory: string
}

const EMPTY_FORM: FormData = {
  id: null,
  name: '',
  soul: '',
  avatar: '🧸',
  role: '',
  goal: '',
  backstory: '',
}

// ===== 组件 =====

export default function PersonaManager() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormData>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [aiDesc, setAiDesc] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Persona | null>(null)
  const [error, setError] = useState('')

  // v2.3.0 A3: 关联角色管理状态
  const [relationsTarget, setRelationsTarget] = useState<Persona | null>(null)
  const [relations, setRelations] = useState<any[]>([])
  const [candidates, setCandidates] = useState<any[]>([])
  const [loadingRelations, setLoadingRelations] = useState(false)
  const [newRelationTargetId, setNewRelationTargetId] = useState<number | null>(null)
  const [newRelationType, setNewRelationType] = useState<string>('complement')
  const [newRelationStrength, setNewRelationStrength] = useState<number>(0.5)

  // 加载角色列表 + 激活角色
  const loadData = async () => {
    setLoading(true)
    try {
      const [list, active] = await Promise.all([
        apiGet<any[]>('/persona'),
        apiGet<any>('/persona/active').catch(() => null),
      ])
      setPersonas(list || [])
      setActiveId(active?.id ?? null)
    } catch (e: any) {
      setError(e?.message || '加载角色失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // 打开新建表单
  const openCreate = () => {
    setForm(EMPTY_FORM)
    setShowForm(true)
    setError('')
  }

  // 打开编辑表单
  const openEdit = (p: Persona) => {
    setForm({
      // v2.3.1 P1-11: Persona 接口已扩展 id/role/goal/backstory, 无需 as any
      id: p.id,
      name: p.name,
      soul: getPersonaSoul(p),
      avatar: getPersonaAvatar(p),
      role: p.role || '',
      goal: p.goal || '',
      backstory: p.backstory || '',
    })
    setShowForm(true)
    setError('')
  }

  // 保存(新建或编辑)
  const handleSave = async () => {
    if (!form.name.trim()) {
      setError('请输入角色名称')
      return
    }
    setSaving(true)
    setError('')
    try {
      // 发送 system_prompt 字段以兼容后端,同时携带三元组
      const body: any = {
        name: form.name.trim(),
        system_prompt: form.soul,
        avatar: form.avatar,
        role: form.role.trim() || null,
        goal: form.goal.trim() || null,
        backstory: form.backstory.trim() || null,
      }
      if (form.id !== null) {
        await apiPut(`/persona/${form.id}`, body)
      } else {
        const created = await apiPost<any>('/persona', body)
        // 新建后自动激活
        if (created?.id) {
          await apiPost(`/persona/${created.id}/activate`)
        }
      }
      setShowForm(false)
      await loadData()
    } catch (e: any) {
      setError(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 激活角色
  const handleActivate = async (p: Persona) => {
    const pid = p.id
    if (pid === activeId) return
    try {
      await apiPost(`/persona/${pid}/activate`)
      setActiveId(pid)
    } catch (e: any) {
      setError(e?.message || '激活失败')
    }
  }

  // AI 辅助生成 SOUL
  const handleAiGenerate = async () => {
    if (!aiDesc.trim()) {
      setError('请输入角色描述')
      return
    }
    setAiLoading(true)
    setError('')
    try {
      // 后端端点为 /persona/generate
      const result = await apiPost<any>('/persona/generate', {
        description: aiDesc.trim(),
      })
      const soul = result?.system_prompt || result?.soul || ''
      const name = result?.name || form.name
      setForm(prev => ({ ...prev, soul, name: prev.name || name }))
      setAiDesc('')
    } catch (e: any) {
      setError(e?.message || 'AI 生成失败')
    } finally {
      setAiLoading(false)
    }
  }

  // 删除角色
  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await apiDelete(`/persona/${deleteTarget.id}`)
      setDeleteTarget(null)
      await loadData()
    } catch (e: any) {
      setError(e?.message || '删除失败')
    }
  }

  // ===== 关联角色管理 =====

  const loadRelationsData = async (pid: number) => {
    setLoadingRelations(true)
    try {
      const [rels, cands] = await Promise.all([
        apiGet<any[]>(`/persona/${pid}/relations`).catch(() => []),
        apiGet<any[]>(`/persona/${pid}/candidates?limit=10`).catch(() => []),
      ])
      setRelations(rels || [])
      setCandidates(cands || [])
    } catch (e: any) {
      setError(e?.message || '加载关联失败')
    } finally {
      setLoadingRelations(false)
    }
  }

  const openRelations = (p: Persona) => {
    setRelationsTarget(p)
    setNewRelationTargetId(null)
    setNewRelationType('complement')
    setNewRelationStrength(0.5)
    setError('')
    loadRelationsData(p.id)
  }

  const handleCreateRelation = async (targetId: number, relationType: string, strength: number) => {
    if (!relationsTarget) return
    const pid = relationsTarget.id
    try {
      await apiPost(`/persona/${pid}/relations`, {
        target_id: targetId,
        relation_type: relationType,
        strength,
      })
      setNewRelationTargetId(null)
      await loadRelationsData(pid)
    } catch (e: any) {
      setError(e?.message || '创建关联失败')
    }
  }

  const handleDeleteRelation = async (relationId: number) => {
    if (!relationsTarget) return
    const pid = relationsTarget.id
    try {
      await apiDelete(`/persona/relations/${relationId}`)
      await loadRelationsData(pid)
    } catch (e: any) {
      setError(e?.message || '删除关联失败')
    }
  }

  return (
    <div className="h-full w-full overflow-y-auto" style={{ background: 'var(--bg-primary)', padding: 'var(--spacing-lg)' }}>
      {/* 顶部标题栏 */}
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div>
          <h2 style={{ fontSize: 'var(--font-xl)', fontWeight: 700, color: 'var(--text-primary)' }}>
            🎭 角色管理
          </h2>
          <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', marginTop: '4px' }}>
            管理你的 AI 角色,每个角色有独特的灵魂设定
          </p>
        </div>
        <button
          onClick={openCreate}
          className="transition-all"
          style={{
            padding: '10px var(--spacing-lg)',
            borderRadius: 'var(--radius-lg)',
            background: 'var(--accent)',
            color: '#fff',
            fontSize: 'var(--font-sm)',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            boxShadow: 'var(--shadow-md)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--accent)')}
        >
          <span style={{ fontSize: '18px' }}>＋</span>
          新建角色
        </button>
      </div>

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

      {/* 加载状态 */}
      {loading ? (
        <div className="flex items-center justify-center" style={{ padding: 'var(--spacing-3xl)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-base)' }}>加载中...</span>
        </div>
      ) : personas.length === 0 ? (
        // 空状态
        <div
          className="flex flex-col items-center justify-center"
          style={{ padding: 'var(--spacing-3xl)', color: 'var(--text-secondary)' }}
        >
          <span style={{ fontSize: '64px', marginBottom: 'var(--spacing-md)' }}>🎭</span>
          <h3 style={{ fontSize: 'var(--font-lg)', color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
            还没有角色
          </h3>
          <p style={{ fontSize: 'var(--font-sm)', marginBottom: 'var(--spacing-lg)' }}>
            创建你的第一个 AI 角色,赋予它独特的灵魂
          </p>
          <button
            onClick={openCreate}
            className="transition-all"
            style={{
              padding: '10px 24px',
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
            ✨ 创建角色
          </button>
        </div>
      ) : (
        // 角色卡片网格
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {personas.map(p => {
            const pid = p.id
            const isActive = pid === activeId
            return (
              <div
                key={pid}
                className="transition-all"
                style={{
                  background: 'var(--bg-card)',
                  borderRadius: 'var(--radius-xl)',
                  padding: 'var(--spacing-lg)',
                  border: isActive ? '2px solid var(--accent)' : '1px solid var(--border)',
                  boxShadow: isActive ? 'var(--shadow-lg)' : 'var(--shadow-sm)',
                  cursor: 'pointer',
                  position: 'relative',
                }}
                onClick={() => handleActivate(p)}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.boxShadow = 'var(--shadow-md)'
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
                }}
              >
                {/* 激活标记 */}
                {isActive && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '-8px',
                      right: 'var(--spacing-md)',
                      padding: '2px 10px',
                      borderRadius: 'var(--radius-full)',
                      background: 'var(--accent)',
                      color: '#fff',
                      fontSize: 'var(--font-xs)',
                      fontWeight: 600,
                    }}
                  >
                    ✓ 当前角色
                  </div>
                )}

                {/* 头像 */}
                <div
                  className="flex items-center justify-center"
                  style={{
                    width: '56px',
                    height: '56px',
                    borderRadius: 'var(--radius-lg)',
                    background: 'var(--bg-secondary)',
                    fontSize: '32px',
                    marginBottom: 'var(--spacing-sm)',
                  }}
                >
                  {getPersonaAvatar(p)}
                </div>

                {/* 名称 */}
                <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                  {p.name}
                </h3>

                {/* 角色定位 (v2.3.0 A3) */}
                {p.role && (
                  <div style={{ marginBottom: '6px' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-secondary)',
                        fontSize: 'var(--font-xs)',
                      }}
                    >
                      🎯 {p.role}
                    </span>
                  </div>
                )}

                {/* SOUL 摘要 */}
                <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', lineHeight: '1.5', minHeight: '40px' }}>
                  {truncate(getPersonaSoul(p), 80) || '暂无灵魂设定'}
                </p>

                {/* 操作按钮 */}
                <div className="flex gap-2 flex-wrap" style={{ marginTop: 'var(--spacing-md)' }} onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => openEdit(p)}
                    className="transition-all"
                    style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-secondary)',
                      color: 'var(--text-primary)',
                      fontSize: 'var(--font-xs)',
                      border: '1px solid var(--border)',
                      cursor: 'pointer',
                    }}
                  >
                    ✏️ 编辑
                  </button>
                  <button
                    onClick={() => openRelations(p)}
                    className="transition-all"
                    style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-secondary)',
                      color: 'var(--text-primary)',
                      fontSize: 'var(--font-xs)',
                      border: '1px solid var(--border)',
                      cursor: 'pointer',
                    }}
                  >
                    🔗 关联
                  </button>
                  <button
                    onClick={() => setDeleteTarget(p)}
                    className="transition-all"
                    style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-md)',
                      background: 'transparent',
                      color: '#e53e3e',
                      fontSize: 'var(--font-xs)',
                      border: '1px solid #F5C6CB',
                      cursor: 'pointer',
                    }}
                  >
                    🗑️ 删除
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ===== 新建/编辑表单弹窗 ===== */}
      {showForm && (
        <div
          className="fixed inset-0 flex items-center justify-center"
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
          }}
          onClick={() => setShowForm(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="角色表单"
            className="flex flex-col"
            style={{
              width: '90%',
              maxWidth: '560px',
              maxHeight: '90vh',
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-xl)',
              boxShadow: 'var(--shadow-xl)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 弹窗标题 */}
            <div
              className="flex items-center justify-between shrink-0"
              style={{
                padding: 'var(--spacing-lg)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                {form.id !== null ? '✏️ 编辑角色' : '✨ 新建角色'}
              </h3>
              <button
                onClick={() => setShowForm(false)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  padding: '4px',
                }}
              >
                ✕
              </button>
            </div>

            {/* 表单内容 */}
            <div className="flex-1 overflow-y-auto" style={{ padding: 'var(--spacing-lg)' }}>
              {/* 头像选择 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  头像
                </label>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_CHOICES.map(emoji => (
                    <button
                      key={emoji}
                      onClick={() => setForm(prev => ({ ...prev, avatar: emoji }))}
                      className="transition-all"
                      style={{
                        width: '40px',
                        height: '40px',
                        borderRadius: 'var(--radius-md)',
                        background: form.avatar === emoji ? 'var(--accent)' : 'var(--bg-secondary)',
                        border: form.avatar === emoji ? '2px solid var(--accent)' : '1px solid var(--border)',
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

              {/* 名称 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  角色名称
                </label>
                <input
                  type="text"
                  value={form.name}
                  onInput={(e) => setForm(prev => ({ ...prev, name: (e.target as HTMLInputElement).value }))}
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
                  🤖 AI 辅助生成 SOUL
                </label>
                <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-sm)' }}>
                  描述你想要的角色,AI 会自动生成灵魂设定
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={aiDesc}
                    onInput={(e) => setAiDesc((e.target as HTMLInputElement).value)}
                    placeholder="例如:一个温柔的知识渊博的学者..."
                    disabled={aiLoading}
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
                    disabled={aiLoading || !aiDesc.trim()}
                    className="transition-all shrink-0"
                    style={{
                      padding: '8px var(--spacing-md)',
                      borderRadius: 'var(--radius-md)',
                      background: aiLoading || !aiDesc.trim() ? 'var(--bg-secondary)' : 'var(--accent)',
                      color: '#fff',
                      fontSize: 'var(--font-sm)',
                      fontWeight: 600,
                      border: 'none',
                      cursor: aiLoading || !aiDesc.trim() ? 'default' : 'pointer',
                    }}
                  >
                    {aiLoading ? '生成中...' : '生成'}
                  </button>
                </div>
              </div>

              {/* SOUL 内容 */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>
                  SOUL 灵魂设定
                </label>
                <textarea
                  value={form.soul}
                  onInput={(e) => setForm(prev => ({ ...prev, soul: (e.target as HTMLTextAreaElement).value }))}
                  placeholder="描述角色的性格、背景、说话风格、知识领域..."
                  rows={6}
                  className="resize-y w-full"
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

              {/* v2.3.0 A3: 角色三元组 (CrewAI) — 用于 role_matcher 自动匹配 */}
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
                  🎯 角色三元组 (用于自动匹配关联)
                </label>
                <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--spacing-sm)' }}>
                  填写后,系统会按相似度/互补度自动推荐候选关联角色
                </p>

                {/* role */}
                <input
                  type="text"
                  value={form.role}
                  onInput={(e) => setForm(prev => ({ ...prev, role: (e.target as HTMLInputElement).value }))}
                  placeholder="角色定位,如:架构师 / 编码者 / 评审"
                  style={{
                    width: '100%',
                    padding: '8px var(--spacing-sm)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    marginBottom: 'var(--spacing-sm)',
                    boxSizing: 'border-box',
                  }}
                />

                {/* goal */}
                <input
                  type="text"
                  value={form.goal}
                  onInput={(e) => setForm(prev => ({ ...prev, goal: (e.target as HTMLInputElement).value }))}
                  placeholder="角色目标,如:交付高质量的代码实现"
                  style={{
                    width: '100%',
                    padding: '8px var(--spacing-sm)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    marginBottom: 'var(--spacing-sm)',
                    boxSizing: 'border-box',
                  }}
                />

                {/* backstory */}
                <textarea
                  value={form.backstory}
                  onInput={(e) => setForm(prev => ({ ...prev, backstory: (e.target as HTMLTextAreaElement).value }))}
                  placeholder="背景故事:角色的经历、专长、个性..."
                  rows={3}
                  className="resize-y w-full"
                  style={{
                    width: '100%',
                    padding: '8px var(--spacing-sm)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    fontSize: 'var(--font-sm)',
                    outline: 'none',
                    lineHeight: '1.5',
                    fontFamily: 'monospace',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* 底部按钮 */}
            <div
              className="flex justify-end gap-2 shrink-0"
              style={{
                padding: 'var(--spacing-md) var(--spacing-lg)',
                borderTop: '1px solid var(--border)',
                background: 'var(--bg-primary)',
              }}
            >
              <button
                onClick={() => setShowForm(false)}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-lg)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  border: '1px solid var(--border)',
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-lg)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--accent)',
                  color: '#fff',
                  fontSize: 'var(--font-sm)',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 关联角色管理弹窗 (v2.3.0 A3) ===== */}
      {relationsTarget && (
        <div
          className="fixed inset-0 flex items-center justify-center"
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
          }}
          onClick={() => setRelationsTarget(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="关联角色管理"
            className="flex flex-col"
            style={{
              width: '90%',
              maxWidth: '640px',
              maxHeight: '90vh',
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-xl)',
              boxShadow: 'var(--shadow-xl)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 弹窗标题 */}
            <div
              className="flex items-center justify-between shrink-0"
              style={{
                padding: 'var(--spacing-lg)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <div>
                <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>
                  🔗 关联角色管理
                </h3>
                <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  为「{relationsTarget.name}」管理与其他角色的协作关系
                </p>
              </div>
              <button
                onClick={() => setRelationsTarget(null)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  padding: '4px',
                }}
              >
                ✕
              </button>
            </div>

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto" style={{ padding: 'var(--spacing-lg)' }}>
              {loadingRelations ? (
                <div className="flex items-center justify-center" style={{ padding: 'var(--spacing-2xl)' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-sm)' }}>加载中...</span>
                </div>
              ) : (
                <>
                  {/* 已关联角色列表 */}
                  <div style={{ marginBottom: 'var(--spacing-lg)' }}>
                    <h4 style={{ fontSize: 'var(--font-sm)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                      📋 已关联角色 ({relations.length})
                    </h4>
                    {relations.length === 0 ? (
                      <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', padding: 'var(--spacing-sm)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                        暂无关联角色
                      </p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {relations.map(rel => {
                          const meta = RELATION_META[rel.relation_type] || RELATION_META.complement
                          return (
                            <div
                              key={rel.id}
                              className="flex items-center justify-between"
                              style={{
                                padding: 'var(--spacing-sm) var(--spacing-md)',
                                borderRadius: 'var(--radius-md)',
                                background: 'var(--bg-secondary)',
                                border: '1px solid var(--border)',
                              }}
                            >
                              <div className="flex items-center gap-2" style={{ flex: 1, minWidth: 0 }}>
                                <span style={{ fontSize: '20px' }}>{getPersonaAvatar(rel.target)}</span>
                                <div style={{ minWidth: 0, flex: 1 }}>
                                  <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {rel.target?.name || `#${rel.target_id}`}
                                  </div>
                                  <div className="flex items-center gap-2" style={{ marginTop: '2px' }}>
                                    <span
                                      style={{
                                        padding: '1px 6px',
                                        borderRadius: 'var(--radius-full)',
                                        background: meta.color,
                                        color: '#fff',
                                        fontSize: 'var(--font-xs)',
                                        fontWeight: 600,
                                      }}
                                    >
                                      {meta.emoji} {meta.label}
                                    </span>
                                    <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)' }}>
                                      强度 {(rel.strength * 100).toFixed(0)}%
                                    </span>
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => handleDeleteRelation(rel.id)}
                                className="transition-all shrink-0"
                                style={{
                                  padding: '4px 10px',
                                  borderRadius: 'var(--radius-md)',
                                  background: 'transparent',
                                  color: '#e53e3e',
                                  fontSize: 'var(--font-xs)',
                                  border: '1px solid #F5C6CB',
                                  cursor: 'pointer',
                                  marginLeft: 'var(--spacing-sm)',
                                }}
                              >
                                解除
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* 自动匹配候选 */}
                  <div style={{ marginBottom: 'var(--spacing-lg)' }}>
                    <h4 style={{ fontSize: 'var(--font-sm)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                      🤖 自动匹配候选 ({candidates.length})
                    </h4>
                    {candidates.length === 0 ? (
                      <p style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', padding: 'var(--spacing-sm)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                        暂无候选 — 请为当前角色和其他角色填写「角色三元组」(role/goal/backstory) 以启用自动匹配
                      </p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {candidates.map(cand => {
                          const candPersona = cand.persona || {}
                          const meta = RELATION_META[cand.relation_type] || RELATION_META.complement
                          const candId = candPersona.id
                          const alreadyRelated = relations.some(r => r.target_id === candId)
                          return (
                            <div
                              key={candId}
                              className="flex items-center justify-between"
                              style={{
                                padding: 'var(--spacing-sm) var(--spacing-md)',
                                borderRadius: 'var(--radius-md)',
                                background: 'var(--bg-secondary)',
                                border: '1px solid var(--border)',
                              }}
                            >
                              <div className="flex items-center gap-2" style={{ flex: 1, minWidth: 0 }}>
                                <span style={{ fontSize: '20px' }}>{getPersonaAvatar(candPersona)}</span>
                                <div style={{ minWidth: 0, flex: 1 }}>
                                  <div style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {candPersona.name || `#${candId}`}
                                    {candPersona.role && (
                                      <span style={{ marginLeft: '6px', fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', fontWeight: 400 }}>
                                        · {candPersona.role}
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2" style={{ marginTop: '2px' }}>
                                    <span
                                      style={{
                                        padding: '1px 6px',
                                        borderRadius: 'var(--radius-full)',
                                        background: meta.color,
                                        color: '#fff',
                                        fontSize: 'var(--font-xs)',
                                        fontWeight: 600,
                                      }}
                                    >
                                      {meta.emoji} {meta.label}
                                    </span>
                                    <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)' }}>
                                      匹配度 {(cand.score * 100).toFixed(0)}%
                                    </span>
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => handleCreateRelation(candId, cand.relation_type, cand.score)}
                                disabled={alreadyRelated}
                                className="transition-all shrink-0"
                                style={{
                                  padding: '4px 10px',
                                  borderRadius: 'var(--radius-md)',
                                  background: alreadyRelated ? 'var(--bg-secondary)' : 'var(--accent)',
                                  color: alreadyRelated ? 'var(--text-secondary)' : '#fff',
                                  fontSize: 'var(--font-xs)',
                                  fontWeight: 600,
                                  border: 'none',
                                  cursor: alreadyRelated ? 'default' : 'pointer',
                                  marginLeft: 'var(--spacing-sm)',
                                }}
                              >
                                {alreadyRelated ? '已关联' : '+ 关联'}
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* 手动添加关联 */}
                  <div
                    style={{
                      padding: 'var(--spacing-md)',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <h4 style={{ fontSize: 'var(--font-sm)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 'var(--spacing-sm)' }}>
                      ✍️ 手动添加关联
                    </h4>
                    <div className="flex flex-col gap-2">
                      {/* 目标角色选择 */}
                      <select
                        value={newRelationTargetId ?? ''}
                        onChange={(e) => setNewRelationTargetId(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
                        style={{
                          width: '100%',
                          padding: '8px var(--spacing-sm)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border)',
                          background: 'var(--bg-card)',
                          color: 'var(--text-primary)',
                          fontSize: 'var(--font-sm)',
                          outline: 'none',
                          boxSizing: 'border-box',
                        }}
                      >
                        <option value="">选择目标角色...</option>
                        {personas
                          .filter(p => p.id !== relationsTarget.id)
                          .map(p => (
                            <option key={p.id} value={p.id}>
                              {p.name}{p.role ? ` · ${p.role}` : ''}
                            </option>
                          ))}
                      </select>

                      {/* 关系类型 + 强度 */}
                      <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                        <select
                          value={newRelationType}
                          onChange={(e) => setNewRelationType(e.currentTarget.value)}
                          style={{
                            flex: '1 1 140px',
                            padding: '8px var(--spacing-sm)',
                            borderRadius: 'var(--radius-md)',
                            border: '1px solid var(--border)',
                            background: 'var(--bg-card)',
                            color: 'var(--text-primary)',
                            fontSize: 'var(--font-sm)',
                            outline: 'none',
                            boxSizing: 'border-box',
                          }}
                        >
                          <option value="complement">🧩 互补 complement</option>
                          <option value="assist">🤝 协助 assist</option>
                          <option value="delegate">📤 委派 delegate</option>
                        </select>
                        <div className="flex items-center gap-2" style={{ flex: '1 1 140px', padding: '0 var(--spacing-sm)' }}>
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.1}
                            value={newRelationStrength}
                            onInput={(e) => setNewRelationStrength(Number((e.target as HTMLInputElement).value))}
                            style={{ flex: 1 }}
                          />
                          <span style={{ fontSize: 'var(--font-xs)', color: 'var(--text-secondary)', minWidth: '36px', textAlign: 'right' }}>
                            {(newRelationStrength * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>

                      <button
                        onClick={() => {
                          if (newRelationTargetId === null) {
                            setError('请选择目标角色')
                            return
                          }
                          handleCreateRelation(newRelationTargetId, newRelationType, newRelationStrength)
                        }}
                        disabled={newRelationTargetId === null}
                        className="transition-all"
                        style={{
                          padding: '8px var(--spacing-md)',
                          borderRadius: 'var(--radius-md)',
                          background: newRelationTargetId === null ? 'var(--bg-secondary)' : 'var(--accent)',
                          color: '#fff',
                          fontSize: 'var(--font-sm)',
                          fontWeight: 600,
                          border: 'none',
                          cursor: newRelationTargetId === null ? 'default' : 'pointer',
                          alignSelf: 'flex-start',
                        }}
                      >
                        + 添加关联
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* 底部按钮 */}
            <div
              className="flex justify-end shrink-0"
              style={{
                padding: 'var(--spacing-md) var(--spacing-lg)',
                borderTop: '1px solid var(--border)',
                background: 'var(--bg-primary)',
              }}
            >
              <button
                onClick={() => setRelationsTarget(null)}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-lg)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  border: '1px solid var(--border)',
                  cursor: 'pointer',
                }}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 删除确认弹窗 ===== */}
      {deleteTarget && (
        <div
          className="fixed inset-0 flex items-center justify-center"
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
          }}
          onClick={() => setDeleteTarget(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="删除角色确认"
            style={{
              width: '90%',
              maxWidth: '400px',
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-xl)',
              boxShadow: 'var(--shadow-xl)',
              padding: 'var(--spacing-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ textAlign: 'center', marginBottom: 'var(--spacing-md)' }}>
              <span style={{ fontSize: '48px' }}>🗑️</span>
            </div>
            <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)', textAlign: 'center', marginBottom: 'var(--spacing-sm)' }}>
              确认删除角色?
            </h3>
            <p style={{ fontSize: 'var(--font-sm)', color: 'var(--text-secondary)', textAlign: 'center', marginBottom: 'var(--spacing-lg)' }}>
              确定要删除「{deleteTarget.name}」吗?此操作不可撤销。
            </p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={() => setDeleteTarget(null)}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-lg)',
                  borderRadius: 'var(--radius-md)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 'var(--font-sm)',
                  border: '1px solid var(--border)',
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                className="transition-all"
                style={{
                  padding: '8px var(--spacing-lg)',
                  borderRadius: 'var(--radius-md)',
                  background: '#e53e3e',
                  color: '#fff',
                  fontSize: 'var(--font-sm)',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
