// 鍙屾爮璁剧疆闈㈡澘 - macOS 椋庢牸, 宸︽爮鍒嗙被鍒楄〃 + 鍙虫爮琛ㄥ崟
import { useState, useEffect } from "preact/hooks"
import { apiGet, apiPost, apiPut, apiDelete } from "../lib/api"
import type { ProviderInfo, Persona, Channel, SchedulerJob } from "../lib/types"
import pkg from '../../package.json'
import UpdateChecker from "./UpdateChecker"

// 璁剧疆鍒嗙被
const CATEGORIES = [
  { id: "general", label: "閫氱敤", icon: "鈿欙笍" },
  { id: "provider", label: "Provider", icon: "馃攲" },
  { id: "persona", label: "瑙掕壊", icon: "馃幁" },
  { id: "memory", label: "璁板繂", icon: "馃" },
  { id: "skills", label: "鎶€鑳?, icon: "鈿? },
  { id: "sync", label: "鍚屾", icon: "馃攧" },
  { id: "channel", label: "娓犻亾", icon: "馃摗" },
  { id: "security", label: "瀹夊叏", icon: "馃敀" },
  { id: "multimodal", label: "澶氭ā鎬?, icon: "馃幀" },
  { id: "os", label: "OS鎰熺煡", icon: "馃枼锔? },
  { id: "scheduler", label: "璋冨害", icon: "鈴? },
  { id: "mcp", label: "MCP", icon: "馃敡" },
  { id: "about", label: "鍏充簬", icon: "鈩癸笍" },
]

const THEMES = [
  { id: "warm-orange", label: "鏆栨", color: "#FF8C42" },
  { id: "soft-pink", label: "鏌旂矇", color: "#FF6B8A" },
  { id: "cream-beige", label: "濂舵补", color: "#D4A574" },
]

export default function Settings() {
  const [activeCategory, setActiveCategory] = useState("general")
  const [theme, setTheme] = useState(
    () => localStorage.getItem("app-theme") || "warm-orange"
  )

  // 鍚勫垎绫荤殑鏁版嵁鐘舵€?
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [jobs, setJobs] = useState<SchedulerJob[]>([])
  const [syncDevices, setSyncDevices] = useState<any[]>([])
  const [mcpServers, setMcpServers] = useState<any[]>([])
  const [mcpTools, setMcpTools] = useState<any[]>([])
  const [skills, setSkills] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  // 娓犻亾娣诲姞琛ㄥ崟
  const [showChannelForm, setShowChannelForm] = useState(false)
  const [channelForm, setChannelForm] = useState({ channel_type: 'discord', name: '', config_json: '{}' })
  const [savingChannel, setSavingChannel] = useState(false)
  // 璋冨害浠诲姟娣诲姞琛ㄥ崟
  const [showJobForm, setShowJobForm] = useState(false)
  const [jobForm, setJobForm] = useState({ name: '', cron_expr: '0 * * * *', action_type: 'ping', action_params: '{}' })
  const [savingJob, setSavingJob] = useState(false)
  // MCP 鏈嶅姟鍣ㄦ坊鍔犺〃鍗?
  const [showMcpServerForm, setShowMcpServerForm] = useState(false)
  const [mcpServerForm, setMcpServerForm] = useState({ name: '', transport: 'stdio', command: '', args: '' })
  const [savingMcpServer, setSavingMcpServer] = useState(false)
  // 鍚屾璁惧閰嶅琛ㄥ崟
  const [showPairingForm, setShowPairingForm] = useState(false)
  const [pairingForm, setPairingForm] = useState({ device_name: '' })
  const [pairingResult, setPairingResult] = useState('')
  const [pairingLoading, setPairingLoading] = useState(false)

  // Provider 娣诲姞琛ㄥ崟
  const [showProviderForm, setShowProviderForm] = useState(false)
  const [providerForm, setProviderForm] = useState({ provider: '', api_key: '', api_base: '', model: '' })
  const [savingProvider, setSavingProvider] = useState(false)
  const [error, setError] = useState("")

  // 閫氱敤璁剧疆
  const [language, setLanguage] = useState("zh-CN")
  const [windowOnTop, setWindowOnTop] = useState(false)
  const [autoStart, setAutoStart] = useState(false)

  // 璁板繂璁剧疆
  const [memoryLayers, setMemoryLayers] = useState(3)
  const [compressThreshold, setCompressThreshold] = useState(100)
  const [spongeMode, setSpongeMode] = useState(true)
  const [blackholeMode, setBlackholeMode] = useState(false)

  // 瀹夊叏璁剧疆
  const [aclRules, setAclRules] = useState("")
  const [injectionGuard, setInjectionGuard] = useState(true)
  const [keyRotationDays, setKeyRotationDays] = useState(30)

  // 澶氭ā鎬佽缃?
  const [visionEnabled, setVisionEnabled] = useState(true)
  const [asrEnabled, setAsrEnabled] = useState(false)
  const [ttsEnabled, setTtsEnabled] = useState(false)
  const [videoAnalysisEnabled, setVideoAnalysisEnabled] = useState(false)
  const [asrModel, setAsrModel] = useState("whisper-1")
  const [ttsVoice, setTtsVoice] = useState("alloy")

  // OS 鎰熺煡璁剧疆
  const [clipboardWatch, setClipboardWatch] = useState(false)
  const [fileWatch, setFileWatch] = useState(false)
  const [screenSense, setScreenSense] = useState(false)
  const [trayEnabled, setTrayEnabled] = useState(true)
  const [watchPaths, setWatchPaths] = useState("")

  // 鍒囨崲涓婚
  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme)
    localStorage.setItem("app-theme", newTheme)
    document.documentElement.dataset.theme = newTheme
  }

  // 鍔犺浇鏁版嵁
  const loadData = async (category: string) => {
    setLoading(true)
    setError("")
    try {
      switch (category) {
        case "provider":
          setProviders(await apiGet<ProviderInfo[]>("/providers"))
          break
        case "persona":
          setPersonas(await apiGet<Persona[]>("/persona"))
          break
        case "channel":
          setChannels(await apiGet<Channel[]>("/channel/list"))
          break
        case "scheduler":
          setJobs(await apiGet<SchedulerJob[]>("/scheduler/jobs"))
          break
        case "sync":
          setSyncDevices(await apiGet<any[]>("/sync/devices"))
          break
case "mcp":
          setMcpServers(await apiGet<any[]>("/mcp/servers"))
          setMcpTools(await apiGet<any[]>("/mcp/tools"))
          break
        case "skills":
          setSkills(await apiGet<any[]>("/skills"))
          break
      }
    } catch (e: any) {
      setError(e.message || "鍔犺浇澶辫触")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData(activeCategory)
  }, [activeCategory])

  // --- 鎿嶄綔澶勭悊 ---

  // 淇濆瓨 Provider 閰嶇疆
  const saveProvider = async () => {
    if (!providerForm.provider.trim() || !providerForm.api_key.trim()) {
      setError('璇烽€夋嫨 Provider 骞惰緭鍏?API Key')
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
      setError(e?.message || '淇濆瓨 Provider 澶辫触')
    } finally {
      setSavingProvider(false)
    }
  }

  // 淇濆瓨娓犻亾
  const saveChannel = async () => {
    if (!channelForm.name.trim()) { setError('璇疯緭鍏ユ笭閬撳悕绉?); return }
    setSavingChannel(true); setError('')
    try {
      let config = {}
      try { config = JSON.parse(channelForm.config_json) } catch {}
      await apiPost('/channel', { channel_type: channelForm.channel_type, name: channelForm.name.trim(), config })
      setShowChannelForm(false); setChannelForm({ channel_type: 'discord', name: '', config_json: '{}' })
      await loadData('channel')
    } catch (e: any) { setError(e?.message || '娣诲姞娓犻亾澶辫触') }
    finally { setSavingChannel(false) }
  }
  // 淇濆瓨璋冨害浠诲姟
  const saveJob = async () => {
    if (!jobForm.name.trim()) { setError('璇疯緭鍏ヤ换鍔″悕绉?); return }
    setSavingJob(true); setError('')
    try {
      let params = {}
      try { params = JSON.parse(jobForm.action_params) } catch {}
      await apiPost('/scheduler/jobs', { name: jobForm.name.trim(), cron_expr: jobForm.cron_expr, action: { type: jobForm.action_type, params }, enabled: true })
      setShowJobForm(false); setJobForm({ name: '', cron_expr: '0 * * * *', action_type: 'ping', action_params: '{}' })
      await loadData('scheduler')
    } catch (e: any) { setError(e?.message || '娣诲姞浠诲姟澶辫触') }
    finally { setSavingJob(false) }
  }
  // 淇濆瓨 MCP 鏈嶅姟鍣?
  const saveMcpServer = async () => {
    if (!mcpServerForm.name.trim() || !mcpServerForm.command.trim()) { setError('璇峰～鍐欐湇鍔″櫒鍚嶇О鍜屽懡浠?); return }
    setSavingMcpServer(true); setError('')
    try {
      await apiPost('/mcp/servers', { name: mcpServerForm.name.trim(), transport: mcpServerForm.transport, command: mcpServerForm.command.trim(), args: mcpServerForm.args ? mcpServerForm.args.split(',').map(s => s.trim()) : [] })
      setShowMcpServerForm(false); setMcpServerForm({ name: '', transport: 'stdio', command: '', args: '' })
      await loadData('mcp')
    } catch (e: any) { setError(e?.message || '娣诲姞鏈嶅姟鍣ㄥけ璐?) }
    finally { setSavingMcpServer(false) }
  }
  // 鍙戣捣璁惧閰嶅
  const startPairing = async () => {
    if (!pairingForm.device_name.trim()) { setError('璇疯緭鍏ヨ澶囧悕绉?); return }
    setPairingLoading(true); setPairingResult(''); setError('')
    try {
      const result = await apiPost<any>('/sync/pairing/initiate', { device_name: pairingForm.device_name.trim() })
      setPairingResult(result?.pairing_code || '閰嶅鐮佸凡鐢熸垚')
      setPairingForm({ device_name: '' })
      await loadData('sync')
    } catch (e: any) { setError(e?.message || '閰嶅澶辫触') }
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

  const deleteJob = async (id: number) => {
    try {
      await apiDelete(`/scheduler/jobs/${id}`)
      setJobs(jobs.filter((j) => j.id !== id))
    } catch (e: any) {
      setError(e.message)
    }
  }

  const toggleSkill = async (id: number, enabled: boolean) => {
    try {
      await apiPut(`/skills/${id}`, { enabled: !enabled })
      setSkills(skills.map((s) => (s.id === id ? { ...s, enabled: !enabled } : s)))
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

  const deleteMcpServer = async (name: string) => {
    try {
      await apiDelete(`/mcp/servers/${name}`)
      setMcpServers(mcpServers.filter((s) => s.name !== name))
    } catch (e: any) {
      setError(e.message)
    }
  }

  // --- 娓叉煋鍚勫垎绫婚潰鏉?---

  const renderPanel = () => {
    if (loading) {
      return <div style={{ padding: "40px", textAlign: "center", color: "var(--text-secondary)" }}>鍔犺浇涓?..</div>
    }

    switch (activeCategory) {
      case "general":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>閫氱敤璁剧疆</h2>
            {error && <div style={errorStyle}>{error}</div>}

            {/* 涓婚鍒囨崲 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>涓婚</label>
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

            {/* 璇█ */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>璇█</label>
              <select
                value={language}
                onChange={(e) => setLanguage((e.target as HTMLSelectElement).value)}
                style={inputStyle}
              >
                <option value="zh-CN">绠€浣撲腑鏂?/option>
                <option value="en-US">English</option>
              </select>
            </div>

            {/* 绐楀彛缃《 */}
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={windowOnTop} onChange={(e) => setWindowOnTop((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                绐楀彛缃《
              </label>
            </div>

            {/* 寮€鏈鸿嚜鍚?*/}
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={autoStart} onChange={(e) => setAutoStart((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                寮€鏈鸿嚜鍚姩
              </label>
            </div>
          </div>
        )

      case "provider":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>Provider 绠＄悊</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setProviderForm({ provider: providers[0]?.name || "openai", api_key: "", api_base: "", model: "" }); setShowProviderForm(true); setError("") }}>+ 娣诲姞 Provider</button>
            </div>
            <div>
              {providers.length === 0 && <div style={emptyStyle}>鏆傛棤 Provider</div>}
              {providers.map((p) => (
                <div key={p.name} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        妯″瀷: {p.supported_models?.join(", ") || "鏈煡"}
                      </div>
                    </div>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      fontSize: "var(--font-xs)",
                      background: p.available ? "rgba(40,200,64,0.15)" : "rgba(255,95,87,0.15)",
                      color: p.available ? "#28C840" : "#FF5F57",
                    }}>
                      {p.available ? "鍙敤" : "涓嶅彲鐢?}
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
            <h2 style={sectionTitleStyle}>瑙掕壊绠＄悊</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { document.querySelector('[data-nav="persona"]')?.dispatchEvent(new Event("click")); setError("") }}>+ 鍒涘缓瑙掕壊</button>
            </div>
            <div>
              {personas.length === 0 && <div style={emptyStyle}>鏆傛棤瑙掕壊</div>}
              {personas.map((p) => (
                <div key={p.id} style={cardStyle}>
                  <div className="flex items-center gap-3">
                    <span style={{ fontSize: "24px" }}>{p.avatar || "馃幁"}</span>
                    <div className="flex-1">
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        {p.soul?.slice(0, 60) || "鏆傛棤鎻忚堪"}
                      </div>
                    </div>
                    {p.is_active && (
                      <span style={{ fontSize: "var(--font-xs)", color: "var(--accent)", fontWeight: 600 }}>褰撳墠</span>
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
            <h2 style={sectionTitleStyle}>璁板繂璁剧疆</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={formGroupStyle}>
              <label style={labelStyle}>璁板繂灞傛暟: {memoryLayers}</label>
              <input type="range" min="1" max="5" value={memoryLayers}
                onChange={(e) => setMemoryLayers(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>鍘嬬缉闃堝€?鏉?: {compressThreshold}</label>
              <input type="range" min="50" max="500" step="10" value={compressThreshold}
                onChange={(e) => setCompressThreshold(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={spongeMode} onChange={(e) => setSpongeMode((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                娴风坏妯″紡(鑷姩鍚告敹淇℃伅)
              </label>
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>
                <input type="checkbox" checked={blackholeMode} onChange={(e) => setBlackholeMode((e.target as HTMLInputElement).checked)} style={{ marginRight: "8px" }} />
                榛戞礊妯″紡(娣卞害鍘嬬缉)
              </label>
            </div>
          </div>
        )

      case "skills":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>鎶€鑳界鐞?/h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div>
              {skills.length === 0 && <div style={emptyStyle}>鏆傛棤鎶€鑳?/div>}
              {skills.map((s) => (
                <div key={s.id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{s.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>{s.description}</div>
                    </div>
                    <label style={{ cursor: "pointer" }}>
                      <input type="checkbox" checked={s.enabled} onChange={() => toggleSkill(s.id, s.enabled)} />
                    </label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "sync":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>鍚屾璁剧疆</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setPairingForm({ device_name: "" }); setPairingResult(""); setShowPairingForm(true); setError("") }}>+ 閰嶅鏂拌澶?/button>
            </div>
            <div>
              {syncDevices.length === 0 && <div style={emptyStyle}>鏆傛棤閰嶅璁惧</div>}
              {syncDevices.map((d) => (
                <div key={d.device_id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{d.device_name || d.device_id}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        {d.platform || "鏈煡骞冲彴"} 路 {d.last_seen || "鏈繛鎺?}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteSyncDevice(d.device_id)}>鍒犻櫎</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "channel":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>娓犻亾绠＄悊</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setChannelForm({ channel_type: "discord", name: "", config_json: "{}" }); setShowChannelForm(true); setError("") }}>+ 娣诲姞娓犻亾</button>
            </div>
            <div>
              {channels.length === 0 && <div style={emptyStyle}>鏆傛棤娓犻亾</div>}
              {channels.map((c) => (
                <div key={c.id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{c.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        绫诲瀷: {c.channel_type} 路 {c.enabled ? "宸插惎鐢? : "宸茬鐢?}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteChannel(c.id)}>鍒犻櫎</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "security":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>瀹夊叏璁剧疆</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={formGroupStyle}>
              <label style={labelStyle}>ACL 瑙勫垯(JSON 鏍煎紡)</label>
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
                娉ㄥ叆闃叉姢
              </label>
            </div>
            <div style={formGroupStyle}>
              <label style={labelStyle}>瀵嗛挜杞崲鍛ㄦ湡(澶?: {keyRotationDays}</label>
              <input type="range" min="7" max="90" value={keyRotationDays}
                onChange={(e) => setKeyRotationDays(parseInt((e.target as HTMLInputElement).value))}
                style={{ width: "100%" }} />
            </div>
          </div>
        )

      case "multimodal":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>澶氭ā鎬佽缃?/h2>
            {error && <div style={errorStyle}>{error}</div>}

            {/* 瑙嗚 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃柤锔?鍥惧儚鐞嗚В
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={visionEnabled}
                    onChange={(e) => setVisionEnabled((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤鍥惧儚鐞嗚В (绮樿创鍥剧墖鍚?AI 鑷姩鎻忚堪)
                </label>
              </div>
            </div>

            {/* 璇煶璇嗗埆 ASR */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃帳 璇煶璇嗗埆 (ASR)
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={asrEnabled}
                    onChange={(e) => setAsrEnabled((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤璇煶杈撳叆
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>ASR 妯″瀷</label>
                <select value={asrModel} onChange={(e) => setAsrModel((e.target as HTMLSelectElement).value)} style={inputStyle}>
                  <option value="whisper-1">Whisper-1 (OpenAI)</option>
                  <option value="whisper-large">Whisper-Large (鏈湴)</option>
                  <option value="paraformer">Paraformer (閫氫箟)</option>
                </select>
              </div>
            </div>

            {/* 璇煶鍚堟垚 TTS */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃攰 璇煶鍚堟垚 (TTS)
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={ttsEnabled}
                    onChange={(e) => setTtsEnabled((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤璇煶杈撳嚭
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>闊宠壊</label>
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

            {/* 瑙嗛鍒嗘瀽 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃帴 瑙嗛鍒嗘瀽
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={videoAnalysisEnabled}
                    onChange={(e) => setVideoAnalysisEnabled((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤瑙嗛鍒嗘瀽 (甯ф娊鍙?+ 鍥惧儚鐞嗚В)
                </label>
              </div>
            </div>
          </div>
        )

      case "os":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>OS 鎰熺煡璁剧疆</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)", marginBottom: "16px", padding: "8px 12px", background: "rgba(255,140,66,0.1)", borderRadius: "var(--radius-md)" }}>
              鈿狅笍 灞忓箷鎰熺煡娑夊強闅愮,榛樿鍏抽棴銆傛埅鍥句粎鐢ㄤ簬褰撳墠璇锋眰,涓嶆寔涔呭寲瀛樺偍銆?
            </div>

            {/* 鍓创鏉跨洃鎺?*/}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃搵 鍓创鏉跨洃鎺?
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={clipboardWatch}
                    onChange={(e) => setClipboardWatch((e.target as HTMLInputElement).checked)}
                  />
                  鐩戞帶鍓创鏉垮彉鍖?(鑷姩妫€娴嬩唬鐮?URL/鏂囨湰)
                </label>
              </div>
            </div>

            {/* 鏂囦欢澶圭洃鎺?*/}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃搧 鏂囦欢澶圭洃鎺?
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={fileWatch}
                    onChange={(e) => setFileWatch((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤鏂囦欢澶圭洃鎺?
                </label>
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>鐩戞帶璺緞 (姣忚涓€涓?</label>
                <textarea
                  value={watchPaths}
                  onChange={(e) => setWatchPaths((e.target as HTMLTextAreaElement).value)}
                  placeholder={"C:\\Users\\Documents\nD:\\Projects"}
                  style={{ ...inputStyle, minHeight: "60px", fontFamily: "monospace" }}
                />
              </div>
            </div>

            {/* 灞忓箷鎰熺煡 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃枼锔?灞忓箷瀹炴椂鎰熺煡
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={screenSense}
                    onChange={(e) => setScreenSense((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤灞忓箷鎰熺煡 (鎴浘涓嶅瓨鍌?浠呯敤浜庡綋鍓嶈姹?
                </label>
              </div>
            </div>

            {/* 绯荤粺鎵樼洏 */}
            <div style={cardStyle}>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px" }}>
                馃搶 绯荤粺鎵樼洏
              </div>
              <div style={formGroupStyle}>
                <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={trayEnabled}
                    onChange={(e) => setTrayEnabled((e.target as HTMLInputElement).checked)}
                  />
                  鍚敤绯荤粺鎵樼洏 (鏈€灏忓寲鍒版墭鐩?
                </label>
              </div>
            </div>
          </div>
        )

      case "scheduler":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>璋冨害浠诲姟</h2>
            {error && <div style={errorStyle}>{error}</div>}
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setJobForm({ name: "", cron_expr: "0 * * * *", action_type: "ping", action_params: "{}" }); setShowJobForm(true); setError("") }}>+ 娣诲姞浠诲姟</button>
            </div>
            <div>
              {jobs.length === 0 && <div style={emptyStyle}>鏆傛棤瀹氭椂浠诲姟</div>}
              {jobs.map((j) => (
                <div key={j.id} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{j.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        Cron: {j.cron_expr} 路 {j.enabled ? "鍚敤" : "绂佺敤"}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteJob(j.id)}>鍒犻櫎</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

      case "mcp":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>MCP 绠＄悊</h2>
            {error && <div style={errorStyle}>{error}</div>}

            <h3 style={subTitleStyle}>鏈嶅姟鍣?/h3>
            <div style={{ marginBottom: "16px" }}>
              <button style={btnPrimaryStyle} onClick={() => { setMcpServerForm({ name: "", transport: "stdio", command: "", args: "" }); setShowMcpServerForm(true); setError("") }}>+ 娣诲姞鏈嶅姟鍣?/button>
            </div>
            <div>
              {mcpServers.length === 0 && <div style={emptyStyle}>鏆傛棤 MCP 鏈嶅姟鍣?/div>}
              {mcpServers.map((s) => (
                <div key={s.name} style={cardStyle}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{s.name}</div>
                      <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>
                        {s.transport || "unknown"} 路 {s.url || s.command || ""}
                      </div>
                    </div>
                    <button style={btnDangerStyle} onClick={() => deleteMcpServer(s.name)}>鍒犻櫎</button>
                  </div>
                </div>
              ))}
            </div>

            <h3 style={{ ...subTitleStyle, marginTop: "24px" }}>宸ュ叿</h3>
            <div>
              {mcpTools.length === 0 && <div style={emptyStyle}>鏆傛棤宸ュ叿</div>}
              {mcpTools.map((t, i) => (
                <div key={i} style={cardStyle}>
                  <div>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{t.name}</div>
                    <div style={{ fontSize: "var(--font-xs)", color: "var(--text-secondary)" }}>{t.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )

case "about":
        return (
          <div style={{ padding: "24px" }}>
            <h2 style={sectionTitleStyle}>鍏充簬</h2>
            <div style={cardStyle}>
              <div style={{ fontSize: "var(--font-xl)", fontWeight: 700, color: "var(--text-primary)", marginBottom: "8px" }}>
                Pangu Nebula
              </div>
              <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)", marginBottom: "16px" }}>
                鐗堟湰 {pkg.version}
              </div>
              <div style={{ fontSize: "var(--font-sm)", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                鐩樺彜鏄熶簯 - 涓€涓熀浜庡 Provider 鐨勬櫤鑳?AI 鍔╃悊骞冲彴,鏀寔瑙掕壊绠＄悊銆佽蹇嗗浘璋便€?
                铚傜兢鍗忎綔銆佹妧鑳藉競鍦恒€佸娓犻亾鎺ュ叆銆佽澶囧悓姝ョ瓑涓板瘜鍔熻兘銆?
              </div>
              <div style={{ marginTop: "16px", fontSize: "var(--font-sm)" }}>
                <a href="https://github.com" style={{ color: "var(--accent)", textDecoration: "none" }}>
                  馃摝 寮€婧愪粨搴?鈫?
                </a>
              </div>
            </div>

            {/* P0-W6.2: 鑷姩鏇存柊妫€鏌?*/}
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
      {/* 宸︽爮: 鍒嗙被鍒楄〃 */}
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

      {/* 鍙虫爮: 璁剧疆琛ㄥ崟 */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          background: "var(--bg-card)",
        }}
      >
        {renderPanel()}
      </div>
      {/* Provider 娣诲姞琛ㄥ崟寮圭獥 */}
      {showProviderForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowProviderForm(false)}>
          <div className="flex flex-col" style={{ width: '90%', maxWidth: '480px', maxHeight: '90vh', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between shrink-0" style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 娣诲姞 Provider</h3>
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
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>API Base URL (鍙€?</label>
                <input type="text" value={providerForm.api_base} onInput={(e) => setProviderForm(prev => ({ ...prev, api_base: (e.target as HTMLInputElement).value }))} placeholder="https://api.deepseek.com" style={{ ...inputStyle, width: '100%' }} />
              </div>
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 'var(--spacing-xs)' }}>榛樿妯″瀷 (鍙€?</label>
                <input type="text" value={providerForm.model} onInput={(e) => setProviderForm(prev => ({ ...prev, model: (e.target as HTMLInputElement).value }))} placeholder="deepseek-chat" style={{ ...inputStyle, width: '100%' }} />
              </div>
            </div>
            <div className="flex justify-end gap-2 shrink-0" style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', background: 'var(--bg-primary)' }}>
              <button onClick={() => setShowProviderForm(false)} style={{ padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 'var(--font-sm)', border: '1px solid var(--border)', cursor: 'pointer' }}>鍙栨秷</button>
              <button onClick={saveProvider} disabled={savingProvider} style={{ padding: '8px var(--spacing-lg)', borderRadius: 'var(--radius-md)', background: 'var(--accent)', color: '#fff', fontSize: 'var(--font-sm)', fontWeight: 600, border: 'none', cursor: 'pointer' }}>{savingProvider ? '淇濆瓨涓?..' : '淇濆瓨'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 娓犻亾娣诲姞寮圭獥 */}
      {showChannelForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowChannelForm(false)}>
          <div className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 娣诲姞娓犻亾</h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>娓犻亾绫诲瀷</label>
                <select value={channelForm.channel_type} onChange={(e) => setChannelForm(prev => ({ ...prev, channel_type: (e.target as HTMLSelectElement).value }))} style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
                  {['discord','telegram','feishu','wechat','wecom','dingtalk'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>鍚嶇О</label>
                <input value={channelForm.name} onInput={(e) => setChannelForm(prev => ({ ...prev, name: (e.target as HTMLInputElement).value }))} placeholder="鎴戠殑娓犻亾" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setShowChannelForm(false)} style={btnCancelStyle}>鍙栨秷</button>
              <button onClick={saveChannel} disabled={savingChannel} style={btnSaveStyle}>{savingChannel ? '淇濆瓨涓?..' : '淇濆瓨'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 璁惧閰嶅寮圭獥 */}
      {showPairingForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowPairingForm(false)}>
          <div className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 閰嶅鏂拌澶?/h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              {pairingResult ? (
                <div style={{ textAlign: 'center', padding: '20px' }}>
                  <div style={{ fontSize: '48px', marginBottom: '12px' }}>鉁?/div>
                  <div style={{ fontSize: 'var(--font-lg)', fontWeight: 700, marginBottom: '8px' }}>閰嶅鐮?/div>
                  <div style={{ fontSize: '24px', fontFamily: 'monospace', padding: '12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', marginBottom: '12px' }}>{pairingResult}</div>
                  <button onClick={() => { setShowPairingForm(false); setPairingResult('') }} style={btnSaveStyle}>鍏抽棴</button>
                </div>
              ) : (
                <>
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>璁惧鍚嶇О</label>
                    <input value={pairingForm.device_name} onInput={(e) => setPairingForm(prev => ({ ...prev, device_name: (e.target as HTMLInputElement).value }))} placeholder="鎴戠殑鎵嬫満" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                    <button onClick={() => setShowPairingForm(false)} style={btnCancelStyle}>鍙栨秷</button>
                    <button onClick={startPairing} disabled={pairingLoading} style={btnSaveStyle}>{pairingLoading ? '閰嶅涓?..' : '鐢熸垚閰嶅鐮?}</button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 璋冨害浠诲姟娣诲姞寮圭獥 */}
      {showJobForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowJobForm(false)}>
          <div className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 娣诲姞浠诲姟</h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>浠诲姟鍚嶇О</label>
                <input value={jobForm.name} onInput={(e) => setJobForm(prev => ({ ...prev, name: (e.target as HTMLInputElement).value }))} placeholder="姣忔棩娓呯悊" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Cron 琛ㄨ揪寮?/label>
                <input value={jobForm.cron_expr} onInput={(e) => setJobForm(prev => ({ ...prev, cron_expr: (e.target as HTMLInputElement).value }))} placeholder="0 * * * *" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setShowJobForm(false)} style={btnCancelStyle}>鍙栨秷</button>
              <button onClick={saveJob} disabled={savingJob} style={btnSaveStyle}>{savingJob ? '淇濆瓨涓?..' : '淇濆瓨'}</button>
            </div>
          </div>
        </div>
      )}

      {/* MCP 鏈嶅姟鍣ㄦ坊鍔犲脊绐?*/}
      {showMcpServerForm && (
        <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', zIndex: 1000 }} onClick={() => setShowMcpServerForm(false)}>
          <div className="flex flex-col" style={{ width: '90%', maxWidth: '420px', background: 'var(--bg-card)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-xl)', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: 'var(--spacing-lg)', borderBottom: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 'var(--font-lg)', fontWeight: 700, color: 'var(--text-primary)' }}>+ 娣诲姞 MCP 鏈嶅姟鍣?/h3>
            </div>
            <div style={{ padding: 'var(--spacing-lg)' }}>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>鏈嶅姟鍣ㄥ悕绉?/label>
                <input value={mcpServerForm.name} onInput={(e) => setMcpServerForm(prev => ({ ...prev, name: (e.target as HTMLInputElement).value }))} placeholder="my-server" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>浼犺緭鏂瑰紡</label>
                <select value={mcpServerForm.transport} onChange={(e) => setMcpServerForm(prev => ({ ...prev, transport: (e.target as HTMLSelectElement).value }))} style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
                  <option value="stdio">stdio</option><option value="sse">sse</option>
                </select>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ fontSize: 'var(--font-sm)', fontWeight: 600, display: 'block', marginBottom: '4px' }}>鍛戒护/URL</label>
                <input value={mcpServerForm.command} onInput={(e) => setMcpServerForm(prev => ({ ...prev, command: (e.target as HTMLInputElement).value }))} placeholder="python server.py" style={{ width: '100%', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setShowMcpServerForm(false)} style={btnCancelStyle}>鍙栨秷</button>
              <button onClick={saveMcpServer} disabled={savingMcpServer} style={btnSaveStyle}>{savingMcpServer ? '淇濆瓨涓?..' : '淇濆瓨'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// --- 鏍峰紡甯搁噺 ---


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

const subTitleStyle: any = {
  fontSize: "var(--font-base)",
  fontWeight: 600,
  color: "var(--text-primary)",
  marginBottom: "12px",
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


