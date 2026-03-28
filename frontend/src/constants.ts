// ─── Shared constants ──────────────────────────────────────────────────────
// Single source of truth for Russian API values used across the frontend.
// These arrays contain values as they appear in the API — do NOT translate them.
// For display, use apiMaps.ts helpers (tStatus, tCategory, tUrgency, etc.)

/** Request categories — synced with backend */
export const CATEGORIES = [
  'Электрика',
  'Сантехника',
  'Отопление',
  'Вентиляция',
  'Лифт',
  'Уборка',
  'Благоустройство',
  'Безопасность',
  'Интернет/ТВ',
  'Другое',
] as const

/** Request categories including "Ремонт" (used on ResidentBoardPage) */
export const CATEGORIES_WITH_REPAIR = [...CATEGORIES, 'Ремонт'] as const

/** Urgency levels — synced with backend */
export const URGENCIES = [
  'Обычная',
  'Средняя',
  'Срочная',
  'Критическая',
] as const

/** Terminal statuses — requests in these statuses cannot be moved */
export const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

/** Shift type values — English keys sent to API */
export const SHIFT_TYPES = [
  { value: 'regular' },
  { value: 'emergency' },
  { value: 'overtime' },
  { value: 'maintenance' },
] as const

/** Priority level values for shifts */
export const PRIORITIES = [
  { value: '1' },
  { value: '2' },
  { value: '3' },
  { value: '4' },
  { value: '5' },
] as const
