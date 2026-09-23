import type { ApiResponse } from '../types/api'
import type { ArticleCreateRequest, ArticleDetail } from '../types/article'
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
