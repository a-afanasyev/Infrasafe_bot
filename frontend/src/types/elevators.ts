/**
 * Типы модуля «Лифты» (/api/v2/elevators). Повторяют один в один
 * `uk_management_bot/api/elevators/schemas.py` — источник истины; при правке
 * схем менять синхронно (openapi.json пока модуль не содержит).
 */

export type ElevatorStatus = 'working' | 'not_working' | 'under_repair' | 'maintenance'
export type OccurrenceKind = 'maintenance' | 'certification'
export type OccurrenceState = 'planned' | 'done' | 'cancelled'
export type CalendarState = OccurrenceState | 'all'
export type RegistryFlag = 'no_contract' | 'cert_expired' | 'maintenance_overdue'

export const ELEVATOR_STATUSES: readonly ElevatorStatus[] = [
  'working',
  'not_working',
  'under_repair',
  'maintenance',
] as const

/**
 * Р18: статусы «по лифту идут работы». Канон бэкенда —
 * `services/elevator_service/validation.py::WORKS_STATUSES`: по такому лифту
 * заявка самообслуживания (житель) запрещена, персоналу — разрешена.
 */
export const ELEVATOR_WORKS_STATUSES: readonly ElevatorStatus[] = ['under_repair', 'maintenance'] as const

export function isElevatorUnderWorks(status: ElevatorStatus | null | undefined): boolean {
  return status != null && (ELEVATOR_WORKS_STATUSES as readonly string[]).includes(status)
}

export const OCCURRENCE_KINDS: readonly OccurrenceKind[] = ['maintenance', 'certification'] as const
export const REGISTRY_FLAGS: readonly RegistryFlag[] = [
  'no_contract',
  'cert_expired',
  'maintenance_overdue',
] as const

/** База API модуля; путь `for-building` нужен и TWA (свой axios-клиент). */
export const ELEVATORS_API_BASE = '/api/v2/elevators'
export function elevatorsForBuildingPath(buildingId: number): string {
  return `${ELEVATORS_API_BASE}/for-building/${buildingId}`
}

/** Максимум номеров в одном bulk-confirm (MAX_BULK_CONFIRM на бэке). */
export const MAX_BULK_CONFIRM = 50
/** Максимум длины причины (MAX_REASON_LEN на бэке). */
export const MAX_REASON_LEN = 500

/**
 * Статусы заявки, из которых менеджер может подтвердить (MANAGER_CONFIRM).
 * Канон — `utils/request_workflow/specs.py`: from={Выполнена} → Исполнено.
 */
export const CONFIRMABLE_REQUEST_STATUSES: readonly string[] = ['Выполнена'] as const

// ── Вход ────────────────────────────────────────────────────────────

export interface ElevatorPassportOptionalIn {
  factory_number?: string | null
  model?: string | null
  production_year?: number | null
  capacity_kg?: number | null
  floors_served?: string | null
  service_org_name?: string | null
  service_org_phone?: string | null
  contract_number?: string | null
  contract_until?: string | null
  cert_number?: string | null
  cert_valid_until?: string | null
  cert_act_url?: string | null
  downtime_reason?: string | null
  spare_part_expected_on?: string | null
  publish_downtime_details?: boolean | null
  is_public?: boolean | null
}

export interface ElevatorCreateIn extends ElevatorPassportOptionalIn {
  building_id: number
  entrance_number: number
  elevator_number: number
  passport_number: string
  manufacturer: string
  serial_number: string
}

export interface ElevatorPatchIn extends ElevatorPassportOptionalIn {
  building_id?: number
  entrance_number?: number
  elevator_number?: number
  passport_number?: string
  manufacturer?: string
  serial_number?: string
  expected_version?: number
}

export interface ElevatorStatusIn {
  status: ElevatorStatus
  reason?: string | null
  request_number?: string | null
}

export interface ElevatorOccurrenceGenerateIn {
  kind: OccurrenceKind
  start: string
  every_months: number
  count: number
}

export interface ElevatorOccurrenceCompleteIn {
  comment?: string | null
  done_at?: string | null
  cert_number?: string | null
  cert_valid_until?: string | null
  cert_act_url?: string | null
  request_number?: string | null
}

export interface ElevatorsDowntimeThresholds {
  not_working: number | null
  under_repair: number | null
}

export interface ElevatorsResidentNotifications {
  repair_started: boolean
  maintenance_started: boolean
  back_in_service: boolean
}

export interface ElevatorsStaffReminders {
  maintenance: number[]
  certification: number[]
  contract: number[]
  overdue_weekly: boolean
}

export interface ElevatorsConfigOut {
  module_public: boolean
  /** Р18a: разрешить жителю заявку по лифту «В ремонте»/«На ТО» (дефолт false). */
  allow_resident_requests_under_works: boolean
  downtime_threshold_days: ElevatorsDowntimeThresholds
  resident_notifications: ElevatorsResidentNotifications
  staff_reminders: ElevatorsStaffReminders
}

/** PUT /config — все секции опциональны (частичное обновление). */
export interface ElevatorsConfigIn {
  module_public?: boolean
  allow_resident_requests_under_works?: boolean
  downtime_threshold_days?: Partial<ElevatorsDowntimeThresholds>
  resident_notifications?: Partial<ElevatorsResidentNotifications>
  staff_reminders?: Partial<ElevatorsStaffReminders>
}

/**
 * Поля колл-центра для «Создать ремонт» (Ф4a-1): адрес уровня дома —
 * `building_id` (без него сервер отвечает 422), `address` — только для
 * читаемости, сервер его игнорирует при заданном доме.
 */
export interface ElevatorRepairIn {
  category: 'elevator'
  urgency: string
  description: string
  building_id: number
  address: string
  elevator_id: number
  elevator_operational: false
  acceptance_mode: 'manager'
}

// ── Выход ───────────────────────────────────────────────────────────

export interface ElevatorFlags {
  no_contract: boolean
  cert_expired: boolean
  maintenance_overdue: boolean
}

export interface ElevatorCard {
  id: number
  building_id: number
  building_address: string
  yard_id: number
  yard_name: string | null
  entrance_number: number
  elevator_number: number
  label: string
  current_status: ElevatorStatus | null
  status_since: string | null
  is_commissioned: boolean
  archived_at: string | null
  is_public: boolean
  flags: ElevatorFlags
  availability_30d: number | null
  open_requests_count: number
}

export interface ElevatorDetail extends ElevatorCard {
  passport_number: string
  manufacturer: string
  serial_number: string
  factory_number: string | null
  model: string | null
  production_year: number | null
  capacity_kg: number | null
  floors_served: string | null
  commissioned_at: string | null
  downtime_reason: string | null
  spare_part_expected_on: string | null
  publish_downtime_details: boolean
  service_org_name: string | null
  service_org_phone: string | null
  contract_number: string | null
  contract_until: string | null
  cert_number: string | null
  cert_valid_until: string | null
  cert_act_url: string | null
  public_code: string
  archived_reason: string | null
  apartments_without_entrance_count: number
  version: number
  created_at: string | null
  updated_at: string | null
}

/** GET /for-building/{building_id} — лифт для выбора в заявке. */
export interface ElevatorMiniOut {
  id: number
  entrance_number: number
  elevator_number: number
  label: string
  current_status: ElevatorStatus | null
  /** С какого момента текущий статус — показывается в отказе Р18. */
  status_since?: string | null
  /**
   * Р18a: готовый вердикт сервера «жителю по этому лифту заявку нельзя»
   * (статус × тумблер `allow_resident_requests_under_works`). Клиент про
   * конфиг не знает; поле опционально ради совместимости со старым ответом.
   */
  resident_request_blocked?: boolean
}

export interface ElevatorListOut {
  items: ElevatorCard[]
  total: number
}

export interface ElevatorStatusChangeOut {
  changed: boolean
  old_status: ElevatorStatus | null
  new_status: ElevatorStatus | null
  status_since: string | null
  notified_residents: number
}

export interface ElevatorEvent {
  id: number
  elevator_id: number
  event_kind: string
  old_status: string | null
  new_status: string | null
  occurred_at: string
  actor_user_id: number | null
  source: string
  request_number: string | null
  reason: string | null
  payload: Record<string, unknown> | null
}

export interface ElevatorOccurrence {
  id: number
  elevator_id: number
  elevator_label: string
  kind: OccurrenceKind
  due_on: string
  state: OccurrenceState
  done_at: string | null
  done_by_user_id: number | null
  comment: string | null
  request_number: string | null
  created_at: string | null
}

export interface ElevatorRequestRow {
  request_number: string
  status: string
  category: string
  urgency: string
  created_at: string | null
  elevator_operational: boolean | null
  executor_name: string | null
  applicant_name: string | null
}

export interface ElevatorBulkConfirmItem {
  request_number: string
  ok: boolean
  error_kind: string | null
  error: string | null
}

export interface ElevatorCounters {
  total: number
  by_status: Record<string, number>
  no_contract: number
  cert_expired: number
  maintenance_overdue: number
  downtime_over_threshold: number
}

export interface ElevatorYardSummary {
  yard_id: number
  yard_name: string
  counters: ElevatorCounters
}

export interface ElevatorSummary {
  today: string
  totals: ElevatorCounters
  yards: ElevatorYardSummary[]
  requests_without_elevator: number
  downtime_threshold_days: ElevatorsDowntimeThresholds
}

// ── Фильтры ─────────────────────────────────────────────────────────

export interface ElevatorListFilters {
  yard_id?: number
  building_id?: number
  status?: ElevatorStatus
  flag?: RegistryFlag[]
  include_archived?: boolean
  limit?: number
  offset?: number
}

export interface OccurrenceFilters {
  kind?: OccurrenceKind
  state?: CalendarState
  from?: string
  to?: string
}
