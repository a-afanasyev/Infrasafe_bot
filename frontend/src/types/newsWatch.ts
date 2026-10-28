// Зеркало backend-схем uk_management_bot/api/news_watch/schemas.py.
export type NewsItemStatus = 'pending' | 'ignored' | 'published' | 'rejected'
export type NewsKind = 'power' | 'water' | 'gas' | 'heating' | 'internet' | 'other'

export interface NewsSource {
  chat: string
  title: string
}

export interface NewsWatchConfig {
  sources: NewsSource[]
  complex_context: string
  keywords: string[]
  auto_publish: boolean
  min_confidence: number
  broadcast: { dm: boolean; residents_groups: boolean }
}

export interface NewsItem {
  id: number
  source_chat_id: number
  source_message_id: number
  chat_title: string | null
  raw_text: string
  posted_at: string | null
  kind: NewsKind | null
  relevant: boolean | null
  confidence: number | null
  summary_ru: string | null
  summary_uz: string | null
  starts_at: string | null
  ends_at: string | null
  status: NewsItemStatus
  published_at: string | null
  decided_by: number | null
  broadcast_status: 'none' | 'pending' | 'running' | 'done' | 'failed'
  broadcast_attempts: number
  broadcast_details: Record<string, unknown> | null
  created_at: string | null
}
