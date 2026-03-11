import { format } from 'date-fns-tz'
import { toZonedTime } from 'date-fns-tz'

const TZ = 'Asia/Tashkent'

export function toTashkent(isoString: string): Date {
  return toZonedTime(new Date(isoString), TZ)
}

export function formatTime(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'HH:mm', { timeZone: TZ })
}

export function formatDateTime(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'dd MMM yyyy, HH:mm', { timeZone: TZ })
}

export function formatDate(isoString: string): string {
  return format(toZonedTime(new Date(isoString), TZ), 'dd.MM.yyyy', { timeZone: TZ })
}
