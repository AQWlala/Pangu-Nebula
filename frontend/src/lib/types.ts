// 共享类型定义 - 前后端数据结构

/** 角色/人格定义 */
export interface Persona {
  id: number
  name: string
  soul: string
  avatar: string
  is_active: boolean
  created_at: string
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
  subtasks: any[]
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
