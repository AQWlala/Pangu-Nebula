// v2.3.0 Phase 0 — 前端统一状态层 (v2.3.1 修复)
//
// Preact Context + useReducer,单一 SSE 连接订阅 /events/stream,
// dispatch 到 7 类全局 state,替代各组件各自轮询。
//
// v2.3.1 修复:
//   - token 改用 Authorization header (不再暴露在 URL)
//   - SSE 断点续传: 重连时传 last_seq 查询参数 + 客户端 seq 去重
//   - SSE 重连指数退避: 5s → 10s → 20s → 60s 上限 + jitter
//   - useGlobalState 引入 selector 模式 (Object.is 比较跳过更新),
//     避免全组件树重渲染
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
//   import { useGlobalState, useDispatch } from '../lib/store'
//   const currentPage = useGlobalState(s => s.currentPage)
//   const dispatch = useDispatch()
//   dispatch({ type: 'NAVIGATE', page: 'memory' })

import { createContext, h } from 'preact'
import { useContext, useEffect, useLayoutEffect, useReducer, useRef } from 'preact/hooks'
import { useSyncExternalStore } from 'preact/compat'
import type { JSX } from 'preact'
import { isTauri, getHandshake, getApiBase, getAuthToken } from './api'
import { logger } from './logger'

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
  detail?: Record<string, unknown>
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
  payload: Record<string, unknown>
  timestamp: string
}

export interface ToolExecution {
  callId: string
  toolName: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout'
  startedAt?: string
  completedAt?: string
  error?: string
  result?: Record<string, unknown>
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
  payload: Record<string, unknown>
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

/** 从 payload 中安全读取 string 字段 */
function pickStr(p: Record<string, unknown>, key: string): string | undefined {
  const v = p[key]
  return typeof v === 'string' ? v : undefined
}

/** 从 payload 中安全读取 number 字段 */
function pickNum(p: Record<string, unknown>, key: string): number | undefined {
  const v = p[key]
  return typeof v === 'number' ? v : undefined
}

/** 从 payload 中安全读取 boolean 字段 */
function pickBool(p: Record<string, unknown>, key: string): boolean | undefined {
  const v = p[key]
  return typeof v === 'boolean' ? v : undefined
}

/** 将总线事件路由到具体 state 更新 */
function dispatchBusEvent(state: AppState, event: BusEvent): AppState {
  const { event_type, payload } = event
  // memory.* → memoryEvents
  if (event_type.startsWith('memory.')) {
    const memEvent: MemoryEvent = {
      seq: event.seq,
      eventType: event_type,
      nodeId: pickNum(payload, 'node_id'),
      action: pickStr(payload, 'action'),
      payload,
      timestamp: event.timestamp,
    }
    return { ...state, memoryEvents: [...state.memoryEvents, memEvent].slice(-50) }
  }
  // evolution.log.appended → evolutionLogs (增量追加, 最新 50 条)
  if (event_type === 'evolution.log.appended') {
    const entry: EvolutionLogEntry = {
      id: pickNum(payload, 'log_id'),
      phase: pickStr(payload, 'phase'),
      status: pickStr(payload, 'status'),
      title: pickStr(payload, 'title'),
      description: pickStr(payload, 'description'),
      detail: payload.detail as Record<string, unknown> | undefined,
      created_at: pickStr(payload, 'created_at') || event.timestamp,
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
    const callId = pickStr(payload, 'call_id')
    if (!callId) return state
    const exec: ToolExecution = {
      callId,
      toolName: pickStr(payload, 'tool_name') || '',
      status: 'running',
      startedAt: event.timestamp,
    }
    return {
      ...state,
      toolExecutions: { ...state.toolExecutions, [exec.callId]: exec },
    }
  }
  if (event_type === 'chat.tool.call.completed') {
    const callId = pickStr(payload, 'call_id')
    if (!callId) return state
    const existing = state.toolExecutions[callId]
    if (!existing) return state
    return {
      ...state,
      toolExecutions: {
        ...state.toolExecutions,
        [callId]: {
          ...existing,
          status: pickBool(payload, 'success') ? 'completed' : 'failed',
          completedAt: event.timestamp,
          error: pickStr(payload, 'error'),
          result: payload.result as Record<string, unknown> | undefined,
        },
      },
    }
  }
  // swarm.* / dag.* → runningTasks
  if (event_type === 'swarm.created' || event_type === 'swarm.started') {
    const swarmId = pickNum(payload, 'swarm_id')
    if (swarmId == null) return state
    const task: RunningTask = {
      id: `swarm-${swarmId}`,
      type: 'swarm',
      title: pickStr(payload, 'title') || `蜂群 #${swarmId}`,
      status: 'running',
      startedAt: event.timestamp,
      personaId: pickNum(payload, 'persona_id'),
    }
    const dagId = `dag-swarm-${swarmId}`
    return {
      ...state,
      runningTasks: [
        ...state.runningTasks.filter((t) => t.id !== task.id),
        task,
      ],
      visibleDagIds: state.visibleDagIds.includes(dagId)
        ? state.visibleDagIds
        : [...state.visibleDagIds, dagId],
    }
  }
  if (event_type === 'swarm.completed' || event_type === 'swarm.failed') {
    const swarmId = pickNum(payload, 'swarm_id')
    if (swarmId == null) return state
    const taskId = `swarm-${swarmId}`
    return {
      ...state,
      runningTasks: state.runningTasks.map((t) =>
        t.id === taskId
          ? { ...t, status: event_type === 'swarm.completed' ? 'completed' : 'failed' }
          : t
      ),
    }
  }
  // v2.3.1 补全: swarm.cancelled / swarm.interrupted
  if (event_type === 'swarm.cancelled' || event_type === 'swarm.interrupted') {
    const swarmId = pickNum(payload, 'swarm_id')
    if (swarmId == null) return state
    const taskId = `swarm-${swarmId}`
    const nextStatus: RunningTask['status'] = event_type === 'swarm.cancelled' ? 'cancelled' : 'interrupted'
    return {
      ...state,
      runningTasks: state.runningTasks.map((t) =>
        t.id === taskId ? { ...t, status: nextStatus } : t
      ),
    }
  }
  // dag.node.* → runningTasks + visibleDagIds
  // 节点级事件: 确保 DAG 可见,触发 DAGCanvas 刷新
  if (event_type === 'dag.node.started') {
    const dagId = pickStr(payload, 'dag_id')
    if (!dagId) return state
    const taskId = `dag-${dagId}`
    const task: RunningTask = {
      id: taskId,
      type: 'dag',
      title: pickStr(payload, 'title') || `DAG ${dagId}`,
      status: 'running',
      startedAt: event.timestamp,
      personaId: pickNum(payload, 'persona_id'),
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
    const dagId = pickStr(payload, 'dag_id')
    if (!dagId) return state
    // phase=dag_completed 表示整个 DAG 完成,标记任务完成
    if (pickStr(payload, 'phase') === 'dag_completed') {
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
  // v2.3.1 修复: dag.node.failed 仅更新节点状态, 不将整个 DAG 标记为 failed
  // 原实现错误地把节点失败等同于 DAG 失败, 导致多节点 DAG 中单节点失败时
  // 整个 DAG 任务被错误标记为 failed。
  // 现在: 节点失败只触发 DAGCanvas 刷新 (新引用), 由 DAGCanvas 自行渲染节点颜色
  if (event_type === 'dag.node.failed') {
    const dagId = pickStr(payload, 'dag_id')
    if (!dagId) return state
    return { ...state, runningTasks: [...state.runningTasks] }
  }
  // v2.3.1 补全: dag.completed / dag.failed (整个 DAG 级事件)
  if (event_type === 'dag.completed' || event_type === 'dag.failed') {
    const dagId = pickStr(payload, 'dag_id')
    if (!dagId) return state
    const taskId = `dag-${dagId}`
    const nextStatus: RunningTask['status'] = event_type === 'dag.completed' ? 'completed' : 'failed'
    return {
      ...state,
      runningTasks: state.runningTasks.map((t) =>
        t.id === taskId ? { ...t, status: nextStatus } : t
      ),
      visibleDagIds: state.visibleDagIds.filter((id) => id !== dagId),
    }
  }
  // health.* → health
  if (event_type === 'health.provider.toggled') {
    const provider = pickStr(payload, 'provider')
    if (!provider) return state
    const existing = state.health.providers[provider] || { healthy: true, enabled: true }
    return {
      ...state,
      health: {
        ...state.health,
        providers: {
          ...state.health.providers,
          [provider]: {
            ...existing,
            healthy: pickBool(payload, 'healthy') ?? existing.healthy,
            enabled: pickBool(payload, 'enabled') ?? existing.enabled,
            lastCheck: event.timestamp,
          },
        },
      },
    }
  }
  if (event_type === 'health.check.completed') {
    return { ...state, health: { ...state.health, ...(payload as Partial<HealthState>), lastUpdate: event.timestamp } }
  }
  // v2.3.1 补全: health.mcp.toggled / health.skill.toggled
  if (event_type === 'health.mcp.toggled' || event_type === 'health.skill.toggled') {
    // 复用 HEALTH_UPDATED 通道, payload 形如 { mcpServers: {...} } / { providers: {...} }
    return { ...state, health: { ...state.health, ...(payload as Partial<HealthState>), lastUpdate: event.timestamp } }
  }
  // skill.* → skillsMcp
  if (event_type === 'skill.enabled.toggled') {
    const skillId = pickStr(payload, 'skill_id')
    if (!skillId) return state
    const existing = state.skillsMcp.skills[skillId] || { enabled: false, source: 'unknown' }
    return {
      ...state,
      skillsMcp: {
        ...state.skillsMcp,
        skills: {
          ...state.skillsMcp.skills,
          [skillId]: { ...existing, enabled: pickBool(payload, 'enabled') ?? existing.enabled },
        },
      },
    }
  }
  // mcp.* → skillsMcp.mcpServers
  if (event_type === 'mcp.connected') {
    const serverId = pickStr(payload, 'server_id')
    if (!serverId) return state
    const transport = pickStr(payload, 'transport') === 'sse' ? 'sse' : 'stdio'
    return {
      ...state,
      skillsMcp: {
        ...state.skillsMcp,
        mcpServers: {
          ...state.skillsMcp.mcpServers,
          [serverId]: { connected: true, transport },
        },
      },
    }
  }
  if (event_type === 'mcp.disconnected') {
    const serverId = pickStr(payload, 'server_id')
    if (!serverId) return state
    const next = { ...state.skillsMcp.mcpServers }
    delete next[serverId]
    return { ...state, skillsMcp: { ...state.skillsMcp, mcpServers: next } }
  }
  // 其他事件: 不修改 state (但已被接收)
  return state
}

// =========================================================================
// 外部 store (供 useSyncExternalStore 订阅)
// =========================================================================

/** 当前最新 state (由 StoreProvider 通过 useLayoutEffect 同步) */
let currentState: AppState = initialState
/** 订阅者集合 */
const listeners = new Set<() => void>()

function emitChange() {
  for (const l of listeners) l()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): AppState {
  return currentState
}

// =========================================================================
// Dispatch 单独 Context (永远不变, 不会触发订阅者重渲染)
// =========================================================================

const DispatchContext = createContext<(action: AppAction) => void>(() => {})

// =========================================================================
// Provider — 含 SSE 连接逻辑
// =========================================================================

/** SSE 连接 URL (token 改用 Authorization header, 不再暴露在 URL) */
async function buildSseUrl(patterns: string, lastSeq: number): Promise<{ url: string; token: string }> {
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
  // v2.3.1: token 改用 Authorization header, 不再放 URL 查询参数
  // last_seq 用于断点续传 (后端 /events/stream 支持 last_event_id 查询参数)
  const lastSeqParam = lastSeq > 0 ? `&last_seq=${lastSeq}` : ''
  const url = `${baseUrl}/events/stream?patterns=${encodeURIComponent(patterns)}${lastSeqParam}`
  return { url, token }
}

/** 指数退避延迟 (5s → 10s → 20s → 40s → 60s 上限) + 随机抖动 */
function backoffDelay(attempt: number): number {
  const base = Math.min(5000 * Math.pow(2, attempt), 60000)
  // jitter: ±20% 随机抖动, 避免大量客户端同时重连
  const jitter = base * 0.2 * (Math.random() * 2 - 1)
  return Math.max(1000, base + jitter)
}

export function StoreProvider({ children }: { children: JSX.Element | JSX.Element[] }) {
  const [state, dispatch] = useReducer(appReducer, initialState)
  const lastSeqRef = useRef<number>(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptRef = useRef<number>(0)

  // 同步外部 store: 每次 state 变化后 (commit phase 同步执行) 通知订阅者
  // 使用 useLayoutEffect 确保订阅者在 paint 前拿到最新 state
  useLayoutEffect(() => {
    currentState = state
    emitChange()
  }, [state])

  useEffect(() => {
    let cancelled = false
    let controller: AbortController | null = null

    async function connectSSE() {
      try {
        // 订阅全量事件 (前端 reducer 自行路由)
        // v2.3.1: 重连时携带 last_seq 实现断点续传, 避免后端重发所有事件
        const { url, token } = await buildSseUrl('*', lastSeqRef.current)
        controller = new AbortController()
        dispatch({ type: 'SSE_CONNECTED', connected: false })

        // v2.3.1: token 通过 Authorization header 传递, 不再暴露在 URL
        const headers: Record<string, string> = { Accept: 'text/event-stream' }
        if (token) {
          headers['Authorization'] = `Bearer ${token}`
        }

        const res = await fetch(url, {
          method: 'GET',
          signal: controller.signal,
          headers,
        })
        if (!res.body) throw new Error('无 SSE 响应流')

        dispatch({ type: 'SSE_CONNECTED', connected: true })
        // 连接成功后重置退避计数
        reconnectAttemptRef.current = 0

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
                // v2.3.1: 客户端 seq 去重 (双重保险, 即使后端 last_seq 没生效)
                // 仅处理 seq > lastSeqRef.current 的事件
                if (event.seq > lastSeqRef.current) {
                  lastSeqRef.current = event.seq
                  dispatch({ type: 'EVENT_DISPATCH', event })
                }
              } catch (e) {
                logger.warn('[SSE] 解析事件失败:', e, currentData)
              }
              currentData = null
            }
            // id: 行 (Last-Event-ID) — 已在 data.seq 中,无需单独处理
            // : heartbeat 注释行 — 忽略
          }
        }
      } catch (e) {
        if (!cancelled) {
          // v2.3.1: 指数退避重连 (5s → 10s → 20s → 60s 上限 + jitter)
          const attempt = reconnectAttemptRef.current++
          const delay = backoffDelay(attempt)
          logger.warn(`[SSE] 连接失败, ${Math.round(delay / 1000)}s 后重连 (attempt=${attempt + 1}):`, e)
          dispatch({ type: 'SSE_CONNECTED', connected: false })
          reconnectTimerRef.current = setTimeout(connectSSE, delay)
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
      apiGet<{ current_version?: string }>('/update/status')
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

  return h(DispatchContext.Provider, { value: dispatch }, children)
}

// =========================================================================
// Hooks
// =========================================================================

/** Hook: 通过 selector 订阅全局 state
 *
 * 方案 C: useSyncExternalStore + Object.is 比较, 仅在 selector 结果变化时触发重渲染。
 * 调用方示例:
 *   const currentPage = useGlobalState(s => s.currentPage)
 *   const tasks = useGlobalState(s => s.runningTasks)
 */
export function useGlobalState<T>(selector: (s: AppState) => T): T {
  // 缓存 selector 引用, 避免 useSyncExternalStore 因依赖变化重建订阅
  const selectorRef = useRef(selector)
  selectorRef.current = selector

  // 缓存上次 selector 结果 + 对应的 state 引用,
  // 防止 useSyncExternalStore 因新引用 (即使值相等) 触发无限重渲染
  const lastStateRef = useRef<AppState>(currentState)
  const lastValueRef = useRef<{ v: T } | null>(null)
  if (lastValueRef.current === null) {
    lastValueRef.current = { v: selector(currentState) }
  }

  const getSnap = (): T => {
    const s = getSnapshot()
    // state 引用未变: 直接返回缓存的值 (引用稳定, 避免无限循环)
    if (s === lastStateRef.current) {
      return lastValueRef.current!.v
    }
    // state 变化: 重新计算 selector
    const next = selectorRef.current(s)
    // Object.is 比较: 若值相同, 更新 state 引用但保留旧值 (引用稳定)
    if (Object.is(next, lastValueRef.current!.v)) {
      lastStateRef.current = s
      return lastValueRef.current!.v
    }
    // 值变化: 更新缓存
    lastValueRef.current = { v: next }
    lastStateRef.current = s
    return next
  }

  // v2.3.1: preact/compat 的 useSyncExternalStore 类型签名仅接受 2 个参数
  // (React 的第 3 个 getServerSnapshot 在 Tauri 客户端场景不需要)
  return useSyncExternalStore(subscribe, getSnap)
}

/** Hook: 仅获取 dispatch 函数 (稳定引用, 不触发重渲染) */
export function useDispatch(): (action: AppAction) => void {
  return useContext(DispatchContext)
}

/** Hook: 仅获取当前页面 */
export function useCurrentPage(): [string, (page: string) => void] {
  const currentPage = useGlobalState((s) => s.currentPage)
  const dispatch = useDispatch()
  return [currentPage, (page: string) => dispatch({ type: 'NAVIGATE', page })]
}

/** Hook: 仅获取应用版本号 */
export function useAppVersion(): string {
  return useGlobalState((s) => s.appVersion)
}
