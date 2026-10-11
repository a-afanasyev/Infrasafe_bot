/** Общие константы и форматтеры страницы аналитики (без React). */

export const PIE_PALETTE = [
  '#00d4aa', // brand-allow (categorical chart palette)
  '#3b82f6',
  '#8b5cf6',
  '#f59e0b',
  '#10b981',
  '#ef4444',
  '#06b6d4',
  '#14b8a6',
]

export const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'] as const

export const TH = 'px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted whitespace-nowrap'
export const TD = 'px-3 py-2 border-t border-border-default align-top'

/** Часы с одним знаком; `—` для пропуска. */
export function fmtHours(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(1)
}
