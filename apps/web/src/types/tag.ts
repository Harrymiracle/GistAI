export interface TagRead {
  id: number
  name: string
  article_count: number
  created_at: string
  updated_at: string
}

export interface PendingTopicSource {
  article_id: number
  title: string | null
}

export interface PendingTagRead {
  id: number
  name: string
  created_at: string
  sources: PendingTopicSource[]
}

export interface TagMergeResult {
  tag_id: number
  target_tag_id: number
  affected_article_count: number
}

export interface TagIgnoreResult {
  tag_id: number
  affected_article_count: number
}

export interface TagDeleteResult {
  tag_id: number
}
