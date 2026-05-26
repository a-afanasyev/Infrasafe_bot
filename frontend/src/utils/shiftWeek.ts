/**
 * Helpers shared between WeekResourceGrid, MonthResourceGrid, and
 * useShiftSchedule's week/month range computation.
 *
 * Conventions:
 *  - Russian/Uzbek calendars treat Monday as week-start, so all `start`
 *    helpers anchor on Monday (ISO weekday).
 *  - All Date math runs in the browser's local timezone; the actual
 *    timezone-aware bucketing of shifts uses `toTashkent` from
 *    `utils/timezone.ts` at the consumer call-site.
 */

export function startOfDay(d: Date): Date {
  const c = new Date(d)
  c.setHours(0, 0, 0, 0)
  return c
}

export function addDays(d: Date, days: number): Date {
  const c = new Date(d)
  c.setDate(c.getDate() + days)
  return c
}

/** Monday-anchored start of the ISO week containing `d`. */
export function startOfWeek(d: Date): Date {
  const c = startOfDay(d)
  // JS getDay(): Sun=0..Sat=6. We want Mon=0..Sun=6 internally.
  const isoDayIndex = (c.getDay() + 6) % 7
  c.setDate(c.getDate() - isoDayIndex)
  return c
}

/** Exclusive end of week — start-of-week + 7 days, used in date_to params. */
export function endOfWeek(d: Date): Date {
  return addDays(startOfWeek(d), 7)
}

/** [Mon, Tue, …, Sun] of the week containing `d` at 00:00 local. */
export function weekDays(d: Date): Date[] {
  const start = startOfWeek(d)
  return Array.from({ length: 7 }, (_, i) => addDays(start, i))
}

export function startOfMonth(d: Date): Date {
  const c = startOfDay(d)
  c.setDate(1)
  return c
}

export function endOfMonth(d: Date): Date {
  const c = startOfDay(d)
  c.setMonth(c.getMonth() + 1, 1)
  return c
}

export function daysInMonth(d: Date): Date[] {
  const start = startOfMonth(d)
  const end = endOfMonth(d)
  const out: Date[] = []
  for (let cur = new Date(start); cur < end; cur = addDays(cur, 1)) {
    out.push(new Date(cur))
  }
  return out
}

/** ISO calendar weeks (Mon-anchored rows) that cover the month — 5 or 6 rows. */
export function monthWeekRows(d: Date): Date[][] {
  const start = startOfWeek(startOfMonth(d))
  const monthEnd = endOfMonth(d)
  const rows: Date[][] = []
  for (let cur = start; cur < monthEnd; cur = addDays(cur, 7)) {
    rows.push(Array.from({ length: 7 }, (_, i) => addDays(cur, i)))
  }
  return rows
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

export function isWeekend(d: Date): boolean {
  const dow = d.getDay() // 0=Sun, 6=Sat
  return dow === 0 || dow === 6
}

export const SHIFT_TYPE_COLORS: Record<string, string> = {
  regular: '#3b82f6',
  emergency: '#ef4444',
  overtime: '#f59e0b',
  maintenance: '#8b5cf6',
}

export function shiftTypeColor(shiftType: string | null | undefined): string {
  return SHIFT_TYPE_COLORS[shiftType ?? 'regular'] ?? SHIFT_TYPE_COLORS.regular
}

/**
 * Stable color per specialization label — used by the SpecializationSidebar
 * dot and by row tinting in MonthResourceGrid. Hashed so the same label
 * always gets the same color across renders/sessions.
 */
const SPEC_PALETTE = [
  '#00d4aa', // accent
  '#3b82f6', // blue
  '#8b5cf6', // violet
  '#f59e0b', // amber
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#10b981', // emerald
  '#a855f7', // purple
]

export function specColor(label: string): string {
  if (!label) return SPEC_PALETTE[0]
  const hash = label.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return SPEC_PALETTE[hash % SPEC_PALETTE.length]
}

/**
 * Sentinel for shifts whose `specialization_focus` is null or `[]`. Lives
 * here (not in `SpecializationSidebar`) so that `MonthResourceGrid` and
 * sidebar both depend on a utility constant — not on each other.
 */
export const UNSPECIFIED_SPEC_KEY = '__unspecified__'

/**
 * Stable per-shift executor key. We try `user_id` first because two
 * different executors may share the same display name. The shift-id
 * fallback exists only for legacy rows where neither identifier is
 * populated.
 */
export function executorKey(shift: {
  user_id: number | null
  executor_name: string | null
  id: number
}): string {
  if (shift.user_id != null) return `user_${shift.user_id}`
  if (shift.executor_name) return shift.executor_name
  return `shift_${shift.id}`
}
