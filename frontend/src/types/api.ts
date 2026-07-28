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

export interface DayStats {
  date: string
  created: number
  closed: number
}

export interface ExecutorStat {
  user_id: number
  name: string | null
  completed: number
  avg_hours: number | null
  score: number
}

export interface ActivityItem {
  event_type: string
  request_number: string
  executor_name: string | null
  created_at: string
}

export interface RequestStatsOut {
  by_day: DayStats[]
  by_category: Record<string, number>
  by_status: Record<string, number>
  top_executors: ExecutorStat[]
  recent_actions: ActivityItem[]
  total_requests: number
  avg_resolution_hours: number | null
  avg_satisfaction: number | null
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
