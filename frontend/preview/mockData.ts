/**
 * Синтетические PD-safe мок-данные для STANDALONE-превью экранов контроля
 * доступа (только для скриншотов; §11 — номера вымышленные, маскирование как
 * в проде). Формы объектов — зеркало src/types/access.ts.
 */
import type {
  AccessEventRow,
  AccessEventDetail,
  VehicleRow,
  PassRow,
  AccessRequestRow,
  ZoneRow,
  GateRow,
  CameraRow,
  BarrierRow,
  ControllerRow,
  SpotRow,
  AssignmentRow,
  TestEventResponse,
  RedeemCodeResponse,
} from '../src/types/access'
import type { AccessEvent } from '../src/hooks/useAccessSecurityFeed'

// Относительные времена, чтобы таймеры/«N мин назад» выглядели живыми.
const minAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

// ── Синтетические фото (§11): inline SVG data-URI, offline, без сети ──────────
// Обзорное «фото авто»: силуэт (кузов + колёса) + подпись. ~640x360 (16:9).
function overviewPhoto(caption: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" fill="#1f2937"/>
  <rect width="640" height="220" y="140" fill="#111827"/>
  <g fill="#94a3b8" stroke="#cbd5e1" stroke-width="3">
    <path d="M120 230 L180 160 L420 160 L500 230 Z"/>
    <rect x="100" y="225" width="420" height="50" rx="10"/>
  </g>
  <g fill="#0f172a" stroke="#e2e8f0" stroke-width="6">
    <circle cx="190" cy="280" r="34"/>
    <circle cx="430" cy="280" r="34"/>
  </g>
  <rect x="250" y="245" width="120" height="26" rx="4" fill="#fde68a"/>
  <text x="310" y="264" font-family="monospace" font-size="18" fill="#1f2937" text-anchor="middle">${caption}</text>
  <text x="320" y="50" font-family="sans-serif" font-size="22" fill="#e2e8f0" text-anchor="middle">обзор · ANPR</text>
</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

// «Фото номера»: широкий узкий номерной знак с синтетическим номером. ~600x150.
function platePhoto(plate: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="150" viewBox="0 0 600 150">
  <rect width="600" height="150" fill="#0f172a"/>
  <rect x="20" y="25" width="560" height="100" rx="10" fill="#f8fafc" stroke="#1e293b" stroke-width="4"/>
  <rect x="20" y="25" width="60" height="100" rx="10" fill="#1d4ed8"/>
  <text x="50" y="95" font-family="sans-serif" font-size="24" fill="#f8fafc" text-anchor="middle">UZ</text>
  <text x="330" y="98" font-family="monospace" font-size="56" font-weight="bold" fill="#0f172a" text-anchor="middle" letter-spacing="6">${plate}</text>
</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

// ── (A) Live-лента (PD-safe: маскированный хвост номера) ─────────────────────
export const liveEvents: AccessEvent[] = [
  {
    decision: 'allow',
    status: 'allowed',
    reason: 'permanent_vehicle_allowed',
    zone_id: 1,
    gate_id: 1,
    direction: 'entry',
    occurred_at: minAgo(0),
    plate_masked: '01A•••BC',
  },
  {
    decision: 'manual_review',
    status: 'pending_review',
    reason: 'manual_review_required',
    zone_id: 1,
    gate_id: 1,
    direction: 'entry',
    occurred_at: minAgo(2),
    plate_masked: '30B•••CD',
  },
  {
    decision: 'deny',
    status: 'denied',
    reason: 'vehicle_not_found',
    zone_id: 1,
    gate_id: 2,
    direction: 'entry',
    occurred_at: minAgo(5),
    plate_masked: '85C•••EF',
  },
  {
    decision: 'allow',
    status: 'allowed',
    reason: 'guest_vehicle_allowed',
    zone_id: 1,
    gate_id: 1,
    direction: 'exit',
    occurred_at: minAgo(8),
    plate_masked: '10D•••GH',
  },
  {
    decision: 'deny',
    status: 'denied',
    reason: 'access_expired',
    zone_id: 2,
    gate_id: 3,
    direction: 'entry',
    occurred_at: minAgo(12),
    plate_masked: '50E•••JK',
  },
]

// ── (A) Очередь ручной проверки (manual_review) ──────────────────────────────
// Подаётся в реальный ManualReviewQueue через предзаполненный кэш React-Query.
export const manualReviewEvents: AccessEventRow[] = [
  {
    id: 9101,
    event_id: 'evt-9101',
    controller_id: 1,
    zone_id: 1,
    gate_id: 1,
    direction: 'entry',
    plate_number_normalized: '30B777CD',
    captured_at: minAgo(2),
    occurred_at: minAgo(2),
    source: 'anpr',
    decision: 'manual_review',
    status: 'pending_review',
    reason: 'manual_review_required',
    decision_id: 5501,
    resolved_by_user_id: null,
    has_command: false,
    overview_photo_url: overviewPhoto('30B777CD'),
    plate_photo_url: platePhoto('30B777CD'),
    resident_confirmations: [{ user_id: 45, response: 'confirm', created_at: minAgo(1) }],
  },
  {
    id: 9102,
    event_id: 'evt-9102',
    controller_id: 1,
    zone_id: 1,
    gate_id: 2,
    direction: 'entry',
    plate_number_normalized: '85C123EF',
    captured_at: minAgo(6),
    occurred_at: minAgo(6),
    source: 'anpr',
    decision: 'manual_review',
    status: 'pending_review',
    reason: 'manual_review_required',
    decision_id: 5502,
    resolved_by_user_id: null,
    has_command: false,
    overview_photo_url: overviewPhoto('85C123EF'),
    plate_photo_url: platePhoto('85C123EF'),
  },
]

// ── (A) Деталь события (для демо крупных фото авто+номера) ───────────────────
export const eventDetail: AccessEventDetail = {
  camera_event: {
    id: 9101,
    event_id: 'evt-9101',
    controller_id: 1,
    zone_id: 1,
    gate_id: 1,
    camera_id: 4,
    direction: 'entry',
    plate_number_original: '30B 777 CD',
    plate_number_normalized: '30B777CD',
    confidence: 0.94,
    captured_at: minAgo(2),
    received_at: minAgo(2),
    source: 'anpr',
    overview_photo_url: overviewPhoto('30B777CD'),
    plate_photo_url: platePhoto('30B777CD'),
    vehicle_class: 'легковой',
    color: 'серебристый',
  },
  decisions: [
    {
      id: 5501,
      decision: 'manual_review',
      status: 'pending_review',
      reason: 'manual_review_required',
      decision_group_id: 'grp-9101',
      supersedes_decision_id: null,
      resolved_by_user_id: null,
      resolved_at: null,
      review_deadline_at: minAgo(-3),
      created_at: minAgo(2),
      prev_hash: null,
      row_hash: null,
    },
  ],
  barrier_commands: [],
  manual_openings: [],
  resident_confirmations: [
    { user_id: 45, response: 'confirm', created_at: minAgo(1) },
  ],
}

// ── (A/B) История проездов ───────────────────────────────────────────────────
export const historyEvents: AccessEventRow[] = [
  mkEvent(8801, '01A123BC', 'allow', 'allowed', 'permanent_vehicle_allowed', 'entry', 1, 1, 14),
  mkEvent(8802, '01A123BC', 'allow', 'allowed', 'permanent_vehicle_allowed', 'exit', 1, 1, 21),
  mkEvent(8803, '30B777CD', 'manual_review', 'pending_review', 'manual_review_required', 'entry', 1, 1, 34),
  mkEvent(8804, '85C456EF', 'deny', 'denied', 'vehicle_not_found', 'entry', 1, 2, 47),
  mkEvent(8805, '10D908GH', 'allow', 'allowed', 'guest_vehicle_allowed', 'entry', 1, 1, 58),
  mkEvent(8806, '50E222JK', 'deny', 'denied', 'access_expired', 'entry', 2, 3, 72),
  mkEvent(8807, '90F345LM', 'allow', 'allowed', 'permanent_vehicle_allowed', 'exit', 2, 3, 95),
  mkEvent(8808, '40G678NP', 'allow', 'allowed', 'guest_vehicle_allowed', 'entry', 1, 1, 121),
  mkEvent(8809, '70H012QR', 'deny', 'denied', 'vehicle_not_found', 'entry', 1, 2, 140),
  mkEvent(8810, '01A123BC', 'allow', 'allowed', 'permanent_vehicle_allowed', 'entry', 1, 1, 168),
]

function mkEvent(
  id: number,
  plate: string,
  decision: string,
  status: string,
  reason: string,
  direction: string,
  zone: number,
  gate: number,
  mins: number,
): AccessEventRow {
  return {
    id,
    event_id: `evt-${id}`,
    controller_id: 1,
    zone_id: zone,
    gate_id: gate,
    direction,
    plate_number_normalized: plate,
    captured_at: minAgo(mins),
    occurred_at: minAgo(mins),
    source: 'anpr',
    decision,
    status,
    reason,
    decision_id: 5000 + id,
    resolved_by_user_id: decision === 'allow' ? null : null,
    has_command: decision === 'allow',
  }
}

// ── (C) База доступа — Автомобили ────────────────────────────────────────────
export const vehicles: VehicleRow[] = [
  {
    id: 301,
    plate_number_original: '01A123BC',
    plate_number_normalized: '01A123BC',
    plate_country: 'UZ',
    plate_type: 'private',
    brand: 'Chevrolet',
    model: 'Cobalt',
    color: 'белый',
    vehicle_class: 'легковой',
    status: 'active',
    blocked_reason: null,
    blocked_by_user_id: null,
    blocked_at: null,
    apartments: [
      { apartment_id: 12, relation_type: 'owner', status: 'active', valid_from: null, valid_until: null, approved_by_user_id: 7, approved_at: minAgo(40000) },
    ],
  },
  {
    id: 302,
    plate_number_original: '30B777CD',
    plate_number_normalized: '30B777CD',
    plate_country: 'UZ',
    plate_type: 'private',
    brand: 'Lada',
    model: 'Vesta',
    color: 'серебристый',
    vehicle_class: 'легковой',
    status: 'active',
    blocked_reason: null,
    blocked_by_user_id: null,
    blocked_at: null,
    apartments: [
      { apartment_id: 45, relation_type: 'tenant', status: 'active', valid_from: null, valid_until: null, approved_by_user_id: 7, approved_at: minAgo(20000) },
    ],
  },
  {
    id: 303,
    plate_number_original: '85C456EF',
    plate_number_normalized: '85C456EF',
    plate_country: 'UZ',
    plate_type: 'private',
    brand: 'Kia',
    model: 'K5',
    color: 'чёрный',
    vehicle_class: 'легковой',
    status: 'blocked',
    blocked_reason: 'Долг по парковке',
    blocked_by_user_id: 7,
    blocked_at: minAgo(1500),
    apartments: [
      { apartment_id: 78, relation_type: 'owner', status: 'active', valid_from: null, valid_until: null, approved_by_user_id: 7, approved_at: minAgo(60000) },
    ],
  },
  {
    id: 304,
    plate_number_original: '90F345LM',
    plate_number_normalized: '90F345LM',
    plate_country: 'UZ',
    plate_type: 'private',
    brand: 'Hyundai',
    model: 'Sonata',
    color: 'синий',
    vehicle_class: 'легковой',
    status: 'active',
    blocked_reason: null,
    blocked_by_user_id: null,
    blocked_at: null,
    apartments: [
      { apartment_id: 23, relation_type: 'owner', status: 'active', valid_from: null, valid_until: null, approved_by_user_id: 7, approved_at: minAgo(10000) },
      { apartment_id: 24, relation_type: 'family', status: 'active', valid_from: null, valid_until: null, approved_by_user_id: 7, approved_at: minAgo(9000) },
    ],
  },
]

// ── (C) База доступа — Пропуска ──────────────────────────────────────────────
export const passes: PassRow[] = [
  {
    id: 701,
    pass_type: 'taxi',
    apartment_id: 12,
    created_by_user_id: 12,
    zone_id: 1,
    plate_number_original: '10D908GH',
    plate_number_normalized: '10D908GH',
    valid_from: minAgo(180),
    valid_until: minAgo(-120),
    max_entries: 2,
    used_entries: 1,
    status: 'active',
    source: 'resident',
    created_at: minAgo(200),
  },
  {
    id: 702,
    pass_type: 'guest',
    apartment_id: 45,
    created_by_user_id: 45,
    zone_id: 1,
    plate_number_original: '40G678NP',
    plate_number_normalized: '40G678NP',
    valid_from: minAgo(2880),
    valid_until: minAgo(1440),
    max_entries: 5,
    used_entries: 5,
    status: 'expired',
    source: 'resident',
    created_at: minAgo(2900),
  },
  {
    id: 703,
    pass_type: 'taxi',
    apartment_id: 78,
    created_by_user_id: 78,
    zone_id: 1,
    plate_number_original: '70H012QR',
    plate_number_normalized: '70H012QR',
    valid_from: minAgo(600),
    valid_until: minAgo(-60),
    max_entries: 1,
    used_entries: 0,
    status: 'revoked',
    source: 'resident',
    created_at: minAgo(620),
  },
]

// ── (C) База доступа — Заявки жителей ────────────────────────────────────────
export const requests: AccessRequestRow[] = [
  {
    id: 501,
    apartment_id: 23,
    created_by_user_id: 23,
    vehicle_id: null,
    plate_number_original: '50E222JK',
    plate_number_normalized: '50E222JK',
    relation_type: 'owner',
    status: 'pending',
    reviewed_by_user_id: null,
    reviewed_at: null,
    review_comment: null,
    created_at: minAgo(90),
  },
  {
    id: 502,
    apartment_id: 12,
    created_by_user_id: 12,
    vehicle_id: 301,
    plate_number_original: '01A123BC',
    plate_number_normalized: '01A123BC',
    relation_type: 'owner',
    status: 'approved',
    reviewed_by_user_id: 7,
    reviewed_at: minAgo(2000),
    review_comment: 'Документы подтверждены',
    created_at: minAgo(2600),
  },
  {
    id: 503,
    apartment_id: 78,
    created_by_user_id: 78,
    vehicle_id: null,
    plate_number_original: '85C456EF',
    plate_number_normalized: '85C456EF',
    relation_type: 'tenant',
    status: 'rejected',
    reviewed_by_user_id: 7,
    reviewed_at: minAgo(1700),
    review_comment: 'Нет договора аренды',
    created_at: minAgo(2400),
  },
]

// ── (E) Оборудование — Зоны ──────────────────────────────────────────────────
export const zones: ZoneRow[] = [
  {
    id: 1,
    code: 'Z-MAIN',
    name: 'Главный двор',
    description: 'Центральный въезд комплекса',
    offline_mode: 'cached_permanent_only',
    max_permanent_per_apartment: 2,
    parking_type: 'assigned',
    capacity: null,
    max_permanent_vehicles_per_apartment: 2,
    is_active: true,
    yard_ids: [1, 2],
  },
  {
    id: 2,
    code: 'Z-PARK',
    name: 'Подземный паркинг',
    description: 'Гостевой и резидентский паркинг',
    offline_mode: 'fail_closed',
    max_permanent_per_apartment: 1,
    parking_type: 'shared',
    capacity: 80,
    max_permanent_vehicles_per_apartment: 1,
    is_active: true,
    yard_ids: [3],
  },
  {
    id: 3,
    code: 'Z-SERV',
    name: 'Служебная зона',
    description: null,
    offline_mode: 'fail_closed',
    max_permanent_per_apartment: null,
    parking_type: 'assigned',
    capacity: null,
    max_permanent_vehicles_per_apartment: null,
    is_active: false,
    yard_ids: [],
  },
]

// ── (E) Парковка — Места (parking_spots) ─────────────────────────────────────
export const spots: SpotRow[] = [
  { id: 1, zone_id: 1, code: 'A-01', status: 'active' },
  { id: 2, zone_id: 1, code: 'A-02', status: 'active' },
  { id: 3, zone_id: 1, code: 'A-03', status: 'inactive' },
  { id: 4, zone_id: 2, code: 'P-101', status: 'active' },
  { id: 5, zone_id: 2, code: 'P-102', status: 'archived' },
]

// ── (E) Парковка — Закрепления (spot_assignments) ────────────────────────────
export const assignments: AssignmentRow[] = [
  {
    id: 1,
    spot_id: 1,
    apartment_id: 12,
    ownership_type: 'owned',
    valid_from: minAgo(60000),
    valid_until: null,
    status: 'active',
    approved_by_user_id: 7,
    approved_at: minAgo(60000),
  },
  {
    id: 2,
    spot_id: 4,
    apartment_id: 45,
    ownership_type: 'rented',
    valid_from: minAgo(20000),
    valid_until: minAgo(-43200),
    status: 'active',
    approved_by_user_id: 7,
    approved_at: minAgo(20000),
  },
  {
    id: 3,
    spot_id: 2,
    apartment_id: 78,
    ownership_type: 'rented',
    valid_from: minAgo(90000),
    valid_until: minAgo(4320),
    status: 'expired',
    approved_by_user_id: 7,
    approved_at: minAgo(90000),
  },
  {
    id: 4,
    spot_id: 3,
    apartment_id: 23,
    ownership_type: 'owned',
    valid_from: minAgo(120000),
    valid_until: null,
    status: 'revoked',
    approved_by_user_id: 7,
    approved_at: minAgo(120000),
  },
]

// ── (E) Оборудование — Въезды ────────────────────────────────────────────────
export const gates: GateRow[] = [
  { id: 1, code: 'G-MAIN-IN', zone_id: 1, direction: 'entry', name: 'Главный въезд', is_active: true },
  { id: 2, code: 'G-MAIN-OUT', zone_id: 1, direction: 'exit', name: 'Главный выезд', is_active: true },
  { id: 3, code: 'G-PARK-IN', zone_id: 2, direction: 'entry', name: 'Въезд в паркинг', is_active: true },
  { id: 4, code: 'G-SERV-IN', zone_id: 3, direction: 'entry', name: 'Служебный въезд', is_active: false },
]

// ── (E) Оборудование — Камеры ────────────────────────────────────────────────
export const cameras: CameraRow[] = [
  { id: 1, code: 'CAM-01', gate_id: 1, direction: 'entry', name: 'ANPR главный въезд', vendor: 'Hikvision', model: 'iDS-2CD7A46', attributes: { fps: 25, resolution: '1920x1080' }, is_active: true },
  { id: 2, code: 'CAM-02', gate_id: 2, direction: 'exit', name: 'ANPR главный выезд', vendor: 'Hikvision', model: 'iDS-2CD7A46', attributes: null, is_active: true },
  { id: 3, code: 'CAM-03', gate_id: 3, direction: 'entry', name: 'ANPR паркинг', vendor: 'Dahua', model: 'ITC413', attributes: null, is_active: true },
]

// ── (E) Оборудование — Шлагбаумы ─────────────────────────────────────────────
export const barriers: BarrierRow[] = [
  { id: 1, code: 'BAR-01', gate_id: 1, name: 'Шлагбаум главный въезд', relay_type: 'NO', relay_channel: 1, config: { pulse_ms: 500, auto_close_s: 8 }, is_active: true },
  { id: 2, code: 'BAR-02', gate_id: 2, name: 'Шлагбаум главный выезд', relay_type: 'NO', relay_channel: 2, config: null, is_active: true },
  { id: 3, code: 'BAR-03', gate_id: 3, name: 'Шлагбаум паркинг', relay_type: 'NC', relay_channel: 1, config: null, is_active: true },
]

// ── (E) Оборудование — Контроллеры ───────────────────────────────────────────
export const controllers: ControllerRow[] = [
  {
    id: 1,
    controller_uid: 'ctrl-main-01',
    name: 'Контроллер главного въезда',
    zone_id: 1,
    gate_id: 1,
    offline_mode: 'cached_permanent_only',
    ip_allowlist: ['10.0.10.21'],
    pinned_public_key_id: 'pk-001',
    status: 'online',
    is_active: true,
  },
  {
    id: 2,
    controller_uid: 'ctrl-park-01',
    name: 'Контроллер паркинга',
    zone_id: 2,
    gate_id: 3,
    offline_mode: 'fail_closed',
    ip_allowlist: ['10.0.10.22'],
    pinned_public_key_id: 'pk-002',
    status: 'online',
    is_active: true,
  },
  {
    id: 3,
    controller_uid: 'ctrl-serv-01',
    name: 'Контроллер служебной зоны',
    zone_id: 3,
    gate_id: 4,
    offline_mode: 'fail_closed',
    ip_allowlist: null,
    pinned_public_key_id: null,
    status: 'offline',
    is_active: false,
  },
]

// ── (E) Демо-ключ контроллера (§11: синтетический, показывается один раз) ─────
export const demoApiKey = 'ak_test_DEMO000000000000'

// ── (F) Резидентский TWA (Мини-апп) — синтетика для мобильных под-видов ───────
// Формы — подмножество src/twa/pages/access/types.ts (рендерим тонкими копиями
// в TwaPreviews, без сети/twaClient). Номера/код вымышленные (§11).

export interface TwaVehicleMock {
  id: number
  plate_number_original: string
  brand: string | null
  model: string | null
  color: string | null
  status: string // active | blocked | inactive
}

export interface TwaRequestMock {
  id: number
  plate: string
  status: string // pending | approved | rejected
  created_at: string
  review_comment: string | null
}

export interface TwaPassMock {
  id: number
  pass_type: string // taxi | guest | delivery
  plate: string | null
  valid_until: string
  used_entries: number
  max_entries: number
  status: string // active | revoked | expired | used
}

// Авто жителя (вкладка «Авто»).
export const twaVehicles: TwaVehicleMock[] = [
  { id: 1, plate_number_original: '01A123BC', brand: 'Chevrolet', model: 'Cobalt', color: 'белый', status: 'active' },
  { id: 2, plate_number_original: '30B777CD', brand: 'Lada', model: 'Vesta', color: 'серебристый', status: 'active' },
  { id: 3, plate_number_original: '85C456EF', brand: 'Kia', model: 'K5', color: 'чёрный', status: 'blocked' },
]

// Заявки на постоянное авто жителя (блок «Мои заявки»).
export const twaVehicleRequests: TwaRequestMock[] = [
  { id: 51, plate: '50E222JK', status: 'pending', created_at: minAgo(90), review_comment: null },
  { id: 52, plate: '01A123BC', status: 'approved', created_at: minAgo(2600), review_comment: 'Документы подтверждены' },
  { id: 53, plate: '85C456EF', status: 'rejected', created_at: minAgo(2400), review_comment: 'Нет договора аренды' },
]

// Пропуска жителя (вкладка «Пропуска»).
export const twaPasses: TwaPassMock[] = [
  { id: 71, pass_type: 'taxi', plate: '10D908GH', valid_until: minAgo(-120), used_entries: 1, max_entries: 2, status: 'active' },
  { id: 72, pass_type: 'guest', plate: null, valid_until: minAgo(-30), used_entries: 0, max_entries: 1, status: 'active' },
  { id: 73, pass_type: 'delivery', plate: '40G678NP', valid_until: minAgo(1440), used_entries: 5, max_entries: 5, status: 'expired' },
]

// Одноразовый гостевой код (§9.3): 8 цифр, plaintext, показывается один раз.
export const twaGuestCode = '48205173'

// ── (G) Охрана — результат проверки гостевого кода (RedeemCodeResponse) ───────
export const redeemResult: RedeemCodeResponse = {
  apartment_id: 45,
  pass_type: 'guest',
  valid_until: minAgo(-30),
  command: { command_id: 'cmd-redeem-7720', barrier_id: 1 },
}

// ── (E) Демо-результат теста точки въезда (decision=allow + команда создана) ──
export const testResult: TestEventResponse = {
  decision: 'allow',
  status: 'allowed',
  reason: 'permanent_vehicle_allowed',
  decision_id: 7701,
  event_id: 'evt-diag-7701',
  zone_id: 1,
  gate_id: 1,
  barrier_id: 1,
  command: { command_id: 'cmd-diag-001', barrier_id: 1 },
}
