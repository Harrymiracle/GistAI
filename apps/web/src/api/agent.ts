import type { ApiResponse } from '../types/api'
import type { AgentChatData, AgentChatRequest } from '../types/agent'
import { apiClient } from './client'

export type {
  AgentChatData,
  AgentChatRequest,
  AgentResponseStatus,
  AgentSource,
} from '../types/agent'

export async function sendAgentMessage(
  payload: AgentChatRequest,
): Promise<AgentChatData> {
  const response = await apiClient.post<ApiResponse<AgentChatData>>(
    '/agent/chat',
    payload,
  )

  return response.data.data
}

export const agentApi = {
  chat: sendAgentMessage,
}
