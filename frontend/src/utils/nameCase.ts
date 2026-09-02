/**
 * Отображение ФИО в дашборде менеджера: предпочтение «С заглавной» (title,
 * дефолт) или «ВСЕ ЗАГЛАВНЫЕ» (caps). Единственный канон форматирования
 * имён людей для рендера — все точки идут через `usePersonName()`.
 *
 * Форматтер не знает fallback'ов (`#12`, «Без имени»): пустой ввод → '',
 * вызывающий подставляет `|| fallback`, чтобы i18n-строки не капсились.
 */
export type NameCase = 'title' | 'caps'

export const NAME_CASE_DEFAULT: NameCase = 'title'

export function isNameCase(v: unknown): v is NameCase {
  return v === 'title' || v === 'caps'
}

const NON_LETTER_TOKEN = /^[^\p{L}]*$/u

/**
 * КАПС → «Вид Имени». Трогаем только слова, записанные целиком капсом
 * (нормальный регистр — уже осознанный ввод менеджера: `МакКей`, `O'g'li`);
 * капитализация после дефиса — да, после апострофа — НЕТ: в узбекской
 * латинице o'/g' — единые буквы (O'g'li, Qo'chqor), «O'G'Li» — ошибка.
 */
function titleWord(w: string): string {
  const isAllCaps = w.length > 1 && w === w.toUpperCase() && !NON_LETTER_TOKEN.test(w)
  if (!isAllCaps) return w
  return w
    .toLowerCase()
    .replace(/(^|-)(\p{L})/gu, (_, sep: string, ch: string) => sep + ch.toUpperCase())
}

function tokens(raw: string | null | undefined): string[] {
  return (raw ?? '').split(/\s+/).filter(Boolean)
}

export function formatPersonName(raw: string | null | undefined, mode: NameCase): string {
  const words = tokens(raw)
  if (mode === 'caps') return words.join(' ').toUpperCase()
  return words.map(titleWord).join(' ')
}

/** first + last через пробел; пустые части отброшены, '' если обе пусты. */
export function joinPersonName(first?: string | null, last?: string | null): string {
  return [...tokens(first), ...tokens(last)].join(' ')
}
