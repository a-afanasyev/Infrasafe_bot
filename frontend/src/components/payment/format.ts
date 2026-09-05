import { formatDate } from '../../i18n/formatters'

/**
 * Дата состояния (`as_of`) и дата платежа (`paid_at`) приходят как `YYYY-MM-DD`
 * и не несут времени: форматируем в UTC, иначе в браузере западнее UTC
 * календарный день уезжает на сутки назад.
 */
export function formatBusinessDate(value?: string | null): string {
  return value ? formatDate(value, { dateStyle: 'short', timeZone: 'UTC' }) : '—'
}

/** Момент из журнала действий — в зоне пользователя, как остальной дашборд. */
export function formatInstant(value?: string | null): string {
  return value ? formatDate(value, { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

/** Валюта приходит из сервиса; хардкодить «UZS» в вёрстке нельзя. */
export function formatMoney(value?: string | null, currency?: string | null): string {
  if (value == null) return '—'
  return currency ? `${value} ${currency}` : value
}
