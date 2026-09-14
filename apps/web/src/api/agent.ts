import { request } from './request'

export type AgentResponseStatus = 'answer' | 'partial' | 'insufficient' | 'error'

export interface AgentSource {
  source_type: 'knowledge_base' | 'web'
  title: string
  article_id: number | null
  chunk_id: number | null
  url: string | null
  source: string | null
  published_at: string | null
}

export interface AgentChatRequest {
  message: string
  thread_id?: string
}

export interface AgentChatResponse {
  thread_id: string
  answer: string
  status: AgentResponseStatus
  sources: AgentSource[]
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export const agentApi = {
  async chat(payload: AgentChatRequest): Promise<AgentChatResponse> {
    const response = await request.post<ApiResponse<AgentChatResponse>>(
      '/agent/chat',
      payload,
    )
    return response.data.data
  },
}
