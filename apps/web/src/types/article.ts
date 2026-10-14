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

export interface ManualArticleImportRequest {
  source_url: string
  content: string
  title?: string
}

export interface ArticleReprocessData {
  content_unchanged: boolean
  article: ArticleDetail
}

export interface ArticleListItem {
  id: number
  title: string | null
  source_url: string
  source_type: string
  source_name: string | null
  one_sentence_summary: string | null
  tags: string[]
  pending_topics: string[]
  favorite: boolean
  status: ArticleProcessingStatus
  fetch_status: ArticleProcessingStatus
  ai_status: ArticleProcessingStatus
  embedding_status: ArticleProcessingStatus
  created_at: string
  updated_at: string
}

export interface ArticleListData {
  items: ArticleListItem[]
  total: number
  page: number
  page_size: number
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
  pending_topics: string[]
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
