/**
 * Период аналитики: пресеты → календарные бизнес-даты, авто-срез, подписи оси.
 *
 * Модуль чистый: «сегодня» приходит параметром (`todayInDisplayTz()` у
 * вызывающего), даты — строки `YYYY-MM-DD` в бизнес-зоне. Арифметика идёт в
 * UTC-полночах, поэтому зона браузера в расчёт не попадает. Пороги авто-среза
 * зеркалят бэкенд (`services/request_analytics/period.py`).
 */

export type Granularity = 'day' | 'month' | 'year'
export type PresetId = 'today' | 'last7' | 'thisMonth' | 'lastMonth' | 'thisYear' | 'lastYear' | 'custom'

export const PRESETS: readonly Exclude<PresetId, 'custom'>[] = [
  'today', 'last7', 'thisMonth', 'lastMonth', 'thisYear', 'lastYear',
]

export interface DateRange {
  from: string
  to: string
}

export const DAY_MAX_DAYS = 62
export const MONTH_MAX_DAYS = 731
export const MAX_RANGE_DAYS = 5 * 366

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const DAY_MS = 86_400_000

function parse(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`)
}

function format(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function addDays(iso: string, days: number): string {
  return format(new Date(parse(iso).getTime() + days * DAY_MS))
}

export function presetRange(preset: Exclude<PresetId, 'custom'>, today: string): DateRange {
  const d = parse(today)
  const y = d.getUTCFullYear()
  const m = d.getUTCMonth()
  switch (preset) {
    case 'today':
      return { from: today, to: today }
    case 'last7':
      return { from: addDays(today, -6), to: today }
    case 'thisMonth':
      return { from: format(new Date(Date.UTC(y, m, 1))), to: today }
    case 'lastMonth':
      return {
        from: format(new Date(Date.UTC(y, m - 1, 1))),
        to: format(new Date(Date.UTC(y, m, 0))),
      }
    case 'thisYear':
      return { from: `${y}-01-01`, to: today }
    case 'lastYear':
      return { from: `${y - 1}-01-01`, to: `${y - 1}-12-31` }
  }
}

export function daysInRange(range: DateRange): number {
  return Math.round((parse(range.to).getTime() - parse(range.from).getTime()) / DAY_MS) + 1
}

export function isValidRange(range: DateRange): boolean {
  if (!ISO_DATE.test(range.from) || !ISO_DATE.test(range.to)) return false
  if (Number.isNaN(parse(range.from).getTime()) || Number.isNaN(parse(range.to).getTime())) return false
  const days = daysInRange(range)
  return days >= 1 && days <= MAX_RANGE_DAYS
}

export function autoGranularity(range: DateRange): Granularity {
  const days = daysInRange(range)
  if (days <= DAY_MAX_DAYS) return 'day'
  if (days <= MONTH_MAX_DAYS) return 'month'
  return 'year'
}

/** Подпись бакета оси: `12.10`, `окт 2026`, `2026`. `monthNames` — 12 коротких имён. */
export function formatBucket(bucket: string, granularity: Granularity, monthNames: readonly string[]): string {
  if (granularity === 'day') {
    const [, mm, dd] = bucket.split('-')
    return `${dd}.${mm}`
  }
  if (granularity === 'month') {
    const [yyyy, mm] = bucket.split('-')
    return `${monthNames[Number(mm) - 1] ?? mm} ${yyyy}`
  }
  return bucket
}

/** Подпись периода: `01.10.2026 — 31.10.2026` (один день — одна дата). */
export function formatRange(range: DateRange): string {
  const human = (iso: string) => iso.split('-').reverse().join('.')
  return range.from === range.to ? human(range.from) : `${human(range.from)} — ${human(range.to)}`
}

/** Изменение к прошлому окну в процентах; null — сравнивать не с чем. */
export function pctChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || previous === 0) return null
  return Math.round(((current - previous) / previous) * 100)
}
