import i18n from './index'

/**
 * Format a date using the current i18n language locale.
 * Falls back to 'ru' if the locale is not supported.
 */
export function formatDate(date: Date | string, options?: Intl.DateTimeFormatOptions): string {
  const lang = i18n.language
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
  return num.toLocaleString(i18n.language, options)
}
