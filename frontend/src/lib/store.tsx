// v2.3.0 Phase 0 — 前端统一状态层
//
// Preact Context + useReducer,单一 SSE 连接订阅 /events/stream,
// dispatch 到 7 类全局 state,替代各组件各自轮询。
//
// 7 类全局 state:
//   1. activePersona:     当前激活角色 + 关联网络
//   2. runningTasks:      运行中的蜂群/DAG/自动化任务
//   3. memoryEvents:      记忆图谱增量事件流 (最新 N 条)
//   4. toolExecutions:    工具调用实时状态 (pending/running/completed/failed)
//   5. health:            Provider/MCP/技能健康状态
//   6. skills_mcp:        技能/MCP 启用状态 + 市场索引
//   7. appVersion:        应用版本号 (修复"版本 v..."bug)
//
// 用法:
//   import { useGlobalState } from '../lib/store'
//   const { state, dispatch } = useGlobalState()
//   // 读取: state.health.providers
//   // 派发: dispatch({ type: 'NAVIGATE', page: 'memory' })

import { createContext, h } from 'preact'
import { useContext, useEffect, useReducer, useRef } from 'preact/hooks'
import type { JSX } from 'preact'
import { isTauri, getHandshake, getApiBase, getAuthToken } from './api'

// =========================================================================
// 类型定义
// =========================================================================

/** 进化日志条目 (来自 evolution.log.appended 事件, 前端 EvolutionPage 增量拼接) */
export interface EvolutionLogEntry {
  id?: number
  phase?: string
  status?: string
  title?: string
  description?: string
  detail?: any
  created_at?: string
  /** 原始事件 seq, 用于去重 */
  seq: number
}

/** 全局应用状态 */
export interface AppState {
  /** 当前激活角色 */
  activePersonaId: number | null
  /** 运行中的任务 (蜂群/DAG/自动化) */
  runningTasks: RunningTask[]
  /** 记忆图谱增量事件 (最新 50 条) */
  memoryEvents: MemoryEvent[]
  /** 工具调用实时状态 (按 call_id 索引) */
  toolExecutions: Record<string, ToolExecution>
  /** 健康状态 */
  health: HealthState
  /** 技能/MCP 状态 */
  skillsMcp: SkillsMcpState
  /** 应用版本号 */
  appVersion: string
  /** SSE 连接状态 */
  sseConnected: boolean
  /** 当前页面 (导航) */
  currentPage: string
  /** 可见 DAG 列表 (多任务并排) */
  visibleDagIds: string[]
  /** 进化日志增量事件 (最新 50 条, 由 evolution.log.appended 推送) */
  evolutionLogs: EvolutionLogEntry[]
}

export interface RunningTask {
  id: string
  type: 'swarm' | 'dag' | 'autowork' | 'scheduler'
  title: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
  progress?: number
  startedAt?: string
  personaId?: number
}

export interface MemoryEvent {
  seq: number
  eventType: string
  nodeId?: number
  action?: string
  payload: any
  timestamp: string
}

export interface ToolExecution {
  callId: string
  toolName: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout'
  startedAt?: string
  completedAt?: string
  error?: string
  result?: any
}

export interface HealthState {
  globalEnabled: boolean
  providers: Record<string, { healthy: boolean; lastCheck?: string; enabled: boolean }>
  mcpServers: Record<string, { healthy: boolean; lastCheck?: string; enabled: boolean }>
  lastUpdate?: string
}

export interface SkillsMcpState {
  skills: Record<string, { enabled: boolean; source: string }>
  mcpServers: Record<string, { connected: boolean; transport: 'stdio' | 'sse' }>
}

/** Action 类型 */
export type AppAction =
  | { type: 'NAVIGATE'; page: string }
  | { type: 'SSE_CONNECTED'; connected: boolean }
  | { type: 'SET_APP_VERSION'; version: string }
  | { type: 'SET_ACTIVE_PERSONA'; personaId: number | null }
  | { type: 'TASK_STARTED'; task: RunningTask }
  | { type: 'TASK_UPDATED'; id: string; patch: Partial<RunningTask> }
  | { type: 'TASK_REMOVED'; id: string }
  | { type: 'MEMORY_EVENT'; event: MemoryEvent }
  | { type: 'TOOL_CALL_STARTED'; exec: ToolExecution }
  | { type: 'TOOL_CALL_UPDATED'; callId: string; patch: Partial<ToolExecution> }
  | { type: 'HEALTH_UPDATED'; patch: Partial<HealthState> }
  | { type: 'SKILL_TOGGLED'; skillId: string; enabled: boolean }
  | { type: 'MCP_CONNECTED'; serverId: string; transport: 'stdio' | 'sse' }
  | { type: 'MCP_DISCONNECTED'; serverId: string }
  | { type: 'DAG_VISIBLE_ADD'; dagId: string }
  | { type: 'DAG_VISIBLE_REMOVE'; dagId: string }
  | { type: 'EVENT_DISPATCH'; event: BusEvent }

/** 总线事件 (从 /events/stream 接收) */
export interface BusEvent {
  seq: number
  event_type: string
  payload: any
  source: string
  timestamp: string
}

// =========================================================================
// 初始状态
// =========================================================================

const initialState: AppState = {
  activePersonaId: null,
  runningTasks: [],
  memoryEvents: [],
  toolExecutions: {},
  health: {
    globalEnabled: true,
    providers: {},
    mcpServers: {},
  },
  skillsMcp: {
    skills: {},
    mcpServers: {},
  },
  appVersion: '',
  sseConnected: false,
  currentPage: 'chat',
  visibleDagIds: [],
  evolutionLogs: [],
}

// =========================================================================
// Reducer
// =========================================================================

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'NAVIGATE':
      return { ...state, currentPage: action.page }

    case 'SSE_CONNECTED':
      return { ...state, sseConnected: action.connected }

    case 'SET_APP_VERSION':
      return { ...state, appVersion: action.version }

    case 'SET_ACTIVE_PERSONA':
      return { ...state, activePersonaId: action.personaId }

    case 'TASK_STARTED':
      // 去重: 同 id 替换
      return {
        ...state,
        runningTasks: [
          ...state.runningTasks.filter((t) => t.id !== action.task.id),
          action.task,
        ],
      }

    case 'TASK_UPDATED':
      return {
        ...state,
        runningTasks: state.runningTasks.map((t) =>
          t.id === action.id ? { ...t, ...action.patch } : t
        ),
      }

    case 'TASK_REMOVED':
      return {
        ...state,
        runningTasks: state.runningTasks.filter((t) => t.id !== action.id),
      }

    case 'MEMORY_EVENT':
      // 保留最新 50 条
      return {
        ...state,
        memoryEvents: [...state.memoryEvents, action.event].slice(-50),
      }

    case 'TOOL_CALL_STARTED':
      return {
        ...state,
        toolExecutions: {
          ...state.toolExecutions,
          [action.exec.callId]: action.exec,
        },
      }

    case 'TOOL_CALL_UPDATED': {
      const existing = state.toolExecutions[action.callId]
      if (!existing) return state
      return {
        ...state,
        toolExecutions: {
          ...state.toolExecutions,
          [action.callId]: { ...existing, ...action.patch },
        },
      }
    }

    case 'HEALTH_UPDATED':
      return {
        ...state,
        health: { ...state.health, ...action.patch, lastUpdate: new Date().toISOString() },
      }

    case 'SKILL_TOGGLED': {
      const existing = state.skillsMcp.skills[action.skillId] || { enabled: false, source: 'unknown' }
      return {
        ...state,
        skillsMcp: {
          ...state.skillsMcp,
          skills: {
            ...state.skillsMcp.skills,
            [action.skillId]: { ...existing, enabled: action.enabled },
          },
        },
      }
    }

    case 'MCP_CONNECTED':
      return {
        ...state,
        skillsMcp: {
          ...state.skillsMcp,
          mcpServers: {
            ...state.skillsMcp.mcpServers,
            [action.serverId]: { connected: true, transport: action.transport },
          },
        },
      }

    case 'MCP_DISCONNECTED': {
      const next = { ...state.skillsMcp.mcpServers }
      delete next[action.serverId]
      return {
        ...state,
        skillsMcp: { ...state.skillsMcp, mcpServers: next },
      }
    }

    case 'DAG_VISIBLE_ADD':
      if (state.visibleDagIds.includes(action.dagId)) return state
      return { ...state, visibleDagIds: [...state.visibleDagIds, action.dagId] }

    case 'DAG_VISIBLE_REMOVE':
      return {
        ...state,
        visibleDagIds: state.visibleDagIds.filter((id) => id !== action.dagId),
      }

    case 'EVENT_DISPATCH':
      // 总线事件路由到具体 state 更新
      return dispatchBusEvent(state, action.event)

    default:
      return state
  }
}

/** 将总线事件路由到具体 state 更新 */
function dispatchBusEvent(state: AppState, event: BusEvent): AppState {
  const { event_type, payload } = event
  // memory.* → memoryEvents
  if (event_type.startsWith('memory.')) {
    const memEvent: MemoryEvent = {
      seq: event.seq,
      eventType: event_type,
      nodeId: payload.node_id,
      action: payload.action,
      payload,
      timestamp: event.timestamp,
    }
    return { ...state, memoryEvents: [...state.memoryEvents, memEvent].slice(-50) }
  }
  // evolution.log.appended → evolutionLogs (增量追加, 最新 50 条)
  if (event_type === 'evolution.log.appended') {
    const entry: EvolutionLogEntry = {
      id: payload.log_id,
      phase: payload.phase,
      status: payload.status,
      title: payload.title,
      description: payload.description,
      detail: payload.detail,
      created_at: payload.created_at || event.timestamp,
      seq: event.seq,
    }
    // 去重: 同 log_id / 同 seq 不重复追加
    const exists = state.evolutionLogs.some(
      (e) => (entry.id != null && e.id === entry.id) || e.seq === entry.seq
    )
    if (exists) return state
    return {
      ...state,
      evolutionLogs: [...state.evolutionLogs, entry].slice(-50),
    }
  }
  // chat.tool.call.* → toolExecutions
  if (event_type === 'chat.tool.call.started') {
    const exec: ToolExecution = {
      callId: payload.call_id,
      toolName: payload.tool_name,
      status: 'running',
      startedAt: event.timestamp,
    }
    return {
      ...state,
      toolExecutions: { ...state.toolExecutions, [exec.callId]: exec },
    }
  }
  if (event_type === 'chat.tool.call.completed') {
    const existing = state.toolExecutions[payload.call_id]
    if (!existing) return state
    return {
      ...state,
      toolExecutions: {
        ...state.toolExecutions,
        [payload.call_id]: {
          ...existing,
          status: payload.success ? 'completed' : 'failed',
          completedAt: event.timestamp,
          error: payload.error,
          result: payload.result,
        },
      },
    }
  }
  // swarm.* / dag.* → runningTasks
  if (event_type === 'swarm.created' || event_type === 'swarm.started') {
    const task: RunningTask = {
      id: `swarm-${payload.swarm_id}`,
      type: 'swarm',
      title: payload.title || `蜂群 #${payload.swarm_id}`,
      status: 'running',
      startedAt: event.timestamp,
      personaId: payload.persona_id,
    }
    return {
      ...state,
      runningTasks: [
        ...state.runningTasks.filter((t) => t.id !== task.id),
        task,
      ],
      visibleDagIds: state.visibleDagIds.includes(`dag-swarm-${payload.swarm_id}`)
        ? state.visibleDagIds
        : [...state.visibleDagIds, `dag-swarm-${payload.swarm_id}`],
    }
  }
  if (event_type === 'swarm.completed' || event_type === 'swarm.failed') {
    const taskId = `swarm-${payload.swarm_id}`
    return {
      ...state,
      runningTasks: state.runningTasks.map((t) =>
        t.id === taskId
          ? { ...t, status: event_type === 'swarm.completed' ? 'completed' : 'failed' }
          : t
      ),
    }
  }
  // dag.node.* → runningTasks + visibleDagIds
  // 节点级事件: 确保 DAG 可见,触发 DAGCanvas 刷新
  if (event_type === 'dag.node.started') {
    const dagId = payload.dag_id
    if (!dagId) return state
    const taskId = `dag-${dagId}`
    const task: RunningTask = {
      id: taskId,
      type: 'dag',
      title: payload.title || `DAG ${dagId}`,
      status: 'running',
      startedAt: event.timestamp,
      personaId: payload.persona_id,
    }
    return {
      ...state,
      runningTasks: [
        ...state.runningTasks.filter((t) => t.id !== taskId),
        task,
      ],
      visibleDagIds: state.visibleDagIds.includes(dagId)
        ? state.visibleDagIds
        : [...state.visibleDagIds, dagId],
    }
  }
  if (event_type === 'dag.node.completed') {
    const dagId = payload.dag_id
    if (!dagId) return state
    // phase=dag_completed 表示整个 DAG 完成,标记任务完成
    if (payload.phase === 'dag_completed') {
      const taskId = `dag-${dagId}`
      return {
        ...state,
        runningTasks: state.runningTasks.map((t) =>
          t.id === taskId ? { ...t, status: 'completed' } : t
        ),
      }
    }
    // 节点级完成: 不改任务状态,但产生新引用以触发 DAGCanvas 刷新
    return { ...state, runningTasks: [...state.runningTasks] }
  }
  if (event_type === 'dag.node.failed') {
    const dagId = payload.dag_id
    if (!dagId) return state
    const taskId = `dag-${dagId}`
    return {
      ...state,
      runningTasks: state.runningTasks.map((t) =>
        t.id === taskId ? { ...t, status: 'failed' } : t
      ),
    }
  }
  // health.* → health
  if (event_type === 'health.provider.toggled') {
    const existing = state.health.providers[payload.provider] || { healthy: true, enabled: true }
    return {
      ...state,
      health: {
        ...state.health,
        providers: {
          ...state.health.providers,
          [payload.provider]: {
            ...existing,
            healthy: payload.healthy,
            enabled: payload.enabled !== undefined ? payload.enabled : existing.enabled,
            lastCheck: event.timestamp,
          },
        },
      },
    }
  }
  if (event_type === 'health.check.completed') {
    return { ...state, health: { ...state.health, ...payload, lastUpdate: event.timestamp } }
  }
  // skill.* → skillsMcp
  if (event_type === 'skill.enabled.toggled') {
    const existing = state.skillsMcp.skills[payload.skill_id] || { enabled: false, source: 'unknown' }
    return {
      ...state,
      skillsMcp: {
        ...state.skillsMcp,
        skills: {
          ...state.skillsMcp.skills,
          [payload.skill_id]: { ...existing, enabled: payload.enabled },
        },
      },
    }
  }
  // mcp.* → skillsMcp.mcpServers
  if (event_type === 'mcp.connected') {
    return {
      ...state,
      skillsMcp: {
        ...state.skillsMcp,
        mcpServers: {
          ...state.skillsMcp.mcpServers,
          [payload.server_id]: { connected: true, transport: payload.transport || 'stdio' },
        },
      },
    }
  }
  if (event_type === 'mcp.disconnected') {
    const next = { ...state.skillsMcp.mcpServers }
    delete next[payload.server_id]
    return { ...state, skillsMcp: { ...state.skillsMcp, mcpServers: next } }
  }
  // 其他事件: 不修改 state (但已被接收)
  return state
}

// =========================================================================
// Context
// =========================================================================

interface StoreContextValue {
  state: AppState
  dispatch: (action: AppAction) => void
}

const StoreContext = createContext<StoreContextValue>({
  state: initialState,
  dispatch: () => {},
})

// =========================================================================
// Provider — 含 SSE 连接逻辑
// =========================================================================

/** SSE 连接 URL (复用 api.ts 的 token 机制) */
async function buildSseUrl(patterns: string): Promise<string> {
  let baseUrl: string
  let token: string
  if (isTauri()) {
    const handshake = await getHandshake()
    if (!handshake) {
      throw new Error('Sidecar 未就绪,无法建立 SSE 连接')
    }
    baseUrl = `http://127.0.0.1:${handshake.port}`
    token = handshake.token
  } else {
    baseUrl = getApiBase()
    token = getAuthToken()
  }
  // token 作为查询参数 (EventSource 不支持自定义 header,这里用 fetch+ReadableStream)
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : ''
  return `${baseUrl}/events/stream?patterns=${encodeURIComponent(patterns)}${tokenParam}`
}

export function StoreProvider({ children }: { children: JSX.Element | JSX.Element[] }) {
  const [state, dispatch] = useReducer(appReducer, initialState)
  const lastSeqRef = useRef<number>(0)
  const reconnectTimerRef = useRef<any>(null)

  useEffect(() => {
    let cancelled = false
    let controller: AbortController | null = null

    async function connectSSE() {
      try {
        // 订阅全量事件 (前端 reducer 自行路由)
        const url = await buildSseUrl('*')
        controller = new AbortController()
        dispatch({ type: 'SSE_CONNECTED', connected: false })

        const res = await fetch(url, {
          method: 'GET',
          signal: controller.signal,
          headers: { Accept: 'text/event-stream' },
        })
        if (!res.body) throw new Error('无 SSE 响应流')

        dispatch({ type: 'SSE_CONNECTED', connected: true })

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let currentData: string | null = null
          for (const line of lines) {
            const trimmed = line.trim()
            if (trimmed.startsWith('data: ')) {
              currentData = trimmed.slice(6)
            } else if (trimmed === '' && currentData) {
              // 空行 = 事件结束
              try {
                const event: BusEvent = JSON.parse(currentData)
                if (event.seq > lastSeqRef.current) {
                  lastSeqRef.current = event.seq
                }
                dispatch({ type: 'EVENT_DISPATCH', event })
              } catch (e) {
                console.warn('[SSE] 解析事件失败:', e, currentData)
              }
              currentData = null
            }
            // id: 行 (Last-Event-ID) — 已在 data.seq 中,无需单独处理
            // : heartbeat 注释行 — 忽略
          }
        }
      } catch (e) {
        if (!cancelled) {
          console.warn('[SSE] 连接失败,5s 后重连:', e)
          dispatch({ type: 'SSE_CONNECTED', connected: false })
          // 5s 后重连 (断线降级)
          reconnectTimerRef.current = setTimeout(connectSSE, 5000)
        }
      }
    }

    connectSSE()

    return () => {
      cancelled = true
      if (controller) controller.abort()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    }
  }, [])

  // 拉取应用版本号 (修复"版本 v..."bug)
  useEffect(() => {
    import('./api').then(({ apiGet }) => {
      apiGet<any>('/update/status')
        .then((res) => {
          // 修复: apiGet 已解包,直接读 res.current_version (非 res.data.current_version)
          if (res?.current_version) {
            dispatch({ type: 'SET_APP_VERSION', version: res.current_version })
          }
        })
        .catch(() => {
          /* ignore */
        })
    })
  }, [])

  return h(StoreContext.Provider, { value: { state, dispatch } }, children)
}

/** Hook: 获取全局状态 + dispatch */
export function useGlobalState(): StoreContextValue {
  return useContext(StoreContext)
}

/** Hook: 仅获取当前页面 */
export function useCurrentPage(): [string, (page: string) => void] {
  const { state, dispatch } = useContext(StoreContext)
  return [state.currentPage, (page: string) => dispatch({ type: 'NAVIGATE', page })]
}

/** Hook: 仅获取应用版本号 */
export function useAppVersion(): string {
  const { state } = useContext(StoreContext)
  return state.appVersion
}
