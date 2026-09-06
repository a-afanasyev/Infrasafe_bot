import { formatDate, formatNumber } from '../../i18n/formatters'

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

export type BalanceTone = 'debt' | 'prepayment' | 'zero'

/**
 * Ячейка баланса в списке: долг со знаком «−», предоплата со знаком «+».
 *
 * Суммы приходят десятичными СТРОКАМИ намеренно — так не теряются копейки.
 * Здесь конвертация в число допустима: она нужна только для разделителей
 * разрядов, а суммы этого масштаба лежат далеко внутри точности double.
 * Сравнение с нулём — явное: `"0.00"` — истинная строка, и проверка на
 * truthiness показала бы подтверждённый ноль как долг.
 */
export function formatBalanceCell(
  snapshot: { debt?: string | null; prepayment?: string | null } | null | undefined,
): { text: string; tone: BalanceTone } | null {
  if (!snapshot) return null
  const debt = Number(snapshot.debt ?? 0)
  const prepayment = Number(snapshot.prepayment ?? 0)
  if (Number.isFinite(debt) && debt > 0) return { text: `−${formatAmount(debt)}`, tone: 'debt' }
  if (Number.isFinite(prepayment) && prepayment > 0) return { text: `+${formatAmount(prepayment)}`, tone: 'prepayment' }
  return { text: formatAmount(0), tone: 'zero' }
}

function formatAmount(value: number): string {
  return formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
