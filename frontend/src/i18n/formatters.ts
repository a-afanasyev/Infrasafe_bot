import i18n, { toBcp47 } from './index'

/**
 * Format a date using the current i18n language locale.
 * Falls back to 'ru' if the locale is not supported.
 */
export function formatDate(date: Date | string, options?: Intl.DateTimeFormatOptions): string {
  const lang = toBcp47(i18n.language)
  try {
    return new Date(date).toLocaleString(lang, options)
  } catch {
    return new Date(date).toLocaleString('ru', options)
  }
}

/**
 * Format a number using the current i18n language locale.
 */
export function formatNumber(num: number, options?: Intl.NumberFormatOptions): string {
  return num.toLocaleString(toBcp47(i18n.language), options)
}
