import { format, fromZonedTime, toZonedTime } from 'date-fns-tz'
import { ru } from 'date-fns/locale'

// ARCH-137 B6: display timezone of the deployment ("зона объекта"), served by
// GET /api/v2/public/board-config (display_tz). The default mirrors the
// backend's DISPLAY_TZ default so a failed/old-backend fetch keeps today's
// behavior.
export const DEFAULT_DISPLAY_TZ = 'Asia/Tashkent'

// Module-level zone rather than React context threading: these formatters are
// called from dozens of non-hook call-sites. DisplayTzProvider sets the zone
// ONCE and gates the app's render until then, so every consumer renders after
// the value is final — no stale-render window, no re-render contract needed.
let displayTz = DEFAULT_DISPLAY_TZ

export function setDisplayTz(tz: string): void {
  displayTz = tz
}

export function getDisplayTz(): string {
  return displayTz
}

export function isValidTimeZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

/**
 * ISO instant → Date whose local (runner-tz) fields carry the display-zone
 * wall clock. This is the calendar-carrier convention shared with the
 * shiftWeek helpers and the shifts grids: all pure Date math on such carriers
 * is display-zone math regardless of the browser's timezone.
 *
 * Известная мина date-fns-tz (унаследована ещё от toTashkent): toZonedTime
 * собирает carrier локальными сеттерами, и если display-стенка попадает в
 * spring-forward-дыру ЗОНЫ БРАУЗЕРА (≤2 даты в год, только DST-зоны зрителя),
 * час тихо сдвигается на +1. Окна дня/недели/месяца не задеты (полночь в
 * реальные DST-дыры не попадает), ввод через fromDisplayTz(string) — тоже
 * (строковая ветка парсинга); остаточный эффект — только позиционирование
 * ночной смены 02:00–03:00 в сетках в эти даты. Осознанно не чиним.
 */
export function toDisplayTz(isoString: string): Date {
  return toZonedTime(new Date(isoString), displayTz)
}

/** Wall-clock "now" in the display zone, as a calendar-carrier Date. */
export function nowInDisplayTz(): Date {
  return toZonedTime(new Date(), displayTz)
}

/** Календарное «сегодня» в display-зоне, date-only `YYYY-MM-DD`. */
export function todayInDisplayTz(): string {
  const d = nowInDisplayTz()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/**
 * Inverse of the carrier convention: a display-zone wall clock (either a
 * carrier Date or a `YYYY-MM-DDTHH:mm` string from <input type="datetime-local">)
 * → the ISO instant it denotes. The browser's own timezone never participates.
 */
export function fromDisplayTz(wallClock: Date | string): string {
  return fromZonedTime(wallClock, displayTz).toISOString()
}

export function formatTime(isoString: string): string {
  return format(toDisplayTz(isoString), 'HH:mm', { timeZone: displayTz })
}

/**
 * Whole-day offset between two instants in the display timezone.
 * 0 = same calendar day, 1 = end is the next day, etc. Used to mark shifts
 * that cross midnight (e.g. a 24h shift) so the UI shows "08:00 +1".
 */
export function dayOffset(startIso: string, endIso: string): number {
  const s = toDisplayTz(startIso)
  const e = toDisplayTz(endIso)
  const sMid = new Date(s.getFullYear(), s.getMonth(), s.getDate()).getTime()
  const eMid = new Date(e.getFullYear(), e.getMonth(), e.getDate()).getTime()
  // Both midnights are built in the runner's local tz, so any runner-tz bias
  // cancels in the subtraction. Math.round (not floor) absorbs the ±1h a DST
  // boundary could introduce in either the runner tz or the display zone.
  return Math.round((eMid - sMid) / 86_400_000)
}

export function formatDateTime(isoString: string): string {
  return format(toDisplayTz(isoString), 'dd MMM yyyy, HH:mm', { locale: ru, timeZone: displayTz })
}

export function formatDate(isoString: string): string {
  return format(toDisplayTz(isoString), 'dd.MM.yyyy', { timeZone: displayTz })
}

/**
 * ISO instant → `YYYY-MM-DDTHH:mm` value for a <input type="datetime-local">,
 * expressed in display-zone wall clock. Paired with `fromDisplayTz` on submit,
 * so an open→save round-trip preserves the instant in any browser timezone.
 */
export function isoToDatetimeLocal(isoString: string): string {
  return format(toDisplayTz(isoString), "yyyy-MM-dd'T'HH:mm", { timeZone: displayTz })
}
