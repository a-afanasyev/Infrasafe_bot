/**
 * Форматтеры домена контроля доступа (без JSX — чтобы не ломать fast-refresh
 * правилом «только компоненты в .tsx»).
 */

// Дата-время в локали браузера; null/битые значения → «—».
export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}
