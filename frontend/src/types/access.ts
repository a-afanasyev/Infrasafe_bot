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

// ── Погашение одноразового гостевого кода (operator.py, §9.3) ─────────────────
/** Тело POST /passes/redeem-code — оператор гасит 8-значный код гостя. */
export interface RedeemCodePayload {
  code: string
  barrier_id?: number
}

/**
 * Ответ POST /passes/redeem-code (200): код принят, пропуск погашен, команда
 * шлагбауму создана. Раскрытие после успеха (§9.3): оператору показывается
 * квартира + тип пропуска. Неверный код → 422 {error:"code_invalid"},
 * блокировка по числу попыток → 429 {error:"too_many_attempts"} (общие тексты,
 * без раскрытия деталей).
 */
export interface RedeemCodeResponse {
  apartment_id: number
  pass_type: string
  valid_until: string | null
  command: { command_id: string; barrier_id: number }
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

// ── Оборудование (admin/equipment) ───────────────────────────────────────────
// Зеркало DTO бэкенда access_control/api/admin.py. RBAC: зоны/въезды —
// manager+system_admin; камеры/шлагбаумы/контроллеры — только system_admin.

/** Режим работы offline (зона/контроллер): закрыто при сбое vs кэш постоянных. */
export type OfflineMode = 'fail_closed' | 'cached_permanent_only'

/** Направление точки проезда/камеры. */
export type GateDirection = 'entry' | 'exit'

// Зоны ────────────────────────────────────────────────────────────────────────
export interface ZoneRow {
  id: number
  code: string
  name: string
  description: string | null
  offline_mode: OfflineMode
  max_permanent_per_apartment: number | null
  is_active: boolean
  yard_ids?: number[]
}

export interface CreateZonePayload {
  code: string
  name: string
  description?: string
  offline_mode: OfflineMode
  max_permanent_per_apartment?: number
  is_active?: boolean
}

export type UpdateZonePayload = Partial<CreateZonePayload>

/** Тело POST /admin/zones/{id}/yards — привязка/отвязка фаз (yards). */
export interface ZoneYardsPayload {
  add?: number[]
  remove?: number[]
}

export interface ZoneYardsResponse {
  zone_id: number
  yard_ids: number[]
}

// Въезды (точки проезда) ────────────────────────────────────────────────────
export interface GateRow {
  id: number
  code: string
  zone_id: number
  direction: GateDirection
  name: string | null
  is_active: boolean
}

export interface CreateGatePayload {
  code: string
  zone_id: number
  direction: GateDirection
  name?: string
  is_active?: boolean
}

export type UpdateGatePayload = Partial<CreateGatePayload>

// Камеры ──────────────────────────────────────────────────────────────────────
export interface CameraRow {
  id: number
  code: string
  gate_id: number
  direction: GateDirection
  name: string | null
  vendor: string | null
  model: string | null
  attributes: Record<string, unknown> | null
  is_active: boolean
}

export interface CreateCameraPayload {
  code: string
  gate_id: number
  direction: GateDirection
  name?: string
  vendor?: string
  model?: string
  attributes?: Record<string, unknown>
  is_active?: boolean
}

export type UpdateCameraPayload = Partial<CreateCameraPayload>

// Шлагбаумы ─────────────────────────────────────────────────────────────────
export interface BarrierRow {
  id: number
  code: string
  gate_id: number
  name: string | null
  relay_type: string | null
  relay_channel: number | null
  config: Record<string, unknown> | null
  is_active: boolean
}

export interface CreateBarrierPayload {
  code: string
  gate_id: number
  name?: string
  relay_type?: string
  relay_channel?: number
  config?: Record<string, unknown>
  is_active?: boolean
}

export type UpdateBarrierPayload = Partial<CreateBarrierPayload>

// Контроллеры ─────────────────────────────────────────────────────────────────
// ВАЖНО: ControllerRow (ответ GET) НЕ содержит api_key. Ключ отдаётся в открытом
// виде РОВНО ОДИН РАЗ — при создании и при ротации (отдельные response-типы).
export interface ControllerRow {
  id: number
  controller_uid: string
  name: string | null
  zone_id: number | null
  gate_id: number | null
  offline_mode: OfflineMode | null
  ip_allowlist: string[] | null
  pinned_public_key_id: string | null
  status: string | null
  is_active: boolean
}

export interface CreateControllerPayload {
  controller_uid: string
  name?: string
  zone_id?: number
  gate_id?: number
  offline_mode?: OfflineMode
  ip_allowlist?: string[]
  pinned_public_key_id?: string
  status?: string
  is_active?: boolean
}

export type UpdateControllerPayload = Partial<CreateControllerPayload>

/** Ответ POST /admin/controllers — строка + api_key (PLAINTEXT, один раз). */
export interface ControllerCreateResponse extends ControllerRow {
  api_key: string
}

/** Ответ POST /admin/controllers/{id}/rotate-key — новый ключ (один раз). */
export interface RotateKeyResponse {
  controller_id: number
  controller_uid: string
  api_key: string
}

/**
 * Тело POST /admin/controllers/{id}/test-event — синтетическая диагностика
 * точки въезда. Все поля опциональны (бэкенд подставляет дефолты:
 * plate_number=DIAG0001, direction=entry, confidence=0.99).
 */
export interface TestEventPayload {
  plate_number?: string
  direction?: GateDirection
  confidence?: number
}

/**
 * Ответ POST /admin/controllers/{id}/test-event — результат прогона
 * синтетического ANPR-события через Decision Engine. `command` присутствует,
 * только если по решению была создана команда шлагбауму.
 */
export interface TestEventResponse {
  decision: string
  status: string
  reason: string | null
  decision_id: number | null
  event_id: string
  zone_id: number | null
  gate_id: number | null
  barrier_id: number | null
  command: { command_id: string; barrier_id: number } | null
}
