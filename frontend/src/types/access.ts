/**
 * Типы домена контроля доступа (access_control) — зеркало DTO бэкенда
 * `uk-access-api` (access_control/api/registry.py + operator.py).
 *
 * Конверт списков единый: `{ items, total, limit, offset }`. Детали — плоские
 * объекты (camera_event + цепочки решений/команд/ручных открытий).
 */

// ── Конверт страницы списка ─────────────────────────────────────────────────
export interface AccessPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ── События (история проездов) ──────────────────────────────────────────────
export interface AccessEventRow {
  id: number
  event_id: string
  controller_id: number
  zone_id: number | null
  gate_id: number | null
  direction: string
  plate_number_normalized: string | null
  captured_at: string
  occurred_at: string | null
  source: string
  decision: string | null
  status: string | null
  reason: string | null
  decision_id: number | null
  resolved_by_user_id: number | null
  has_command: boolean
  // Фото проезда (§11): обзорное фото авто и фото номера. Строка списка теперь
  // отдаёт их вместе с детальной camera_event (str | null, опц. для совместимости).
  plate_photo_url?: string | null
  overview_photo_url?: string | null
}

export interface AccessEventsFilters {
  decision?: string
  zone_id?: number
  gate_id?: number
  plate?: string
  date_from?: string
  date_to?: string
  source?: string
  limit?: number
  offset?: number
}

// ── Деталь события ──────────────────────────────────────────────────────────
export interface CameraEventDetail {
  id: number
  event_id: string
  controller_id: number
  zone_id: number | null
  gate_id: number | null
  camera_id: number | null
  direction: string
  plate_number_original: string | null
  plate_number_normalized: string | null
  confidence: number | null
  captured_at: string
  received_at: string | null
  source: string
  plate_photo_url: string | null
  overview_photo_url: string | null
  vehicle_class: string | null
  color: string | null
}

export interface DecisionRow {
  id: number
  decision: string
  status: string
  reason: string | null
  decision_group_id: string | null
  supersedes_decision_id: number | null
  resolved_by_user_id: number | null
  resolved_at: string | null
  review_deadline_at: string | null
  created_at: string
  prev_hash: string | null
  row_hash: string | null
}

export interface CommandRow {
  command_id: string
  decision_id: number | null
  barrier_id: number
  controller_id: number
  command_type: string
  status: string
  attempts: number
  created_at: string
  leased_at: string | null
  acked_at: string | null
  dead_at: string | null
}

export interface ManualOpeningRow {
  id: number
  barrier_id: number
  command_id: string | null
  decision_id: number | null
  operator_user_id: number
  reason: string
  created_at: string
}

export interface AccessEventDetail {
  camera_event: CameraEventDetail
  decisions: DecisionRow[]
  barrier_commands: CommandRow[]
  manual_openings: ManualOpeningRow[]
}

// ── Авто (база данных) ──────────────────────────────────────────────────────
export interface ApartmentLink {
  apartment_id: number
  relation_type: string
  status: string
  valid_from: string | null
  valid_until: string | null
  approved_by_user_id: number | null
  approved_at: string | null
}

export interface VehicleRow {
  id: number
  plate_number_original: string
  plate_number_normalized: string
  plate_country: string | null
  plate_type: string | null
  brand: string | null
  model: string | null
  color: string | null
  vehicle_class: string | null
  status: string
  blocked_reason: string | null
  blocked_by_user_id: number | null
  blocked_at: string | null
  apartments: ApartmentLink[]
}

export interface VehiclesFilters {
  status?: string
  plate?: string
  apartment_id?: number
  limit?: number
  offset?: number
}

export interface VehicleEventRow {
  id: number
  event_id: string
  captured_at: string
  direction: string
  gate_id: number | null
  zone_id: number | null
  decision: string | null
  status: string | null
}

export interface VehicleDetail {
  vehicle: VehicleRow
  apartments: ApartmentLink[]
  recent_events: VehicleEventRow[]
}

// ── Пропуска ────────────────────────────────────────────────────────────────
export interface PassRow {
  id: number
  pass_type: string
  apartment_id: number
  created_by_user_id: number | null
  zone_id: number | null
  plate_number_original: string | null
  plate_number_normalized: string | null
  valid_from: string | null
  valid_until: string | null
  max_entries: number
  used_entries: number
  status: string
  source: string | null
  created_at: string
}

export interface PassesFilters {
  pass_type?: string
  status?: string
  apartment_id?: number
  limit?: number
  offset?: number
}

// ── Заявки жителей ──────────────────────────────────────────────────────────
export interface AccessRequestRow {
  id: number
  apartment_id: number
  created_by_user_id: number
  vehicle_id: number | null
  plate_number_original: string | null
  plate_number_normalized: string | null
  relation_type: string | null
  status: string
  reviewed_by_user_id: number | null
  reviewed_at: string | null
  review_comment: string | null
  created_at: string
}

export interface AccessRequestsFilters {
  status?: string
  apartment_id?: number
  limit?: number
  offset?: number
}

// ── Действия охраны (operator.py) ───────────────────────────────────────────
export interface ResolvePayload {
  action: 'manual_open' | 'deny'
  barrier_id?: number
  reason: string
  decision_id?: number
}

export interface ResolveResponse {
  ok: boolean
  decision_id: number
  status: string
}

export interface ManualOpenResponse {
  ok: boolean
  command_id: string
  barrier_id: number
}

// ── Действия менеджера: мутации базы доступа (registry.py) ───────────────────
/** Связь авто с квартирой (POST /vehicles). */
export type VehicleRelationType = 'owner' | 'tenant' | 'family' | 'service'

/** Тело POST /vehicles — создание авто менеджером. */
export interface CreateVehiclePayload {
  plate_number_original: string
  plate_country?: string
  plate_type?: string
  brand?: string
  model?: string
  color?: string
  vehicle_class?: string
  apartment_id?: number
  relation_type?: VehicleRelationType
  zone_id?: number
}

/** Статусы авто для PATCH /vehicles/{id}/status. */
export type VehicleStatus = 'active' | 'blocked' | 'archived'

/** Тело PATCH /vehicles/{id}/status. reason обязателен при status=blocked. */
export interface UpdateVehicleStatusPayload {
  status: VehicleStatus
  reason?: string
}

/** Тело POST /passes/taxi — разовый/временный taxi-пропуск. */
export interface CreateTaxiPassPayload {
  apartment_id: number
  zone_id: number
  valid_until: string
  plate_number_original?: string
  valid_from?: string
  max_entries?: number
}

/** Тело POST /requests/{id}/review — рассмотрение заявки жителя. */
export interface ReviewRequestPayload {
  action: 'approve' | 'reject'
  comment?: string
  zone_id?: number
}

export interface ReviewRequestResponse {
  ok: boolean
  request_id: number
  status: string
  vehicle_id: number | null
  replayed: boolean
}
