import { fromZonedTime } from 'date-fns-tz'
import type { TFunction } from 'i18next'
import type { WorkingHourCfg } from '../../types/boardConfig'

export const BOARD_STATUSES = [
  { status: 'Новая', key: 'new', color: '#2563eb', bg: '#eff3ff' },
  { status: 'В работе', key: 'in_progress', color: '#7c3aed', bg: '#f3f0ff' },
  { status: 'Закуп', key: 'purchase', color: '#a65b00', bg: '#fff7e6' },
  { status: 'Уточнение', key: 'clarification', color: '#08758a', bg: '#ecfeff' },
  { status: 'Выполнена', key: 'executed', color: '#087c59', bg: '#ecfdf5' },
  { status: 'Принято', key: 'approved', color: '#166534', bg: '#f0fdf4' },
] as const

export function boardClock(date: Date, timeZone: string, seconds = false) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone, hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}),
  }).format(date)
}

export function boardDate(date: Date, timeZone: string, t: TFunction) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone, day: 'numeric', month: 'numeric', year: 'numeric' }).formatToParts(date)
  const part = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
  return `${t(`days.full.${boardDay(date, timeZone)}`)}, ${Number(part('day'))} ${t(`months.${months[Number(part('month')) - 1]}`)} ${part('year')}`
}

export function groupBoardHours(hours: WorkingHourCfg[]) {
  const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
  const groups: { days: string[]; hours: WorkingHourCfg }[] = []
  for (const hour of hours) {
    const last = groups.at(-1)
    const consecutive = last && days.indexOf(hour.day) === days.indexOf(last.days.at(-1)!) + 1
    if (last && consecutive && last.hours.closed === hour.closed && last.hours.open === hour.open && last.hours.close === hour.close) last.days.push(hour.day)
    else groups.push({ days: [hour.day], hours: hour })
  }
  return groups
}

export function boardDay(date: Date, timeZone: string) {
  return new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short' }).format(date).toLowerCase()
}

// The editor stores datetime-local in the object's zone; zoned API dates are instants.
export function boardPublished(iso: string, timeZone: string) {
  if (!iso) return ''
  const date = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? new Date(iso) : fromZonedTime(iso, timeZone)
  if (Number.isNaN(date.getTime())) return ''
  const day = new Intl.DateTimeFormat('en-GB', { timeZone, day: '2-digit', month: '2-digit' }).format(date).replace('/', '.')
  return `${day}, ${boardClock(date, timeZone)}`
}

// Preserve every character, including long words, without clipping TV slides.
export function splitBoardText(text: string, limit: number): string[] {
  let rest = Array.from(text.replace(/\s+/g, ' ').trim())
  const pages: string[] = []
  while (rest.length > limit) {
    const space = rest.slice(0, limit + 1).lastIndexOf(' ')
    const end = space > limit / 2 ? space : limit
    pages.push(rest.slice(0, end).join('').trim())
    rest = rest.slice(end)
    if (rest[0] === ' ') rest.shift()
  }
  if (rest.length) pages.push(rest.join(''))
  return pages.length ? pages : ['']
}
