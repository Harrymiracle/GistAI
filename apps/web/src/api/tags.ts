import type { ApiResponse } from '../types/api'
import type { PendingTagRead, TagDeleteResult, TagIgnoreResult, TagMergeResult, TagRead } from '../types/tag'
import { apiClient } from './client'

export async function listTags(): Promise<TagRead[]> {
  const response = await apiClient.get<ApiResponse<TagRead[]>>('/tags')
  return response.data.data
}

export async function listPendingTags(): Promise<PendingTagRead[]> {
  const response = await apiClient.get<ApiResponse<PendingTagRead[]>>('/tags/pending')
  return response.data.data
}

export async function promotePendingTag(id: number): Promise<TagRead> {
  const response = await apiClient.post<ApiResponse<TagRead>>(`/tags/${id}/promote`)
  return response.data.data
}

export async function mergePendingTag(id: number, targetTagId: number): Promise<TagMergeResult> {
  const response = await apiClient.post<ApiResponse<TagMergeResult>>(`/tags/${id}/merge`, { target_tag_id: targetTagId })
  return response.data.data
}

export async function ignorePendingTag(id: number): Promise<TagIgnoreResult> {
  const response = await apiClient.post<ApiResponse<TagIgnoreResult>>(`/tags/${id}/ignore`)
  return response.data.data
}

export async function deleteTag(id: number): Promise<TagDeleteResult> {
  const response = await apiClient.delete<ApiResponse<TagDeleteResult>>(`/tags/${id}`)
  return response.data.data
}
