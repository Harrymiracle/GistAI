export type ArticleProcessingStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'partial_failed'
  | 'failed'

export interface ArticleCreateRequest {
  source_url: string
  source_type: 'web'
}

export interface ArticleDetail {
  id: number
  user_id: number
  source_type: string
  source_url: string
  source_name: string | null
  title: string | null
  author: string | null
  published_at: string | null
  clean_content: string | null
  content_hash: string | null
  one_sentence_summary: string | null
  detailed_summary: string | null
  key_points: string[] | null
  tags: string[]
  favorite: boolean
  status: ArticleProcessingStatus
  fetch_status: ArticleProcessingStatus
  ai_status: ArticleProcessingStatus
  embedding_status: ArticleProcessingStatus
  fetch_error: string | null
  ai_error: string | null
  embedding_error: string | null
  created_at: string
  updated_at: string
}
