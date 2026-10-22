// src/types/api.ts
// Centralised API response types — single source of truth

// 'requested' — менеджер запросил документы; ось верификации жителя
// (users.verification_status), общая с сотрудниками.
export type VerificationStatus = 'verified' | 'rejected' | 'pending' | 'requested'
export type ShiftStatus = 'active' | 'completed' | 'cancelled' | 'planned' | 'paused'
export type ShiftType = 'regular' | 'emergency' | 'overtime' | 'maintenance'
export type AnalyticsPeriod = '7d' | '30d' | '90d'

export interface EmployeeBrief {
  id: number
  first_name: string | null
  last_name: string | null
  phone: string | null
  specialization: string[]
  active_shift_id: number | null
  verification_status: VerificationStatus
  status: string
  roles: string[]
  /** Сотрудник заблокировал бота. */
  bot_blocked: boolean
  /** Простой режим исполнителя в Mini App (включает менеджер). */
  simple_mode: boolean
  /** Язык профиля: ru / uz (латиница) / uz_cyrl (кириллица). */
  language: string
}

export interface ShiftBrief {
  id: number
  user_id: number | null
  executor_name: string | null
  status: string
  shift_type: string | null
  start_time: string
  end_time: string | null
  max_requests: number
  current_request_count: number
  load_percentage: number
  // Surfaced on Brief so week/month views can color-code rows + drive the
  // SpecializationSidebar without re-fetching ShiftDetail for each shift.
  specialization_focus: string[] | null
}

export interface ShiftDetail extends ShiftBrief {
  notes: string | null
  specialization_focus: string[] | null
  coverage_areas: unknown[] | null
  priority_level: number
  completed_requests: number
  efficiency_score: number | null
  quality_rating: number | null
  template_id: number | null
  created_at: string | null
}

export interface EmployeeDetail extends EmployeeBrief {
  active_shift: ShiftBrief | null
  rating: number | null
  total_shifts: number
  total_completed: number
}

export interface TransferOut {
  id: number
  shift_id: number
  from_executor_name: string | null
  to_executor_name: string | null
  status: string
  reason: string
  urgency_level: string
  comment: string | null
  created_at: string
}

export interface ShiftStatsOut {
  active_shifts: number
  active_executors: number
  coverage_pct: number
  avg_efficiency: number | null
  shifts_today: number
  pending_transfers: number
}

export interface TemplateBrief {
  id: number
  name: string
  description: string | null
  start_hour: number
  start_minute: number
  duration_hours: number
  default_shift_type: string
  days_of_week: number[] | null
  recurrence_mode?: 'weekday' | 'cycle'
  cycle_days_on?: number | null
  cycle_days_off?: number | null
  cycle_anchor_date?: string | null
  is_active: boolean
  min_executors: number
  max_executors: number
  auto_create: boolean
  required_specializations: string[] | null
  default_max_requests: number
  priority_level: number
}

// ── Аналитика заявок (/api/v2/requests/stats*) ──────────────────────────────
// Зеркало uk_management_bot/api/requests/stats_router.py. Даты периода —
// бизнес-даты YYYY-MM-DD включительно.

export type StatsGranularity = 'day' | 'month' | 'year'

export interface StatsSeriesPoint {
  bucket: string
  created: number
  accepted: number
}

export interface StatsKpi {
  created: number
  accepted: number
  avg_assign_hours: number | null
  avg_work_hours: number | null
  avg_to_accept_hours: number | null
  avg_satisfaction: number | null
  returned: number
}

export interface RequestStatsOut {
  date_from: string
  date_to: string
  granularity: StatsGranularity
  series: StatsSeriesPoint[]
  by_category: Record<string, number>
  open_by_status: Record<string, number>
  kpi: StatsKpi
  previous: StatsKpi
}

/** Вкладка «Отчёт»: `all` — поступившие в периоде, `done` — принятые в периоде. */
export type ReportScope = 'all' | 'done'

export interface ReportRequestRow {
  request_number: string
  created_at: string | null
  status: string
  category: string
  urgency: string
  address: string | null
  executor_name: string | null
  completed_at: string | null
  /** Только у принятых: уложились ли в норматив. */
  on_time: boolean | null
}

export interface ReportRequestsOut {
  rows: ReportRequestRow[]
  truncated: boolean
}

export interface ExecutorStatsRow {
  user_id: number | null
  name: string | null
  executed: number
  accepted: number
  returned: number
  overdue: number
  avg_work_hours: number | null
  avg_to_accept_hours: number | null
  avg_rating: number | null
  ratings_count: number
  in_work_now: number
  materials_cost: number
}

export interface UrgencySla {
  urgency: string
  sla_hours: number
  accepted: number
  measured: number
  median_hours: number | null
  p90_hours: number | null
  overdue: number
}

export interface QualityStatsOut {
  sla_hours: Record<string, number>
  by_urgency: UrgencySla[]
  returns_by_category: { category: string; accepted: number; returned: number }[]
  ratings: Record<string, number>
  recent_reviews: {
    request_number: string
    rating: number
    review: string
    executor_name: string | null
    completed_at: string | null
  }[]
}

export interface BacklogOpenRequest {
  request_number: string
  status: string
  category: string
  created_at: string
  executor_id: number | null
  executor_name: string | null
  age_days: number
}

export interface BacklogOut {
  total: number
  by_age: Record<string, number>
  queues: { user_id: number | null; name: string | null; open: number; oldest_age_days: number }[]
  oldest: BacklogOpenRequest[]
}

export interface AddressStatsOut {
  buildings: { id: number; name: string; count: number }[]
  yards: { id: number; name: string; count: number }[]
  repeats: {
    request_number: string
    previous_number: string
    address: string | null
    category: string
    days_after: number
  }[]
}

export interface ChannelStatsOut {
  granularity: StatsGranularity
  totals: Record<string, number>
  series: { bucket: string; counts: Record<string, number> }[]
}

export interface CostStatsOut {
  total: number
  requests_with_materials: number
  accepted: number
  by_category: Record<string, number>
  by_building: { id: number; name: string; amount: number }[]
}

export interface CreateTemplatePayload {
  name: string
  description?: string | null
  start_hour: number
  start_minute: number
  duration_hours: number
  default_shift_type: string
  days_of_week?: number[]
  recurrence_mode?: 'weekday' | 'cycle'
  cycle_days_on?: number | null
  cycle_days_off?: number | null
  cycle_anchor_date?: string | null
  required_specializations?: string[]
  min_executors?: number
  max_executors?: number
  default_max_requests?: number
  auto_create?: boolean
  priority_level?: number
}

// Address management
export interface YardBrief {
  id: number
  name: string
  description: string | null
  gps_latitude: number | null
  gps_longitude: number | null
  is_active: boolean
  created_at: string | null
  buildings_count: number
}

export interface BuildingBrief {
  id: number
  address: string
  yard_id: number
  yard_name: string | null
  entrance_count: number
  floor_count: number
  description: string | null
  gps_latitude: number | null
  gps_longitude: number | null
  is_active: boolean
  created_at: string | null
  apartments_count: number
}

export interface ApartmentBrief {
  account_number?: string | null
  id: number
  building_id: number
  apartment_number: string
  building_address: string | null
  yard_name: string | null
  entrance: number | null
  floor: number | null
  rooms_count: number | null
  area: number | null
  description: string | null
  is_active: boolean
  created_at: string | null
  residents_count: number
}

/** Житель В КАРТОЧКЕ КВАРТИРЫ (адресный раздел) — не путать с ResidentListItem
 *  раздела «Жители»: там строка списка людей, здесь строка жильцов квартиры. */
export interface ApartmentResidentBrief {
  id: number
  user_id: number
  user_name: string | null
  user_phone: string | null
  username: string | null
  is_owner: boolean
  is_primary: boolean
  status: string
  requested_at: string | null
  reviewed_at: string | null
}

export interface ApartmentDetail {
  account_number?: string | null
  id: number
  building_id: number
  apartment_number: string
  building_address: string | null
  yard_name: string | null
  entrance: number | null
  floor: number | null
  rooms_count: number | null
  area: number | null
  description: string | null
  is_active: boolean
  created_at: string | null
  residents: ApartmentResidentBrief[]
}

export interface ModerationItem {
  id: number
  user_id: number
  user_name: string | null
  user_phone: string | null
  apartment_id: number
  apartment_number: string
  building_address: string | null
  yard_name: string | null
  status: string
  is_owner: boolean
  is_primary: boolean
  requested_at: string | null
}

export interface AddressStats {
  yards_total: number
  yards_active: number
  buildings_total: number
  buildings_active: number
  apartments_total: number
  apartments_active: number
  residents_approved: number
  residents_pending: number
}

// ── Раздел «Жители» (/api/v2/residents) ──────────────────────────────

export interface ResidentListItem {
  id: number
  telegram_id: number
  username: string | null
  first_name: string | null
  last_name: string | null
  phone: string | null
  /** Ось аккаунта: pending | approved | blocked. */
  status: string
  /** Ось верификации — независима от статуса аккаунта. */
  verification_status: VerificationStatus
  language: string | null
  created_at: string | null
  /** Привязки approved+pending; rejected не считается принадлежностью. */
  apartments_count: number
  /** «Двор · дом · кв. N» основной квартиры или null. */
  primary_address: string | null
  /** Пользователь заблокировал бота — запрос номера/уведомления недоставимы. */
  bot_blocked: boolean
}

export interface ResidentListResponse {
  items: ResidentListItem[]
  total: number
  limit: number
  offset: number
}

export interface ResidentStats {
  total: number
  pending: number
  approved: number
  blocked: number
  verification_pending: number
  verification_requested: number
  verified: number
  verification_rejected: number
}

export interface ResidentApartment {
  /** id связи user_apartments, НЕ квартиры. */
  id: number
  apartment_id: number
  apartment_number: string
  building_id: number
  building_address: string | null
  yard_id: number
  yard_name: string | null
  status: string
  is_owner: boolean
  is_primary: boolean
  requested_at: string | null
  reviewed_at: string | null
  admin_comment: string | null
}

export interface ResidentDocument {
  id: number
  document_type: string
  file_name: string | null
  file_size: number | null
  verification_status: string | null
  created_at: string | null
}

export interface ResidentVerification {
  id: number
  status: string | null
  requested_info: unknown
  requested_at: string | null
  requested_by: number | null
  admin_notes: string | null
  verified_by: number | null
  verified_at: string | null
  created_at: string | null
}

export interface ResidentProfile {
  id: number
  telegram_id: number
  username: string | null
  first_name: string | null
  last_name: string | null
  phone: string | null
  status: string
  verification_status: VerificationStatus
  verification_notes: string | null
  verification_date: string | null
  language: string | null
  created_at: string | null
  /** Все роли: блокировка общая на все, поэтому мультиролевым её прячем. */
  roles: string[]
  apartments: ResidentApartment[]
  documents: ResidentDocument[]
  latest_verification: ResidentVerification | null
}

export interface BulkCreateResult {
  created: number
  skipped: number
  errors: string[]
}
