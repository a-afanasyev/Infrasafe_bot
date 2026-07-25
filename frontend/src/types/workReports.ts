// Зеркало backend-схем uk_management_bot/api/work_reports/schemas.py
// (менеджерский API) и uk_management_bot/api/work_reports/public_router.py
// (публичная лента, T8) — см. docstring public_router.py про то, чем
// PublicWorkReportOut отличается от WorkReportOut (нет request_number,
// нет user id, дата вместо datetime).

import type { LocalizedText } from './boardConfig'

export type WorkReportStatus =
  | 'pending'
  | 'needs_media'
  | 'publishing'
  | 'published'
  | 'needs_review'
  | 'rejected'

export type WorkReportSource = 'auto' | 'manual'

export interface WorkReportMediaMetaItem {
  id: number
  file_type: string
  mime: string
  size: number
}

export interface WorkReport {
  id: number
  request_number: string
  category_key: string
  address_public: string
  performed_at: string
  before_media_ids: number[]
  after_media_ids: number[]
  media_meta: WorkReportMediaMetaItem[]
  locked_media_ids: number[]
  status: WorkReportStatus
  source: WorkReportSource
  reject_reason: string | null
  created_at: string
  published_at: string | null
  media_synced_at: string | null
  state_changed_at: string | null
  moderated_by: number | null
}

export interface WorkReportListOut {
  items: WorkReport[]
  total: number
  limit: number
  offset: number
}

export interface WorkReportCreatePayload {
  request_number: string
  building_id?: number
  yard_id?: number
}

export interface WorkReportPatchPayload {
  category_key?: string
  before_media_ids?: number[]
  after_media_ids?: number[]
  building_id?: number
  yard_id?: number
}

export interface WorkReportsSettingsPayload {
  autopost?: boolean
  autopublish?: boolean
  categories?: string[]
  limit?: number
  title?: LocalizedText
}

/**
 * Канонические ключи категорий, доступные для фильтра автопостинга. Зеркалит
 * `CANONICAL_CATEGORY_KEYS` из uk_management_bot/keyboards/requests.py — бэкенд
 * отклоняет всё, чего в том кортеже нет (см. `WorkReportsCfg._known_categories`).
 * Порядок — как в UI-меню бота: сначала 8 «менюшных», затем 3 остальных.
 */
export const WORK_REPORT_CATEGORY_KEYS = [
  'electricity',
  'plumbing',
  'heating',
  'elevator',
  'cleaning',
  'landscaping',
  'security',
  'internet',
  'ventilation',
  'repair',
  'other',
] as const

// Public feed — a DIFFERENT, narrower shape than WorkReport above (no
// request_number, no description, no user ids — this is what unauthenticated
// visitors see, mirrors the backend's PublicWorkReportOut).
export interface PublicWorkReport {
  id: number
  category_key: string
  address: string
  completed_on: string
  before: number[]
  after: number[]
}

export interface PublicWorkReportsPage {
  items: PublicWorkReport[]
  total: number
  limit: number
  offset: number
}
