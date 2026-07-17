// 双栏设置面板 - macOS 风格, 左栏分类列表 + 右栏表单
import { useState, useEffect } from "preact/hooks"
import { apiGet, apiPost, apiDelete } from "../lib/api"
import type { ProviderInfo, Persona, Channel } from "../lib/types"
import { useAppVersion } from '../lib/store'
import UpdateChecker from "./UpdateChecker"

// 设置分类
const CATEGORIES = [
  { id: "general", label: "通用", icon: "⚙️" },
  { id: "provider", label: "Provider", icon: "🔌" },
  { id: "persona", label: "角色", icon: "🎭" },
  { id: "memory", label: "记忆", icon: "🧠" },
  { id: "sync", label: "同步", icon: "🔄" },
  { id: "channel", label: "渠道", icon: "📡" },
  { id: "security", label: "安全", icon: "🔒" },
  { id: "multimodal", label: "多模态", icon: "🎬" },
  { id: "os", label: "OS感知", icon: "🖥️" },
  { id: "about", label: "关于", icon: "ℹ️" },
]

const THEMES = [
  { id: "warm-orange", label: "暖橙", color: "#FF8C42" },
  { id: "soft-pink", label: "柔粉", color: "#FF6B8A" },
  { id: "cream-beige", label: "奶油", color: "#D4A574" },
]

export default function Settings() {
  const [activeCategory, setActiveCategory] = useState("general")
  const [theme, setTheme] = useState(
    () => localStorage.getItem("app-theme") || "warm-orange"
  )

  // 各分类的数据状态
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [syncDevices, setSyncDevices] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  // 版本号: 优先使用 store (Phase 0 统一状态层), 避免重复 fetch
  const appVersion = useAppVersion()

  // 渠道添加表单
  const [showChannelForm, setShowChannelForm] = useState(false)
  const [channelForm, setChannelForm] = useState({ channel_type: 'discord', name: '', config_json: '{}' })
  const [savingChannel, setSavingChannel] = useState(false)
  // 同步设备配对表单
  const [showPairingForm, setShowPairingForm] = useState(false)
  const [pairingForm, setPairingForm] = useState({ device_name: '' })
  const [pairingResult, setPairingResult] = useState('')
  const [pairingLoading, setPairingLoading] = useState(false)

  // Provider 添加表单
  const [showProviderForm, setShowProviderForm] = useState(false)
  const [providerForm, setProviderForm] = useState({ provider: '', api_key: '', api_base: '', model: '' })
  const [savingProvider, setSavingProvider] = useState(false)
  const [error, setError] = useState("")

  // 通用设置
  const [language, setLanguage] = useState("zh-CN")
  const [windowOnTop, setWindowOnTop] = useState(false)
  const [autoStart, setAutoStart] = useState(false)

  // 记忆设置
  const [memoryLayers, setMemoryLayers] = useState(3)
  const [compressThreshold, setCompressThreshold] = useState(100)
  const [spongeMode, setSpongeMode] = useState(true)
  const [blackholeMode, setBlackholeMode] = useState(false)

  // 安全设置
  const [aclRules, setAclRules] = useState("")
  const [injectionGuard, setInjectionGuard] = useState(true)
  const [keyRotationDays, setKeyRotationDays] = useState(30)

  // 多模态设置
  const [visionEnabled, setVisionEnabled] = useState(true)
  const [asrEnabled, setAsrEnabled] = useState(false)
  const [ttsEnabled, setTtsEnabled] = useState(false)
  const [videoAnalysisEnabled, setVideoAnalysisEnabled] = useState(false)
  const [asrModel, setAsrModel] = useState("whisper-1")
  const [ttsVoice, setTtsVoice] = useState("alloy")

  // OS 感知设置
  const [clipboardWatch, setClipboardWatch] = useState(false)
  const [fileWatch, setFileWatch] = useState(false)
  const [screenSense, setScreenSense] = useState(false)
  const [trayEnabled, setTrayEnabled] = useState(true)
  const [watchPaths, setWatchPaths] = useState("")

  // 切换主题
  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme)
    localStorage.setItem("app-theme", newTheme)
    document.documentElement.dataset.theme = newTheme
  }

  // 加载数据
  const loadData = async (category: string) => {
    setLoading(true)
    setError("")
    try {
      switch (category) {
        case "provider":
          setProviders((await apiGet<ProviderInfo[]>("/providers")) ?? [])
          break
        case "persona":
          setPersonas((await apiGet<Persona[]>("/persona")) ?? [])
          break
        case "channel":
          setChannels((await apiGet<Channel[]>("/channel/list")) ?? [])
          break
        case "sync":
          setSyncDevices((await apiGet<any[]>("/sync/devices")) ?? [])
          break
      }
    } catch (e: any) {
      setError(e.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData(activeCategory)
  }, [activeCategory])

  // --- 操作处理 ---

  // 保存 Provider 配置
  const saveProvider = async () => {
    if (!providerForm.provider.trim() || !providerForm.api_key.trim()) {
      setError('请选择 Provider 并输入 API Key')
      return
    }
    setSavingProvider(true)
    setError('')
    try {
      await apiPost('/providers/configure', {
        provider: providerForm.provider.trim(),
        api_key: providerForm.api_key.trim(),
        api_base: providerForm.api_base.trim() || undefined,
        default_model: providerForm.model.trim() || undefined,
      })
      setShowProviderForm(false)
      setProviderForm({ provider: '', api_key: '', api_base: '', model: '' })
      await loadData('provider')
    } catch (e: any) {
      setError(e?.message || '保存 Provider 失败')
    } finally {
      setSavingProvider(false)
    }
  }

  // 保存渠道
  const saveChannel = async () => {
    if (!channelForm.name.trim()) { setError('请输入渠道名称'); return }
    setSavingChannel(true); setError('')
    try {
      let config = {}
      try { config = JSON.parse(channelForm.config_json) } catch {}
      await apiPost('/channel', { channel_type: channelForm.channel_type, name: channelForm.name.trim(), config })
      setShowChannelForm(false); setChannelForm({ channel_type: 'discord', name: '', config_json: '{}' })
      await loadData('channel')
    } catch (e: any) { setError(e?.message || '添加渠道失败') }
    finally { setSavingChannel(false) }
  }
  // 发起设备配对
  const startPairing = async () => {
    if (!pairingForm.device_name.trim()) { setError('请输入设备名称'); return }
    setPairingLoading(true); setPairingResult(''); setError('')
    try {
      const result = await apiPost<any>('/sync/pairing/initiate', { device_name: pairingForm.device_name.trim() })
      setPairingResult(result?.pairing_code || '配对码已生成')
      setPairingForm({ device_name: '' })
      await loadData('sync')
    } catch (e: any) { setError(e?.message || '配对失败') }
    finally { setPairingLoading(false) }
  }


  const deleteChannel = async (id: number) => {
    try {
      await apiDelete(`/channel/${id}`)
      setChannels(channels.filter((c) => c.id !== id))
    } catch (e: any) {
      setError(e.message)
    }
  }

  const deleteSyncDevice = async (deviceId: string) => {
    try {
      await apiDelete(`/sync/devices/${deviceId}`)
      setSyncDevices(syncDevices.filter((d) => d.device_id !== deviceId))
    } catch (e: any) {
      setError(e.message)
    }
  }

  // --- 渲染各分类面板 ---

  const renderPanel = () => {
    if (loading) {
      return <div style={{ padding: "40px", textAlign: "center", color: "var(--text-secondary)" }}>加载中...</div>
    }

    switch (activeCategory) {
      case "general":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>通用设置</h2>
            {error && <div style={errorStyle}>{error}</div>}

            {/* 主题切换 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>主题</label>
              <div className="flex gap-3 mt-2">
                {THEMES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleThemeChange(t.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "8px 16px",
                      borderRadius: "var(--radius-md)",
                      border: theme === t.id ? "2px solid var(--accent)" : "2px solid var(--border)",
                      background: theme === t.id ? "var(--bg-secondary)" : "var(--bg-card)",
                      cursor: "pointer",
                      fontSize: "var(--font-sm)",
                      color: "var(--text-primary)",
                    }}
                  >
                    <span style={{ width: "16px", height: "16px", borderRadius: "50%", background: t.color }} />
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 语言 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>语言</label>
              <select
                value={language}
                onChange={(e) => setLanguage((e.target as HTMLSelectElement).value)}
                style={inputStyle}
              >
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
            </div>

            {/* 窗口置顶 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={windowOnTop} onChange={(e) => setWindowOnTop((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                窗口置顶
              </label>
            </div>

            {/* 开机自启 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={autoStart} onChange={(e) => setAutoStart((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                开机自启动
              </label>
            </div>
          </div>
        )

      case "provider":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>Provider 管理</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setProviderForm({ provider: providers[0]?.name || "openai", api_key: "", api_base: "", model: "" }); setShowProviderForm(true); setError("") }}>+ 添加 Provider</button>
            </div>
            <div>
              {providers.length === 0 && <div style={emptyStyle}>暂无 Provider</div>}
              {providers.map((p) => (
                <div key={p.name} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        模型: {p.supported_models?.join(", ") || "未知"}
                      </div>
                    </div>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      fontSize: "var(--font-xs)",
                      background: p.available ? "rgba(40,200,64,0.15)" : "rgba(255,95,87,0.15)",
                      color: p.available ? "#28C840" : "#FF5F57",
                    }}>
                      {p.available ? "可用" : "不可用"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "persona":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>角色管理</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { document.querySelector('[data-nav="persona"]')?.dispatchEvent(new Event("click")); setError("") }}>+ 创建角色</button>
            </div>
            <div>
              {personas.length === 0 && <div style={emptyStyle}>暂无角色</div>}
              {personas.map((p) => (
                <div key={p.id} style={cardStyle}>
                  <div className="flex items-center gap-3">
                    <span style={{ fontSize: "24px" }}>{p.avatar || "🎭"}</span>
                    <div className="flex-1">
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        {p.soul?.slice(0, 60) || "暂无描述"}
                      </div>
                    </div>
                    {p.is_active && (
                      <span style={{ fontSize: "var(--font-xs)", color: "var(--accent)", fontWeight: 600 }}>当前</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "memory":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>记忆设置</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={formGroupStyle}>
              <label style={labelStyle}>记忆层数: {memoryLayers}</label>
              <input type="range" min="1" max="5" value={memoryLayers}
                onChange={(e) => setMemoryLayers(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>压缩阈值(条): {compressThreshold}</label>
              <input type="range" min="50" max="500" step="10" value={compressThreshold}
                onChange={(e) => setCompressThreshold(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={spongeMode} onChange={(e) => setSpongeMode((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                海绵模式(自动吸收信息)
              </label>
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={blackholeMode} onChange={(e) => setBlackholeMode((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                黑洞模式(深度压缩)
              </label>
            </div>
          </div>
        )

      case "sync":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>同步设置</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setPairingForm({ device_name: "" }); setPairingResult(""); setShowPairingForm(true); setError("") }}>+ 配对新设备</button>
            </div>
            <div>
              {syncDevices.length === 0 && <div style={emptyStyle}>暂无配对设备</div>}
              {syncDevices.map((d) => (
                <div key={d.device_id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{d.device_name || d.device_id}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        {d.platform || "未知平台"} · {d.last_seen || "未连接"}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteSyncDevice(d.device_id)}>删除</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "channel":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>渠道管理</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setChannelForm({ channel_type: "discord", name: "", config_json: "{}" }); setShowChannelForm(true); setError("") }}>+ 添加渠道</button>
            </div>
            <div>
              {channels.length === 0 && <div style={emptyStyle}>暂无渠道</div>}
              {channels.map((c) => (
                <div key={c.id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{c.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        类型: {c.channel_type} · {c.enabled ? "已启用" : "已禁用"}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteChannel(c.id)}>删除</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "security":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>安全设置</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={formGroupStyle}>
              <label style={labelStyle}>ACL 规则(JSON 格式)</label>
              <textarea
                value={aclRules}
                onChange={(e) => setAclRules((e.target as HTMLTextAreaElement).value)}
                style={{ ...inputStyle, minHeight: "100px", fontFamily: "monospace" }}
                placeholder='[{"action": "allow", "path": "/chat/*"}]'
              />
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={injectionGuard} onChange={(e) => setInjectionGuard((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                注入防护
              </label>
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>密钥轮换周期(天): {keyRotationDays}</label>
              <input type="range" min="7" max="90" value={keyRotationDays}
                onChange={(e) => setKeyRotationDays(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
          </div>
        )

      case "multimodal":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>多模态设置</h2>
            {error && <div style={errorStyle}>{error}</div>}

            {/* 视觉 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                🖼️ 图像理解
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={visionEnabled}
                    onChange={(e) => setVisionEnabled((e.target as HTMLInputElement).checked)}
                  />
                  启用图像理解 (粘贴图片后 AI 自动描述)
                </label>
              </div>
            </div>

            {/* 语音识别 ASR */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                🎤 语音识别 (ASR)
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={asrEnabled}
                    onChange={(e) => setAsrEnabled((e.target as HTMLInputElement).checked)}
                  />
                  启用语音输入
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>ASR 模型</label>
                <select value={asrModel} onChange={(e) => setAsrModel((e.target as HTMLSelectElement).value)} style={inputStyle}>
                  <option value="whisper-1">Whisper-1 (OpenAI)</option>
                  <option value="whisper-large">Whisper-Large (本地)</option>
                  <option value="paraformer">Paraformer (通义)</option>
                </select>
              </div>
            </div>

            {/* 语音合成 TTS */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                🔊 语音合成 (TTS)
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={ttsEnabled}
                    onChange={(e) => setTtsEnabled((e.target as HTMLInputElement).checked)}
                  />
                  启用语音输出
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>音色</label>
                <select value={ttsVoice} onChange={(e) => setTtsVoice((e.target as HTMLSelectElement).value)} style={inputStyle}>
                  <option value="alloy">Alloy</option>
                  <option value="echo">Echo</option>
                  <option value="fable">Fable</option>
                  <option value="onyx">Onyx</option>
                  <option value="nova">Nova</option>
                  <option value="shimmer">Shimmer</option>
                </select>
              </div>
            </div>

            {/* 视频分析 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                🎥 视频分析
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={videoAnalysisEnabled}
                    onChange={(e) => setVideoAnalysisEnabled((e.target as HTMLInputElement).checked)}
                  />
                  启用视频分析 (帧抽取 + 图像理解)
                </label>
              </div>
            </div>
          </div>
        )

      case "os":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>OS 感知设置</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)", marginBottom: "16px", padding: "8px 12px", background: "rgba(255,140,66,0.1)", borderRadius: "var(--radius-md)" }}>
              ⚠️ 屏幕感知涉及隐私,默认关闭。截图仅用于当前请求,不持久化存储。
            </div>

            {/* 剪贴板监控 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                📋 剪贴板监控
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={clipboardWatch}
                    onChange={(e) => setClipboardWatch((e.target as HTMLInputElement).checked)}
                  />
                  监控剪贴板变化 (自动检测代码/URL/文本)
                </label>
              </div>
            </div>

            {/* 文件夹监控 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                📁 文件夹监控
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={fileWatch}
                    onChange={(e) => setFileWatch((e.target as HTMLInputElement).checked)}
                  />
                  启用文件夹监控
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>监控路径 (每行一个)</label>
                <textarea
                  value={watchPaths}
                  onChange={(e) => setWatchPaths((e.target as HTMLTextAreaElement).value)}
                  placeholder={"C:\\Users\\Documents\nD:\\Projects"}
                  style={{ ...inputStyle, minHeight: "60px", fontFamily: "monospace" }}
                />
              </div>
            </div>

            {/* 屏幕感知 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                🖥️ 屏幕实时感知
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={screenSense}
                    onChange={(e) => setScreenSense((e.target as HTMLInputElement).checked)}
                  />
                  启用屏幕感知 (截图不存储,仅用于当前请求)
                </label>
              </div>
            </div>

            {/* 系统托盘 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                📌 系统托盘
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={trayEnabled}
                    onChange={(e) => setTrayEnabled((e.target as HTMLInputElement).checked)}
                  />
                  启用系统托盘 (最小化到托盘)
                </label>
              </div>
            </div>
          </div>
        )

case "about":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>关于</h2>
            <div style={cardStyle}>
              <div style={{ fontSize: "var(--font-xl)", fontWeight: 700, color: "var(--text-primary)", marginBottom: "8px" }}>
                Pangu Nebula
              </div>
              <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)", marginBottom: "16px" }}>
                版本 v{appVersion || "..."}
              </div>
              <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                盘古星云 - 一个基于多 Provider 的智能 AI 助理平台,支持角色管理、记忆图谱、
                蜂群协作、技能市场、多渠道接入、设备同步等丰富功能。
              </div>
              <div style={{ marginTop: "16px", fontSize: "var(--font-sm)" }}>
                <a href="https://github.com" style={{ color: "var(--accent)", textDecoration: "none" }}>
                  📦 开源仓库 →
                </a>
              </div>
            </div>

            {/* P0-W6.2: 自动更新检查 */}
            <div style={{ marginTop: "16px" }}>
              <UpdateChecker />
            </div>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="flex h-full" style={{ background: "var(--bg-primary)" }}>
      {/* 左栏: 分类列表 */}
      <div
        style={{
          width: "200px",
          flexShrink: 0,
          background: "var(--bg-secondary)",
          borderRight: "1px solid var(--border)",
          padding: "12px 0",
          overflowY: "auto",
        }}
      >
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              width: "100%",
              padding: "10px 16px",
              background: activeCategory === cat.id ? "var(--bg-card)" : "transparent",
              border: "none",
              borderLeft: activeCategory === cat.id ? "3px solid var(--accent)" : "3px solid transparent",
              cursor: "pointer",
              fontSize: "var(--font-sm)",
              color: activeCategory === cat.id ? "var(--text-primary)" : "var(--text-secondary)",
              fontWeight: activeCategory === cat.id ? 600 : 400,
              textAlign: "left",
            }}
          >
            <span>{cat.icon}</span>
            {cat.label}
          </button>
        ))}
      </div>

      {/* 右栏: 设置表单 */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          background: "var(--bg-card)",
        }}
      >
        {renderPanel()}
      </div>
      {/* Provider 添加表单弹窗 */}
      {showProviderForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowProviderForm(false)}>
          <div role="dialog" aria-modal="true" aria-label="添加 Provider" className="flex flex-col" style={{ width: '90%', maxWidth: '480px', maxHeight: '90vh', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between shrink-0" style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 添加 Provider</h3>
              <button onClick={() => setShowProviderForm(false)} style={{ border: 'none', background: 'transparent', fontSize: '20px', cursor: 'pointer', color: 'var(--text-secondary)' }}>x</button>
            </div>
            <div className="flex-1 overflow-y-auto" style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <input
                  list="provider-list"
                  value={providerForm.provider}
                  onInput={(e) => setProviderForm(prev => ({ ...prev, provider: (e.target as HTMLInputElement).value }))}
                  placeholder="Type or select Provider..."
                  style={{ ...inputStyle, width: '100%' }}
                />
                <datalist id="provider-list">
                  {providers.map(p => <option key={p.name} value={p.name} />)}
                </datalist>
              </div>
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>API Key</label>
                <input type="password" value={providerForm.api_key} onInput={(e) => setProviderForm(prev => ({ ...prev, api_key: (e.target as HTMLInputElement).value }))} placeholder="sk-..." style={{ ...inputStyle, width: '100%' }} />
              </div>
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>API Base URL (可选)</label>
                <input type="text" value={providerForm.api_base} onInput={(e) => setProviderForm(prev => ({ ...prev, api_base: (e.target as HTMLInputElement).value }))} placeholder="https://api.deepseek.com" style={{ ...inputStyle, width: '100%' }} />
              </div>
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>默认模型 (可选)</label>
                <input type="text" value={providerForm.model} onInput={(e) => setProviderForm(prev => ({ ...prev, model: (e.target as HTMLInputElement).value }))} placeholder="deepseek-chat" style={{ ...inputStyle, width: '100%' }} />
              </div>
            </div>
            <div className="flex justify-end gap-2 shrink-0" style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', background: 'var(--bg-primary)' }}>
              <button onClick={() => setShowProviderForm(false)} style={{ padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-sm)', border: '1px solid var(--border)', cursor: 'pointer' }}>取消</button>
              <button onClick={saveProvider} disabled={savingProvider} style={{ padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)', background: 'var(--accent)', color: '#fff', fontSize: 'var(--font-sm)', fontWeight: 600, border: 'none', cursor: 'pointer' }}>{savingProvider ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 渠道添加弹窗 */}
      {showChannelForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowChannelForm(false)}>
          <div role="dialog" aria-modal="true" aria-label="添加渠道" className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 添加渠道</h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>渠道类型</label>
                <select value={channelForm.channel_type} onChange={(e) => setChannelForm(prev => ({ ...prev, channel_type: (e.target as HTMLSelectElement).value }))} style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
                  {['discord','telegram','feishu','wechat','wecom','dingtalk'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>名称</label>
                <input value={channelForm.name} onInput={(e) => setChannelForm(prev => ({ ...prev, name: (e.target as HTMLInputElement).value }))} placeholder="我的渠道" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setShowChannelForm(false)} style={btnCancelStyle}>取消</button>
              <button onClick={saveChannel} disabled={savingChannel} style={btnSaveStyle}>{savingChannel ? '保存中...' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 设备配对弹窗 */}
      {showPairingForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowPairingForm(false)}>
          <div role="dialog" aria-modal="true" aria-label="配对新设备" className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 配对新设备</h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              {pairingResult ? (
                <div style={{ textAlign: 'center', padding: '20px' }}>
                  <div style={{ fontSize: '48px', marginBottom: '12px' }}>✅</div>
                  <div style={{ fontSize: 'var(--font-lg)', fontWeight: 700, marginBottom: '8px' }}>配对码</div>
                  <div style={{ fontSize: '24px', fontFamily: 'monospace', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', marginBottom: '12px' }}>{pairingResult}</div>
                  <button onClick={() => { setShowPairingForm(false); setPairingResult('') }} style={btnSaveStyle}>关闭</button>
                </div>
              ) : (
                <>
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>设备名称</label>
                    <input value={pairingForm.device_name} onInput={(e) => setPairingForm(prev => ({ ...prev, device_name: (e.target as HTMLInputElement).value }))} placeholder="我的手机" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                    <button onClick={() => setShowPairingForm(false)} style={btnCancelStyle}>取消</button>
                    <button onClick={startPairing} disabled={pairingLoading} style={btnSaveStyle}>{pairingLoading ? '配对中...' : '生成配对码'}</button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

// --- 样式常量 ---


const btnCancelStyle: any = {
  padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)',
  background: 'transparent', color: 'var(--text-secondary)',
  fontSize: 'var(--font-sm)', border: '1px solid var(--border)', cursor: 'pointer',
}
const btnSaveStyle: any = {
  padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)',
  background: 'var(--accent)', color: '#fff',
  fontSize: 'var(--font-sm)', fontWeight: 600, border: 'none', cursor: 'pointer',
}

const sectionTitleStyle: any = {
  fontSize: "var(--font-xl)",
  fontWeight: 700,
  color: "var(--text-primary)",
  marginBottom: "20px",
}

const formGroupStyle: any = {
  marginBottom: "20px",
}

const labelStyle: any = {
  display: "block",
  fontSize: "var(--font-sm)",
  color: "var(--text-primary)",
  fontWeight: 500,
  marginBottom: "8px",
}

const inputStyle: any = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--border)",
  background: "var(--bg-card)",
  color: "var(--text-primary)",
  fontSize: "var(--font-sm)",
  outline: "none",
}

const cardStyle: any = {
  padding: "12px 16px",
  borderRadius: "var(--radius-lg)",
  background: "var(--bg-secondary)",
  border: "1px solid var(--border)",
  marginBottom: "8px",
}

const btnPrimaryStyle: any = {
  padding: "8px 16px",
  borderRadius: "var(--radius-md)",
  background: "var(--accent)",
  color: "#fff",
  border: "none",
  cursor: "pointer",
  fontSize: "var(--font-sm)",
  fontWeight: 500,
}

const btnDangerStyle: any = {
  padding: "4px 12px",
  borderRadius: "var(--radius-md)",
  background: "rgba(255,95,87,0.1)",
  color: "#FF5F57",
  border: "1px solid rgba(255,95,87,0.3)",
  cursor: "pointer",
  fontSize: "var(--font-xs)",
}

const emptyStyle: any = {
  padding: "24px",
  textAlign: "center",
  color: "var(--text-secondary)",
  fontSize: "var(--font-sm)",
}

const errorStyle: any = {
  padding: "8px 12px",
  marginBottom: "16px",
  borderRadius: "var(--radius-md)",
  background: "rgba(255,95,87,0.1)",
  color: "#FF5F57",
  fontSize: "var(--font-sm)",
}
