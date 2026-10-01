export function dash(v: unknown): React.ReactNode {
  return v === null || v === undefined || v === '' ? '—' : String(v)
}

/** Дата ISO → локальная короткая строка (или прочерк). */
export function fmtDate(v: string | null): React.ReactNode {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString()
}
