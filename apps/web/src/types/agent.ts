export type AgentResponseStatus =
  | 'answer'
  | 'partial'
  | 'insufficient'
  | 'error'

export interface AgentChatRequest {
  message: string
  thread_id?: string | null
}

export interface AgentSource {
  source_type: 'knowledge_base' | 'web'
  title: string
  article_id: number | null
  chunk_id: number | null
  url: string | null
  source: string | null
  published_at: string | null
}

export interface AgentChatData {
  thread_id: string
  answer: string
  status: AgentResponseStatus
  sources: AgentSource[]
}
