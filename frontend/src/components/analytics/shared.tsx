import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

/** Карточка-секция страницы аналитики. */
export function Panel({ title, actions, children, className }: {
  title: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('bg-bg-card border border-border-default rounded-default p-5 overflow-hidden min-w-0', className)}>
      <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
        <h2 className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  )
}

/** Ссылка на карточку заявки в канбане (deep-link `?request=`). */
export function RequestLink({ number }: { number: string }) {
  return (
    <Link
      to={`/dashboard?request=${encodeURIComponent(number)}`}
      className="font-[family-name:var(--font-mono)] text-accent hover:underline"
    >
      #{number}
    </Link>
  )
}

/** Индикатор изменения к прошлому окну: ↑12% / ↓5%; `better` — какое направление хорошее. */
export function ChangeBadge({ pct, better, title }: {
  pct: number | null
  better: 'up' | 'down'
  title: string
}) {
  if (pct === null) return <span className="text-xs text-text-muted" title={title}>—</span>
  const good = pct === 0 ? null : (pct > 0) === (better === 'up')
  const color = good === null ? 'var(--text-muted)' : good ? 'var(--emerald)' : 'var(--red)'
  const arrow = pct > 0 ? '↑' : pct < 0 ? '↓' : '→'
  return (
    <span className="text-xs font-semibold" style={{ color }} title={title}>
      {arrow} {Math.abs(pct)}%
    </span>
  )
}

export function KpiCard({ label, value, hint, change }: {
  label: string
  value: string | number
  hint?: string
  change?: ReactNode
}) {
  return (
    <div className="rounded-default bg-bg-card border border-border-default p-4 min-w-0">
      <div className="font-[family-name:var(--font-mono)] text-2xl font-bold leading-none text-text-primary">
        {value}
      </div>
      <div className="text-sm text-text-secondary mt-1.5">{label}</div>
      <div className="mt-1.5 flex items-center gap-2 flex-wrap">
        {change}
        {hint && <span className="text-[11px] text-text-muted">{hint}</span>}
      </div>
    </div>
  )
}

export function TableShell({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto -mx-5 px-5">
      <table className="w-full border-collapse text-[13px]">{children}</table>
    </div>
  )
}
