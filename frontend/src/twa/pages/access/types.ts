/**
 * Контроль доступа жителя (applicant) — типы DTO и общие хелперы.
 *
 * Контракт бэкенда: APPLICANT-API контроля доступа `/api/v1/access/*`
 * (access_control/api/resident.py). Списки приходят в едином конверте
 * `{ items, total, limit, offset }`. Аутентификация — общий twaClient
 * (TWA-токен в Authorization), в проде same-origin через edge.
 */

/** Конверт постраничного списка (общий для всех access-эндпоинтов жителя). */
export interface AccessPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** Связь авто с квартирой (часть VehicleRow). */
export interface ApartmentLink {
  apartment_id: number
  relation_type: string
  status: string
  valid_from: string | null
  valid_until: string | null
}

/** Авто жителя (GET /my/vehicles). */
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

/** Пропуск (GET /my/passes, POST /passes). */
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

/**
 * Ответ POST /passes — созданный пропуск + одноразовый код (§9.3).
 * `one_time_code` приходит ТОЛЬКО для guest-пропуска без номера (8 цифр,
 * plaintext, показывается жителю РОВНО ОДИН РАЗ). Для taxi/delivery/guest-с-
 * номером поле = null.
 */
export interface PassCreateResponse extends PassRow {
  one_time_code?: string | null
}

/** Заявка на постоянный авто (GET /my/requests, POST /requests). */
export interface RequestRow {
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

/** Событие проезда (GET /my/events). */
export interface AccessEventRow {
  id: number
  event_id: string
  occurred_at: string
  direction: string
  gate_id: number | null
  zone_id: number | null
  apartment_id: number | null
  plate_number_normalized: string | null
  decision: string | null
  reason: string | null
}

/** Квартира жителя (GET /api/v2/profile/apartments). */
export interface ApartmentOption {
  apartment_id: number
  full_address: string
}

/** Базовый путь applicant-API контроля доступа (same-origin в проде). */
export const ACCESS_BASE = '/api/v1/access'

/** Допустимые типы пропуска для жителя (§6.4). */
export const RESIDENT_PASS_TYPES = ['taxi', 'guest', 'delivery'] as const
export type ResidentPassType = (typeof RESIDENT_PASS_TYPES)[number]

/** Типы связи авто с квартирой. */
export const RELATION_TYPES = ['owner', 'tenant', 'family', 'service'] as const
export type RelationType = (typeof RELATION_TYPES)[number]

/** Tailwind-классы бейджа по нормализованному статусу (как StatusBadge в TWA). */
const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  blocked: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  revoked: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  expired: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  used: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  inactive: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
}

export function statusBadgeClass(status: string): string {
  return STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'
}

/** Краткая дата/время DD.MM HH:mm (ru) для списков. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
