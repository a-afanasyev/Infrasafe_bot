import type { TFunction } from 'i18next'
import { tCategory } from '../../i18n/apiMaps'
import { toDisplayTz } from '../../utils/timezone'
import type { PlannedWorkCfg, WorkingHourCfg } from '../../types/boardConfig'

// Чистые форматтеры страницы жителей: без React и без Date-зоны браузера —
// всё, что зависит от «сегодня», получает его аргументом (YYYY-MM-DD стенки
// display-зоны), поэтому тесты не зависят от зоны раннера.

export const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'] as const
const DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export type Lang = 'ru' | 'uz'

/** «08:00» → «08:00»; пустое время → ''. */
export function timeRange(from: string, to: string): string {
  if (from && to) return `${from}–${to}`
  return from || to || ''
}

/**
 * Часы работы одной строкой: подряд идущие дни с одинаковым графиком
 * сворачиваются — «Пн–Пт 09:00–18:00 · Сб 09:00–17:00 · Вс выходной».
 */
export function formatWorkingHours(hours: WorkingHourCfg[], t: TFunction): string {
  const byDay = new Map(hours.map((h) => [h.day, h]))
  const schedule = (day: string) => {
    const h = byDay.get(day)
    if (!h || h.closed) return t('home.dayOff')
    return timeRange(h.open, h.close)
  }
  const groups: { first: string; last: string; value: string }[] = []
  for (const day of DAY_ORDER) {
    const value = schedule(day)
    const prev = groups[groups.length - 1]
    if (prev && prev.value === value) {
      groups[groups.length - 1] = { ...prev, last: day }
    } else {
      groups.push({ first: day, last: day, value })
    }
  }
  return groups
    .map((g) => {
      const days = g.first === g.last
        ? t(`days.short.${g.first}`)
        : `${t(`days.short.${g.first}`)}–${t(`days.short.${g.last}`)}`
      return `${days} ${g.value}`
    })
    .join(' · ')
}

/** Работы с сегодняшней даты и позже, по дате и времени начала. */
export function upcomingWorks(works: PlannedWorkCfg[], today: string, limit: number): PlannedWorkCfg[] {
  return works
    .filter((w) => w.date >= today)
    .sort((a, b) => (a.date + a.time_from).localeCompare(b.date + b.time_from))
    .slice(0, limit)
}

/** «2026-10-15» → { day: '15', month: 'окт' } для плитки даты. */
export function workDateParts(date: string, t: TFunction): { day: string; month: string } {
  const [, mm, dd] = date.split('-')
  const monthKey = MONTH_KEYS[Number(mm) - 1]
  return { day: String(Number(dd)), month: monthKey ? t(`home.monthsShort.${monthKey}`) : '' }
}

/** «2026-10-15» + время → «15 октября · 10:00–12:00» (без времени — только дата). */
export function workDateLabel(work: PlannedWorkCfg, t: TFunction, lang: Lang): string {
  const [, mm, dd] = work.date.split('-')
  const monthKey = MONTH_KEYS[Number(mm) - 1]
  const day = lang === 'uz'
    ? `${Number(dd)}-${t(`months.${monthKey}`)}`
    : `${Number(dd)} ${t(`months.${monthKey}`)}`
  const time = timeRange(work.time_from, work.time_to)
  return time ? `${day} · ${time}` : day
}

/**
 * published_at объявления → стенка display-зоны (carrier Date) или null.
 * Редактор пишет naive «YYYY-MM-DDTHH:mm» — это УЖЕ стенка объекта (ARCH-138),
 * её нельзя прогонять через зону браузера; значение с зоной — инстант.
 */
export function announcementWall(publishedAt: string): Date | null {
  const naive = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(publishedAt)
  if (naive) {
    const [, y, mo, d, h, mi] = naive.map(Number)
    return new Date(y, mo - 1, d, h, mi)
  }
  if (Number.isNaN(new Date(publishedAt).getTime())) return null
  return toDisplayTz(publishedAt)
}

/** Стенка display-зоны (carrier Date) → «15 октября · 09:00». */
export function wallDateTimeLabel(wall: Date, t: TFunction, lang: Lang): string {
  const month = t(`months.${MONTH_KEYS[wall.getMonth()]}`)
  const day = lang === 'uz' ? `${wall.getDate()}-${month}` : `${wall.getDate()} ${month}`
  const hh = String(wall.getHours()).padStart(2, '0')
  const mm = String(wall.getMinutes()).padStart(2, '0')
  return `${day} · ${hh}:${mm}`
}

/**
 * Категории группы обращений строкой «Сантехника — 3 · Электрика — 2»:
 * по убыванию, не больше `limit` позиций — строка должна влезть в карточку.
 */
export function categoryLine(counts: Record<string, number> | undefined, t: TFunction, limit = 4): string {
  return Object.entries(counts ?? {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([category, n]) => `${category ? tCategory(category, t) : '—'} — ${n}`)
    .join(' · ')
}

/** «+998 78 333 19 71» → «tel:+998783331971». */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

/** Username бота без «@» и мусора — для ссылки t.me. */
export function botHandle(username: string): string {
  return username.replace(/^@/, '').replace(/[^A-Za-z0-9_]/g, '')
}
