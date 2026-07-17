// 仪表盘组件
// 顶部统计卡片 + Provider 健康 + 定时任务 + 同步设备 + IM 渠道 + 审计日志
import { useState, useEffect } from 'preact/hooks'
import { apiGet, apiPost } from '../lib/api'
import { useGlobalState } from '../lib/store'

// 统计卡片数据
interface StatItem {
  label: string
  value: number | string
  icon: string
  color: string
}

// Provider 健康项
interface ProviderHealth {
  name?: string
  provider?: string
  status?: string
  healthy?: boolean | null
  latency_ms?: number | null
  message?: string
  enabled?: boolean
  consecutive_failures?: number
  last_check?: string
}

// v2.3.0 Phase 3-D: 健康检查全局状态 + 汇总
interface HealthSummary {
  total?: number
  healthy?: number
  degraded?: number
  down?: number
  disabled?: number
}

interface HealthMonitorStatus {
  running?: boolean
  interval?: number
  last_check?: string | null
}

// 定时任务项
interface SchedulerJob {
  id?: string | number
  name?: string
  type?: string
  next_run?: string
  last_run?: string
  status?: string
  enabled?: boolean
  schedule?: string
}

// 同步设备项
interface SyncDevice {
  id?: string | number
  name?: string
  device_name?: string
  platform?: string
  status?: string
  last_seen?: string
  paired_at?: string
}

// IM 渠道项
interface IMChannel {
  id?: string | number
  name?: string
  type?: string
  platform?: string
  status?: string
  enabled?: boolean
}

// 审计日志项
interface AuditLog {
  id?: string | number
  action?: string
  resource?: string
  success?: boolean
  created_at?: string
  input_summary?: string
  output_summary?: string
}

// 通用骨架屏
function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3 rounded"
          style={{
            background: 'var(--bg-secondary)',
            width: `${100 - i * 12}%`,
          }}
        />
      ))}
    </div>
  )
}

// 卡片容器
function Card({
  title,
  icon,
  children,
  loading,
}: {
  title: string
  icon: string
  children: preact.ComponentChildren
  loading?: boolean
}) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-md)',
        border: '1px solid var(--border)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <h3
          className="font-semibold text-sm"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h3>
      </div>
      <div className="flex-1">{loading ? <Skeleton lines={3} /> : children}</div>
    </div>
  )
}

export default function Dashboard() {
  // 统计数据
  const [stats, setStats] = useState<StatItem[]>([
    { label: '对话总数', value: '—', icon: '💬', color: '#FF8C42' },
    { label: '记忆总数', value: '—', icon: '🧠', color: '#FF6B8A' },
    { label: '技能总数', value: '—', icon: '⚡', color: '#52C41A' },
    { label: '角色总数', value: '—', icon: '🎭', color: '#3B82F6' },
  ])
  const [statsLoading, setStatsLoading] = useState(true)

  // 各模块数据
  const [providers, setProviders] = useState<ProviderHealth[]>([])
  const [jobs, setJobs] = useState<SchedulerJob[]>([])
  const [devices, setDevices] = useState<SyncDevice[]>([])
  const [channels, setChannels] = useState<IMChannel[]>([])
  const [audits, setAudits] = useState<AuditLog[]>([])
  const [providersLoading, setProvidersLoading] = useState(true)
  const [jobsLoading, setJobsLoading] = useState(true)
  const [devicesLoading, setDevicesLoading] = useState(true)
  const [channelsLoading, setChannelsLoading] = useState(true)
  const [auditsLoading, setAuditsLoading] = useState(true)

  // v2.3.0 Phase 3-D: 健康检查全局开关 + 汇总 + 操作状态
  // v2.3.1: 改用 selector 模式订阅, 仅订阅 health 切片避免全组件树重渲染
  const health = useGlobalState((s) => s.health)
  const [globalEnabled, setGlobalEnabled] = useState<boolean>(true)
  const [healthSummary, setHealthSummary] = useState<HealthSummary>({})
  const [monitorStatus, setMonitorStatus] = useState<HealthMonitorStatus>({})
  const [globalActing, setGlobalActing] = useState(false)
  const [actingProvider, setActingProvider] = useState<string | null>(null)

  // 加载统计
  useEffect(() => {
    let cancelled = false
    async function loadStats() {
      setStatsLoading(true)
      // 各接口并发,各自容错
      const [conv, mem, skl, per] = await Promise.all([
        apiGet<any>('/chat/conversations').catch(() => null),
        apiGet<any>('/memory').catch(() => null),
        apiGet<any>('/skills').catch(() => null),
        apiGet<any>('/persona').catch(() => null),
      ])
      if (cancelled) return
      const convCount = Array.isArray(conv) ? conv.length : conv?.total ?? conv?.count ?? (conv?.items?.length || 0)
      const memCount = Array.isArray(mem) ? mem.length : mem?.total ?? mem?.count ?? (mem?.items?.length || 0)
      const sklCount = Array.isArray(skl) ? skl.length : skl?.total ?? skl?.count ?? (skl?.items?.length || 0)
      const perCount = Array.isArray(per) ? per.length : per?.total ?? per?.count ?? (per?.items?.length || 0)
      setStats([
        { label: '对话总数', value: convCount || 0, icon: '💬', color: '#FF8C42' },
        { label: '记忆总数', value: memCount || 0, icon: '🧠', color: '#FF6B8A' },
        { label: '技能总数', value: sklCount || 0, icon: '⚡', color: '#52C41A' },
        { label: '角色总数', value: perCount || 0, icon: '🎭', color: '#3B82F6' },
      ])
      setStatsLoading(false)
    }
    loadStats()
    return () => {
      cancelled = true
    }
  }, [])

  // 加载 Provider 健康 (v2.3.0 Phase 3-D: 改用 /health-check/status 获取全局开关 + 汇总)
  const loadHealthStatus = () => {
    apiGet<any>('/health-check/status')
      .then((data) => {
        const list: ProviderHealth[] = Array.isArray(data?.providers)
          ? data.providers
          : Array.isArray(data)
            ? data
            : []
        setProviders(list)
        setGlobalEnabled(data?.global_enabled !== false)
        setHealthSummary(data?.summary || {})
        setMonitorStatus(data?.monitor || {})
      })
      .catch(() => {
        // 回退到旧端点 (向后兼容)
        apiGet<any>('/health-check/providers')
          .then((d) => {
            const list = Array.isArray(d)
              ? d
              : d?.providers || d?.items || d?.data || []
            setProviders(list)
          })
          .catch(() => {
            setProviders([])
          })
      })
      .finally(() => {
        setProvidersLoading(false)
      })
  }

  useEffect(() => {
    loadHealthStatus()
  }, [])

  // v2.3.0 Phase 3-D: 监听 SSE 健康事件, 实时合并全局状态到本地展示
  useEffect(() => {
    const sseHealth = health
    // 全局开关 (SSE 优先)
    if (sseHealth.globalEnabled !== undefined) {
      setGlobalEnabled(sseHealth.globalEnabled)
    }
    // 合并单 Provider 实时状态 (SSE 覆盖本地)
    if (sseHealth.providers && Object.keys(sseHealth.providers).length > 0) {
      setProviders((prev) =>
        prev.map((p) => {
          const name = p.name || p.provider || ''
          const sseEntry = sseHealth.providers[name]
          if (!sseEntry) return p
          return {
            ...p,
            name,
            healthy: sseEntry.healthy,
            enabled: sseEntry.enabled,
            last_check: sseEntry.lastCheck,
          }
        })
      )
    }
  }, [health])

  // 加载定时任务
  useEffect(() => {
    let cancelled = false
    apiGet<any>('/scheduler/jobs')
      .then((data) => {
        if (cancelled) return
        const list = Array.isArray(data) ? data : data?.jobs || data?.items || []
        setJobs(list.slice(0, 6))
      })
      .catch(() => {
        if (!cancelled) setJobs([])
      })
      .finally(() => {
        if (!cancelled) setJobsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 加载同步设备
  useEffect(() => {
    let cancelled = false
    apiGet<any>('/sync/devices')
      .then((data) => {
        if (cancelled) return
        const list = Array.isArray(data) ? data : data?.devices || data?.items || []
        setDevices(list)
      })
      .catch(() => {
        if (!cancelled) setDevices([])
      })
      .finally(() => {
        if (!cancelled) setDevicesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 加载 IM 渠道
  useEffect(() => {
    let cancelled = false
    apiGet<any>('/channel/list')
      .then((data) => {
        if (cancelled) return
        const list = Array.isArray(data) ? data : data?.channels || data?.items || []
        setChannels(list)
      })
      .catch(() => {
        if (!cancelled) setChannels([])
      })
      .finally(() => {
        if (!cancelled) setChannelsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 加载审计日志(最近 5 条)
  useEffect(() => {
    let cancelled = false
    apiGet<any>('/audit')
      .then((data) => {
        if (cancelled) return
        const list = Array.isArray(data) ? data : data?.logs || data?.items || []
        setAudits(list.slice(0, 5))
      })
      .catch(() => {
        if (!cancelled) setAudits([])
      })
      .finally(() => {
        if (!cancelled) setAuditsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // v2.3.0 Phase 3-D: 全局开关
  const handleGlobalToggle = async () => {
    setGlobalActing(true)
    try {
      if (globalEnabled) {
        await apiPost('/health-check/stop')
        setGlobalEnabled(false)
      } else {
        await apiPost('/health-check/start', { interval_seconds: 300 })
        setGlobalEnabled(true)
      }
      loadHealthStatus()
    } catch {
      /* ignore */
    } finally {
      setGlobalActing(false)
    }
  }

  // v2.3.0 Phase 3-D: 单 Provider 测试
  const handleTestProvider = async (name: string) => {
    setActingProvider(name)
    try {
      await apiPost(`/health-check/providers/${encodeURIComponent(name)}/test`)
      loadHealthStatus()
    } catch {
      /* ignore */
    } finally {
      setActingProvider(null)
    }
  }

  // v2.3.0 Phase 3-D: 单 Provider 启停
  const handleToggleProvider = async (name: string, currentEnabled: boolean) => {
    setActingProvider(name)
    try {
      await apiPost(`/health-check/providers/${encodeURIComponent(name)}/toggle`, {
        enabled: !currentEnabled,
      })
      // 乐观更新本地状态
      setProviders((prev) =>
        prev.map((p) =>
          (p.name || p.provider || '') === name ? { ...p, enabled: !currentEnabled } : p
        )
      )
      loadHealthStatus()
    } catch {
      /* ignore */
    } finally {
      setActingProvider(null)
    }
  }

  return (
    <div
      className="rounded-2xl p-5 flex flex-col gap-5"
      style={{
        background: 'var(--bg-primary)',
        boxShadow: 'var(--shadow-lg)',
        border: '1px solid var(--border)',
      }}
    >
      <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        📊 仪表盘
      </h2>

      {/* 顶部统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-xl p-4 flex items-center gap-3"
            style={{
              background: 'var(--bg-card)',
              boxShadow: 'var(--shadow-md)',
              border: '1px solid var(--border)',
            }}
          >
            <div
              className="flex items-center justify-center w-12 h-12 rounded-xl text-2xl flex-shrink-0"
              style={{ background: `${s.color}22` }}
            >
              {statsLoading ? '⏳' : s.icon}
            </div>
            <div className="min-w-0">
              <div
                className="text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                {s.label}
              </div>
              {statsLoading ? (
                <div
                  className="h-6 mt-1 rounded"
                  style={{ background: 'var(--bg-secondary)', width: 60 }}
                />
              ) : (
                <div
                  className="text-2xl font-bold"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {s.value}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 卡片网格(2列) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Provider 健康状态 (v2.3.0 Phase 3-D: 全局开关 + 测试/启停按钮) */}
        <Card title="Provider 健康状态" icon="🔌" loading={providersLoading}>
          {/* 全局开关 + 汇总 */}
          <div
            className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg mb-2"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: globalEnabled ? '#52C41A' : '#D1D5DB' }}
              />
              <span
                className="text-sm font-semibold"
                style={{ color: 'var(--text-primary)' }}
              >
                全局健康检查
              </span>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {globalEnabled ? '已开启' : '已停止'}
                {globalEnabled && monitorStatus.running === false && ' (监控未运行)'}
              </span>
            </div>
            <button
              onClick={handleGlobalToggle}
              disabled={globalActing}
              className="px-2 py-1 rounded text-xs font-semibold disabled:opacity-50 transition-colors"
              style={{
                background: globalEnabled ? '#FEE2E2' : '#DCFCE7',
                color: globalEnabled ? '#DC2626' : '#16A34A',
              }}
            >
              {globalActing ? '...' : globalEnabled ? '停止' : '启动'}
            </button>
          </div>

          {/* 汇总统计 */}
          {(healthSummary.total != null && healthSummary.total > 0) && (
            <div className="flex items-center gap-3 text-xs px-1 mb-2" style={{ color: 'var(--text-secondary)' }}>
              <span>共 {healthSummary.total}</span>
              <span style={{ color: '#52C41A' }}>✓ {healthSummary.healthy ?? 0}</span>
              <span style={{ color: '#F59E0B' }}>⚠ {healthSummary.degraded ?? 0}</span>
              <span style={{ color: '#EF4444' }}>✗ {healthSummary.down ?? 0}</span>
              <span>⏸ {healthSummary.disabled ?? 0}</span>
            </div>
          )}

          {providers.length === 0 ? (
            <div className="text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
              暂无 Provider
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {providers.map((p, idx) => {
                const name = p.name || p.provider || `Provider ${idx + 1}`
                const pEnabled = p.enabled !== false
                const healthy = p.healthy ?? (p.status === 'healthy' || p.status === 'ok')
                const acting = actingProvider === name
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg"
                    style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span
                        className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                        style={{
                          background: !pEnabled
                            ? '#D1D5DB'
                            : healthy
                              ? '#52C41A'
                              : '#EF4444',
                        }}
                      />
                      <span
                        className="text-sm truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {name}
                      </span>
                      {!pEnabled && (
                        <span
                          className="text-xs px-1.5 py-0.5 rounded-full"
                          style={{ background: '#F3F4F6', color: '#6B7280' }}
                        >
                          已禁用
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <div
                        className="flex items-center gap-2 text-xs mr-1"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {p.latency_ms != null && <span>{p.latency_ms}ms</span>}
                        <span>{healthy ? '正常' : p.status || '异常'}</span>
                      </div>
                      {/* 测试按钮 */}
                      <button
                        onClick={() => handleTestProvider(name)}
                        disabled={acting}
                        title="测试连通性"
                        className="px-2 py-1 rounded text-xs bg-blue-100 text-blue-600 hover:bg-blue-200 disabled:opacity-50 transition-colors"
                      >
                        {acting ? '...' : '测试'}
                      </button>
                      {/* 启停按钮 */}
                      <button
                        onClick={() => handleToggleProvider(name, pEnabled)}
                        disabled={acting}
                        title={pEnabled ? '禁用监控' : '启用监控'}
                        className="px-2 py-1 rounded text-xs disabled:opacity-50 transition-colors"
                        style={{
                          background: pEnabled ? '#FEF3C7' : '#DCFCE7',
                          color: pEnabled ? '#D97706' : '#16A34A',
                        }}
                      >
                        {pEnabled ? '停' : '启'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* 定时任务 */}
        <Card title="定时任务" icon="⏰" loading={jobsLoading}>
          {jobs.length === 0 ? (
            <div className="text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
              暂无定时任务
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {jobs.map((j, idx) => (
                <div
                  key={j.id ?? idx}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                >
                  <div className="min-w-0">
                    <div
                      className="text-sm truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {j.name || j.type || `任务 ${j.id ?? idx + 1}`}
                    </div>
                    {j.schedule && (
                      <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {j.schedule}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                    {j.next_run && (
                      <div>下次: {new Date(j.next_run).toLocaleString('zh-CN')}</div>
                    )}
                    <div>{j.enabled === false ? '已禁用' : j.status || '已启用'}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 同步设备 */}
        <Card title="同步设备" icon="📱" loading={devicesLoading}>
          {devices.length === 0 ? (
            <div className="text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
              暂无已配对设备
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {devices.map((d, idx) => (
                <div
                  key={d.id ?? idx}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                >
                  <div className="min-w-0">
                    <div
                      className="text-sm truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {d.name || d.device_name || `设备 ${d.id ?? idx + 1}`}
                    </div>
                    {d.platform && (
                      <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {d.platform}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-right" style={{ color: 'var(--text-secondary)' }}>
                    <div>{d.status || '未知'}</div>
                    {d.last_seen && (
                      <div>{new Date(d.last_seen).toLocaleDateString('zh-CN')}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* IM 渠道 */}
        <Card title="IM 渠道" icon="📨" loading={channelsLoading}>
          {channels.length === 0 ? (
            <div className="text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
              暂无已配置渠道
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {channels.map((c, idx) => (
                <div
                  key={c.id ?? idx}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                      style={{
                        background: c.enabled === false ? '#D1D5DB' : '#52C41A',
                      }}
                    />
                    <span
                      className="text-sm truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {c.name || `渠道 ${c.id ?? idx + 1}`}
                    </span>
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {c.type || c.platform || ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 审计日志摘要(跨两列) */}
        <Card title="审计日志(最近 5 条)" icon="📋" loading={auditsLoading}>
          {audits.length === 0 ? (
            <div className="text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
              暂无审计日志
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {audits.map((a, idx) => (
                <div
                  key={a.id ?? idx}
                  className="flex items-start gap-2 px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                >
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                    style={{ background: a.success === false ? '#EF4444' : '#52C41A' }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-sm font-medium"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {a.action || '未知操作'}
                      </span>
                      {a.resource && (
                        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                          · {a.resource}
                        </span>
                      )}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {a.created_at
                        ? new Date(a.created_at).toLocaleString('zh-CN')
                        : ''}
                      {a.input_summary ? ` · ${a.input_summary.slice(0, 60)}` : ''}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
