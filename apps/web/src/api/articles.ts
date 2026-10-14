import axios from 'axios'
import type { ApiResponse } from '../types/api'
import type { ArticleCreateRequest, ArticleDetail, ArticleListData, ArticleReprocessData, ManualArticleImportRequest } from '../types/article'
import { apiClient } from './client'

export async function createArticle(
  payload: ArticleCreateRequest,
): Promise<ArticleDetail> {
  const response = await apiClient.post<ApiResponse<ArticleDetail>>(
    '/articles',
    payload,
  )

  return response.data.data
}

export async function listArticles(page: number, tagId?: number): Promise<ArticleListData> {
  const response = await apiClient.get<ApiResponse<ArticleListData>>('/articles', {
    params: { page, page_size: 10, tag_id: tagId },
  })
  return response.data.data
}

export async function getArticle(id: number): Promise<ArticleDetail> {
  const response = await apiClient.get<ApiResponse<ArticleDetail>>(`/articles/${id}`)
  return response.data.data
}

export async function updateArticleTitle(id: number, title: string): Promise<ArticleDetail> {
  const response = await apiClient.patch<ApiResponse<ArticleDetail>>(`/articles/${id}`, { title })
  return response.data.data
}

export async function reprocessArticle(id: number): Promise<ArticleReprocessData> {
  const response = await apiClient.post<ApiResponse<ArticleReprocessData>>(`/articles/${id}/reprocess`)
  return response.data.data
}

export async function importManualArticle(id: number, payload: ManualArticleImportRequest): Promise<ArticleDetail> {
  const response = await apiClient.post<ApiResponse<ArticleDetail>>(`/articles/${id}/manual-import`, payload)
  return response.data.data
}

export function getExistingArticleId(error: unknown): number | null {
  if (!axios.isAxiosError<ApiResponse<{ article_id?: number }>>(error)) return null
  const body = error.response?.data
  const id = body?.data?.article_id
  return error.response?.status === 409 && body?.code === 40901 && typeof id === 'number' && Number.isSafeInteger(id) && id > 0
    ? id
    : null
}

export function getArticleRequestErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiResponse<unknown>>(error)) {
    const message = error.response?.data?.message
    if (typeof message === 'string' && message.trim()) return message.trim()
  }
  return '请求失败，请稍后重试'
}
