/** Календарные даты раздела «Уборка» в виде «ГГГГ-ММ-ДД» (без времени и зон). */

export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return isoDate(new Date(year, month - 1, day + days))
}

/** Понедельник недели, в которую входит дата. */
export function mondayOf(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  const weekday = (new Date(year, month - 1, day).getDay() + 6) % 7 // 0 = понедельник
  return addDays(iso, -weekday)
}

/** Первый и последний день месяца даты. */
export function monthRange(iso: string): [string, string] {
  const [year, month] = iso.split('-').map(Number)
  return [isoDate(new Date(year, month - 1, 1)), isoDate(new Date(year, month, 0))]
}

/** «ГГГГ-ММ-ДД» → «ДД.ММ». */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${day}.${month}`
}
