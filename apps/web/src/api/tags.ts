import type { ApiResponse } from '../types/api'
import type { TagRead } from '../types/tag'
import { apiClient } from './client'

export async function listTags(): Promise<TagRead[]> {
  const response = await apiClient.get<ApiResponse<TagRead[]>>('/tags')
  return response.data.data
}
