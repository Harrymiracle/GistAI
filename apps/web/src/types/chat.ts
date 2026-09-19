import type { AgentResponseStatus, AgentSource } from './agent'

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  status?: AgentResponseStatus
  sources?: AgentSource[]
}
