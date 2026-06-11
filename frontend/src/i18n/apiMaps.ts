/**
 * Typed mapping of Russian API values to i18n keys.
 * Russian strings appear ONLY here — components use tStatus(), tUrgency(), etc.
 */
import type { TFunction } from 'i18next'

// === Statuses (9 values) ===
// PR7: «Возвращена» — канон-статус возврата заявителем (SSOT-кластер #1).
// Менеджерский дашборд и TWA видят его напрямую; публичная витрина и InfraSafe
// получают спроецированное «Исполнено» (бэкенд project_public_status).
export const STATUS_MAP = {
  'Новая':      'status.new',
  'В работе':   'status.in_progress',
  'Закуп':      'status.purchase',
  'Уточнение':  'status.clarification',
  'Выполнена':  'status.executed',
  'Исполнено':  'status.completed',
  'Возвращена': 'status.returned',
  'Принято':    'status.approved',
  'Отменена':   'status.cancelled',
} as const

export type ApiStatus = keyof typeof STATUS_MAP

export function tStatus(apiValue: string, t: TFunction): string {
  const key = STATUS_MAP[apiValue as ApiStatus]
  if (!key) {
    console.warn(`[i18n] Unknown API status: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Urgencies (4 values) ===
// TASK 17: канон — ключи. Dual-read на окно перехода: принимаем И ключ, И
// legacy-рус (старые/cached клиенты, смешанные данные). Рус-ключи снять в Фазе 2.
export const URGENCY_MAP = {
  low:           'urgency.normal',
  medium:        'urgency.medium',
  high:          'urgency.urgent',
  critical:      'urgency.critical',
  // legacy-рус
  'Обычная':      'urgency.normal',
  'Средняя':      'urgency.medium',
  'Срочная':      'urgency.urgent',
  'Критическая':  'urgency.critical',
} as const

export type ApiUrgency = keyof typeof URGENCY_MAP

export function tUrgency(apiValue: string, t: TFunction): string {
  const key = URGENCY_MAP[apiValue as ApiUrgency]
  if (!key) {
    console.warn(`[i18n] Unknown API urgency: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Categories (11 values) ===
export const CATEGORY_MAP = {
  // Russian keys (from web/callcenter)
  'Электрика':       'category.electrical',
  'Сантехника':      'category.plumbing',
  'Отопление':       'category.heating',
  'Вентиляция':      'category.ventilation',
  'Лифт':            'category.elevator',
  'Уборка':          'category.cleaning',
  'Благоустройство': 'category.landscaping',
  'Безопасность':    'category.security',
  'Интернет/ТВ':     'category.internet_tv',
  'Ремонт':          'category.repair',
  'Другое':          'category.other',
  // English keys (from bot)
  'electricity':     'category.electrical',
  'plumbing':        'category.plumbing',
  'heating':         'category.heating',
  'ventilation':     'category.ventilation',
  'elevator':        'category.elevator',
  'cleaning':        'category.cleaning',
  'landscaping':     'category.landscaping',
  'security':        'category.security',
  'internet_tv':     'category.internet_tv',
  'repair':          'category.repair',
  'other':           'category.other',
} as const

export type ApiCategory = keyof typeof CATEGORY_MAP

export function tCategory(apiValue: string, t: TFunction): string {
  const key = CATEGORY_MAP[apiValue as ApiCategory]
  if (!key) {
    console.warn(`[i18n] Unknown API category: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Specializations (8 values — keys already in English) ===
export const SPECIALIZATION_MAP = {
  'electrician':  'specialization.electrician',
  'plumber':      'specialization.plumber',
  'heating':      'specialization.heating',
  'cleaning':     'specialization.cleaning',
  'security':     'specialization.security',
  'elevator':     'specialization.elevator',
  'landscaping':  'specialization.landscaping',
  'ventilation':  'specialization.ventilation',
  'hvac':         'specialization.hvac',
  'maintenance':  'specialization.maintenance',
  'installation': 'specialization.installation',
  'repair':       'specialization.repair',
} as const

export type ApiSpecialization = keyof typeof SPECIALIZATION_MAP

export function tSpecialization(apiValue: string, t: TFunction): string {
  const key = SPECIALIZATION_MAP[apiValue as ApiSpecialization]
  if (!key) {
    console.warn(`[i18n] Unknown API specialization: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Shift Types (4 values — English keys) ===
export const SHIFT_TYPE_MAP = {
  'regular':     'shiftType.regular',
  'emergency':   'shiftType.emergency',
  'overtime':    'shiftType.overtime',
  'maintenance': 'shiftType.maintenance',
} as const

export type ApiShiftType = keyof typeof SHIFT_TYPE_MAP

export function tShiftType(apiValue: string, t: TFunction): string {
  const key = SHIFT_TYPE_MAP[apiValue as ApiShiftType]
  if (!key) {
    console.warn(`[i18n] Unknown API shift type: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Analytics Status (7 values — English keys, different from kanban!) ===
export const ANALYTICS_STATUS_MAP = {
  'new':         'analyticsStatus.new',
  'pending':     'analyticsStatus.pending',
  'in_progress': 'analyticsStatus.in_progress',
  'assigned':    'analyticsStatus.assigned',
  'completed':   'analyticsStatus.completed',
  'cancelled':   'analyticsStatus.cancelled',
  'rejected':    'analyticsStatus.rejected',
} as const

export type ApiAnalyticsStatus = keyof typeof ANALYTICS_STATUS_MAP

export function tAnalyticsStatus(apiValue: string, t: TFunction): string {
  const key = ANALYTICS_STATUS_MAP[apiValue as ApiAnalyticsStatus]
  if (!key) {
    console.warn(`[i18n] Unknown analytics status: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Analytics Events (4 values — English keys) ===
export const ANALYTICS_EVENT_MAP = {
  'created':   'analyticsEvent.created',
  'assigned':  'analyticsEvent.assigned',
  'completed': 'analyticsEvent.completed',
  'cancelled': 'analyticsEvent.cancelled',
} as const

export type ApiAnalyticsEvent = keyof typeof ANALYTICS_EVENT_MAP

export function tAnalyticsEvent(apiValue: string, t: TFunction): string {
  const key = ANALYTICS_EVENT_MAP[apiValue as ApiAnalyticsEvent]
  if (!key) {
    console.warn(`[i18n] Unknown analytics event: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Roles (English keys) ===
export const ROLE_MAP = {
  'executor':  'role.executor',
  'manager':   'role.manager',
  'inspector': 'role.inspector',
} as const

export type ApiRole = keyof typeof ROLE_MAP

export function tRole(apiValue: string, t: TFunction): string {
  const key = ROLE_MAP[apiValue as ApiRole]
  if (!key) {
    console.warn(`[i18n] Unknown API role: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}

// === Priorities (5 values — numeric string keys) ===
export const PRIORITY_MAP = {
  '1': 'priority.1',
  '2': 'priority.2',
  '3': 'priority.3',
  '4': 'priority.4',
  '5': 'priority.5',
} as const

export function tPriority(apiValue: string | number, t: TFunction): string {
  const key = PRIORITY_MAP[String(apiValue) as keyof typeof PRIORITY_MAP]
  if (!key) {
    console.warn(`[i18n] Unknown priority: "${apiValue}"`)
    return String(apiValue)
  }
  return t(key)
}

// === Approval Status (2 values) ===
export const APPROVAL_STATUS_MAP = {
  'approved': 'approvalStatus.approved',
  'pending':  'approvalStatus.pending',
} as const

export function tApprovalStatus(apiValue: string, t: TFunction): string {
  const key = APPROVAL_STATUS_MAP[apiValue as keyof typeof APPROVAL_STATUS_MAP]
  if (!key) {
    console.warn(`[i18n] Unknown approval status: "${apiValue}"`)
    return apiValue
  }
  return t(key)
}
