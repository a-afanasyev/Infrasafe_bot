import { addDays, format, parseISO } from 'date-fns'
import { formatDateTime as formatInstant, todayInDisplayTz } from './timezone'

/**
 * Форматтеры модуля «Лифты» (без JSX). Даты-инстанты (ISO с временем) — через
 * display-зону проекта (`utils/timezone`); календарные даты `YYYY-MM-DD`
 * (due_on, contract_until…) — как есть, без сдвига по зоне.
 */

/** Единый прочерк для пустых значений. */
export const DASH = '—'

/** Доля 0..1 → «97 %»; null → «—». */
export function fmtAvailability(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return `${Math.round(value * 100)} %`
}

/** Календарная дата `YYYY-MM-DD` → `dd.MM.yyyy`; пусто/битое → «—»/как есть. */
export function fmtDateOnly(value: string | null | undefined): string {
  if (!value) return DASH
  const d = parseISO(value)
  if (Number.isNaN(d.getTime())) return value
  return format(d, 'dd.MM.yyyy')
}

/** ISO-инстант → «dd MMM yyyy, HH:mm» в display-зоне; пусто/битое → «—»/как есть. */
export function fmtInstant(value: string | null | undefined): string {
  if (!value) return DASH
  if (Number.isNaN(new Date(value).getTime())) return value
  return formatInstant(value)
}

/**
 * `YYYY-MM-DD` «сегодня» в display-зоне проекта + сдвиг в днях — для окон
 * календаря. Зона браузера не участвует (ARCH-137).
 */
export function displayTodayPlusDays(days: number): string {
  return format(addDays(parseISO(todayInDisplayTz()), days), 'yyyy-MM-dd')
}

/** Только http(s)-ссылки: `javascript:`/`data:`/относительные — нет. */
export function isHttpUrl(value: string): boolean {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

/** Пустая строка → null (для опциональных текстовых полей формы). */
export function emptyToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Строка формы → целое или null (пусто/не число). */
export function toIntOrNull(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const n = Number(trimmed)
  return Number.isInteger(n) ? n : null
}

/** «30, 7, 1» → [30, 7, 1]; мусор отбрасывается. */
export function parseIntList(value: string): number[] {
  return value
    .split(/[,\s;]+/)
    .filter((s) => s !== '')
    .map((s) => Number(s))
    .filter((n) => Number.isInteger(n) && n >= 0)
}
