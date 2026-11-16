/** Типы API модуля «Уборка» (/api/v2/cleaning, см. docs/tech/openapi.json). */

export type CleaningWorkKind = 'wet' | 'dry' | 'elevator' | 'parking'

export interface CleaningPlanItem {
  work_kind: CleaningWorkKind
  /** 0 = понедельник … 6 = воскресенье. */
  weekdays: number[]
  /** Нет поля — все подъезды. */
  entrances?: number[]
  /** Нет полей — все этажи. */
  floor_from?: number
  floor_to?: number
}

export interface CleaningPlan {
  id: number
  valid_from: string
  valid_to: string | null
  items: CleaningPlanItem[]
  extra_points: string[]
  floor_count: number
  entrance_count: number
}

export interface CleaningPlanView {
  building_id: number
  floor_count: number
  entrance_count: number
  current: CleaningPlan | null
  upcoming: CleaningPlan | null
  uncovered: Record<string, number[]>
  snapshot_mismatch: boolean
}

export interface CleaningBuilding {
  id: number
  address: string
  yard_id: number
  floor_count: number
  entrance_count: number
  has_plan: boolean
  show_to_residents: boolean
  show_photos: boolean
  entrances: { entrance: number; user_id: number | null }[]
}

export interface CleaningEntranceRef {
  building_id: number
  entrance: number
}

export interface CleaningStaffMember {
  user_id: number
  first_name: string | null
  last_name: string | null
  entrances: CleaningEntranceRef[]
  by_weekday: number[]
  buildings: Record<string, number[]>
  week: number
  peak: number
  percent: number
  overloaded: boolean
}

export interface CleaningStaff {
  norm: number
  cleaners: CleaningStaffMember[]
  unassigned: CleaningEntranceRef[]
}

export interface CleaningRules {
  version: number | null
  data: Record<string, string | number | boolean>
}

// ── контроль ────────────────────────────────────────────────────────────────

export type CleaningTaskStatus = 'planned' | 'in_progress' | 'accepted' | 'review' | 'rejected' | 'missed' | 'expired'

export interface CleaningTaskRow {
  id: number
  building_id: number
  address: string
  entrance: number
  work_date: string
  status: CleaningTaskStatus
  responsible_id: number | null
  slots_total: number
  slots_done: number
  sampled: boolean | null
}

export interface CleaningTasks {
  date_from: string
  date_to: string
  tasks: CleaningTaskRow[]
}

export interface CleaningPhotoInfo {
  id: number
  slot: string
  outcome: string | null
  refusal_code: string | null
  trust_level: string | null
  received_at: string
  client_captured_at: string | null
  has_file: boolean
}

export interface CleaningEvent {
  kind: string
  actor_id: number | null
  from_status: string | null
  to_status: string | null
  reason: string | null
  payload: { reasons?: string[]; sampled?: boolean } | null
  created_at: string | null
}

export interface CleaningComplaint {
  id: number
  building_id: number
  entrance: number
  work_date: string
  author_id: number
  task_id: number | null
  request_number: string | null
  outcome: 'pending' | 'confirmed' | 'unfounded'
  created_at: string | null
}

export interface CleaningTaskCard {
  task: CleaningTaskRow
  version: number
  works: string[]
  slots_required: string[]
  session_opened_at: string | null
  current: CleaningPhotoInfo[]
  evidence: CleaningPhotoInfo[]
  other: CleaningPhotoInfo[]
  events: CleaningEvent[]
  complaints: CleaningComplaint[]
}

export interface CleaningTimesheetRow {
  user_id: number
  first_name: string | null
  last_name: string | null
  planned: number
  accepted: number
  rejected: number
  expired: number
  missed: number
  complaints: number
  confirmed: number
  percent: number
}
