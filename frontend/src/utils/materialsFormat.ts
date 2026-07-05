/** Форматирование чисел складского учёта (qty/деньги приходят строками). */

/** Количество без хвостовых нулей: "10.500" → "10.5", "3.000" → "3". */
export function fmtQty(value: string | number): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return num.toLocaleString('ru-RU', { maximumFractionDigits: 3 })
}

/** Деньги (сум UZS): "10500.00" → "10 500,00". */
export function fmtMoney(value: string | number): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return num.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
