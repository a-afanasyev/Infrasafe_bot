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
  'internet':        'category.internet_tv',
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

// === Specializations ===
// Первые девять — канон (constants/specializations.ts). Ниже legacy-значения:
// они ещё встречаются в архивных заявках и назначениях до миграции 010, и их
// надо чем-то рисовать — но в формах они не предлагаются.
export const SPECIALIZATION_MAP = {
  'electrician':  'specialization.electrician',
  'plumber':      'specialization.plumber',
  'heating':      'specialization.heating',
  'ventilation':  'specialization.ventilation',
  'elevator':     'specialization.elevator',
  'cleaning':     'specialization.cleaning',
  'security':     'specialization.security',
  'landscaping':  'specialization.landscaping',
  'repair':       'specialization.repair',
  // legacy — только для отображения
  'hvac':         'specialization.hvac',
  'maintenance':  'specialization.maintenance',
  'installation': 'specialization.installation',
  'general':      'specialization.general',
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
