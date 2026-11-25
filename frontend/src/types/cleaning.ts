/** Типы API модуля «Уборка» (/api/v2/cleaning, см. docs/tech/openapi.json). */

export type CleaningWorkKind = 'wet' | 'dry' | 'elevator' | 'parking' | 'fire_stairs'

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

/** Площади мест общего пользования подъезда, м². Подъезд переопределяет «*» по полю/ключу. */
export interface CleaningEntranceAreas {
  typical?: number
  /** Отличающиеся этажи: «1», «-1», «16». */
  floors?: Record<string, number>
  /** Работы-точки плана: fire_stairs, parking, elevator. */
  points?: Partial<Record<CleaningWorkKind, number>>
}

export interface CleaningAreas {
  entrances: Record<string, CleaningEntranceAreas>
}

export interface CleaningAreasView {
  building_id: number
  floor_count: number
  entrance_count: number
  areas: CleaningAreas | null
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
  m2_by_weekday: number[]
  m2_peak: number
  m2_percent: number
  /** Дома без площадей — их м² в нагрузку не вошли. */
  missing_areas: number[]
  /** По м², если задана норма м², иначе по этажам. */
  overloaded: boolean
}

export interface CleaningStaff {
  norm: number
  /** 0 — норма м² не задана. */
  area_norm: number
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
