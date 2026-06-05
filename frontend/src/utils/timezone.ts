import { format } from 'date-fns-tz'
import { toZonedTime } from 'date-fns-tz'
import { ru } from 'date-fns/locale'

const TZ = 'Asia/Tashkent'
const LOCALE_OPTS = { locale: ru, timeZone: TZ }

export function toTashkent(isoString: string): Date {
  return toZonedTime(new Date(isoString), TZ)
}

export function formatTime(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'HH:mm', { timeZone: TZ })
}

/**
 * Whole-day offset between two instants in the display timezone.
 * 0 = same calendar day, 1 = end is the next day, etc. Used to mark shifts
 * that cross midnight (e.g. a 24h shift) so the UI shows "08:00 +1".
 */
export function dayOffset(startIso: string, endIso: string): number {
  const s = toZonedTime(new Date(startIso), TZ)
  const e = toZonedTime(new Date(endIso), TZ)
  const sMid = new Date(s.getFullYear(), s.getMonth(), s.getDate()).getTime()
  const eMid = new Date(e.getFullYear(), e.getMonth(), e.getDate()).getTime()
  // Both midnights are built in the runner's local tz, so any runner-tz bias
  // cancels in the subtraction. Math.round (not floor) absorbs the ±1h a DST
  // boundary could introduce; Tashkent is UTC+5 with no DST, so it's exact.
  return Math.round((eMid - sMid) / 86_400_000)
}

export function formatDateTime(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'dd MMM yyyy, HH:mm', LOCALE_OPTS)
}

export function formatDate(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'dd.MM.yyyy', { timeZone: TZ })
}
