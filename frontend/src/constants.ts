// ─── Shared constants ──────────────────────────────────────────────────────
// Single source of truth for API values used across the frontend.
// These arrays contain values as they appear in the API — do NOT translate them.
// For display, use apiMaps.ts helpers (tStatus, tCategory, tUrgency, etc.)

/** Request categories — canonical EN keys sent to backend (FS-04). Display via tCategory(). */
export const CATEGORIES = [
  'electricity',
  'plumbing',
  'heating',
  'ventilation',
  'elevator',
  'cleaning',
  'landscaping',
  'security',
  'internet',
  'other',
] as const

/** Request categories including "repair" (used on ResidentBoardPage) */
export const CATEGORIES_WITH_REPAIR = [...CATEGORIES, 'repair'] as const

/** Urgency levels — canonical keys, synced with backend (TASK 17) */
export const URGENCIES = [
  'low',
  'medium',
  'high',
  'critical',
] as const

/** Legacy-рус → канон-ключ (dual-read окно перехода; снять в Фазе 2). */
const URGENCY_RU_TO_KEY: Record<string, string> = {
  'Обычная': 'low',
  'Средняя': 'medium',
  'Срочная': 'high',
  'Критическая': 'critical',
}

/** Normalize a stored urgency (key or legacy-russian) to its canonical key. */
export function normalizeUrgency(value: string): string {
  return URGENCY_RU_TO_KEY[value] ?? value
}

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

/** Cycle recurrence presets (N working / M off days) for shift templates */
export const CYCLE_PRESETS = [
  { on: 1, off: 3 },
  { on: 2, off: 2 },
  { on: 3, off: 3 },
  { on: 1, off: 2 },
] as const
