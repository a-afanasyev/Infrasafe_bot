// src/types/api.ts
// Centralised API response types — single source of truth

export type VerificationStatus = 'verified' | 'rejected' | 'pending'
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

export interface ResidentBrief {
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
  residents: ResidentBrief[]
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

export interface BulkCreateResult {
  created: number
  skipped: number
  errors: string[]
}
