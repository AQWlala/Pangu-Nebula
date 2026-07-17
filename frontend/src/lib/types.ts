// 共享类型定义 - 前后端数据结构

/** 角色/人格定义 */
export interface Persona {
  id: number
  name: string
  soul: string
  avatar: string
  is_active: boolean
  created_at: string
  // v2.3.0 A3: 角色三元组 (后端 _persona_to_dict 返回的扩展字段)
  role?: string | null
  goal?: string | null
  backstory?: string | null
  // 后端可能返回 system_prompt 字段名 (兼容老版本)
  system_prompt?: string
}

/** 对话消息 */
export interface Message {
  id: number
  conversation_id: number
  role: string
  content: string
  created_at: string
}

/** 对话会话 */
export interface Conversation {
  id: number
  title: string
  persona_id: number
  created_at: string
}

/** 记忆条目 */
export interface Memory {
  id: number
  layer: string
  title: string
  content: string
  tags: string[]
  created_at: string
}

/** 技能定义 */
export interface Skill {
  id: number
  name: string
  description: string
  skill_type: string
  enabled: boolean
}

/** 蜂群任务 */
export interface SwarmTask {
  id: number
  title: string
  status: string
  progress: number
  subtasks: SwarmSubtask[]
}

/** 蜂群 worker */
export interface SwarmWorker {
  id?: number | string
  swarm_id?: number
  subtask_id?: number | string
  persona_id?: number
  status: string
  result?: string
  error?: string
  started_at?: string
  completed_at?: string
}

/** 蜂群子任务 */
export interface SwarmSubtask {
  id: number | string
  title?: string
  description?: string
  status?: string
}

/** 蜂群实体 (后端 /swarm 返回) */
export interface Swarm {
  id: number
  title?: string
  status: string
  progress?: number
  description?: string
  goal?: string
  persona_id?: number
  subtasks?: SwarmSubtask[]
  workers?: SwarmWorker[]
  created_at?: string
  updated_at?: string
  // v2.3.1 P1-11: 后端完成后写入的聚合结果文本
  result?: string
}

/** 渠道配置 */
export interface Channel {
  id: number
  name: string
  channel_type: string
  enabled: boolean
  config: any
}

/** 调度任务 */
export interface SchedulerJob {
  id: number
  name: string
  cron_expr: string
  action: any
  enabled: boolean
  created_at: string
}

/** Provider 信息 */
export interface ProviderInfo {
  name: string
  capabilities: any
  supported_models: string[]
  available: boolean
}
