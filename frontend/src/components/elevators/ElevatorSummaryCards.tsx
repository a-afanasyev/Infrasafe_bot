import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import ElevatorStatusBadge from './ElevatorStatusBadge'
import { ELEVATOR_STATUSES, type ElevatorSummary } from '../../types/elevators'

/** Сводка реестра: всего, по статусам, флаги, долгий простой, заявки без лифта. */
interface Props {
  summary: ElevatorSummary
}

function Tile({ label, value, tone = '' }: { label: string; value: number; tone?: string }) {
  return (
    <div className="bg-bg-card border border-border-default rounded-default px-4 py-3 flex flex-col gap-1 min-w-36">
      <span className="text-[11px] uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)]">
        {label}
      </span>
      <span className={cn('text-2xl font-semibold text-text-primary', value > 0 && tone)}>{value}</span>
    </div>
  )
}

export default function ElevatorSummaryCards({ summary }: Props) {
  const { t } = useTranslation()
  const c = summary.totals
  // by_status на бэке считает только лифты со статусом; «не введён» = остаток.
  const withStatus = Object.values(c.by_status).reduce((acc, n) => acc + n, 0)
  const noneCount = Math.max(0, c.total - withStatus)
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Tile label={t('elevators.summary.total')} value={c.total} />
        <Tile label={t('elevators.summary.noContract')} value={c.no_contract} tone="text-orange-500" />
        <Tile label={t('elevators.summary.certExpired')} value={c.cert_expired} tone="text-red" />
        <Tile label={t('elevators.summary.maintenanceOverdue')} value={c.maintenance_overdue} tone="text-red" />
        <Tile label={t('elevators.summary.downtimeOverThreshold')} value={c.downtime_over_threshold} tone="text-red" />
        <Tile label={t('elevators.summary.requestsWithoutElevator')} value={summary.requests_without_elevator} tone="text-orange-500" />
      </div>
      <div className="flex flex-wrap items-center gap-3 text-[13px] text-text-secondary">
        <span className="text-text-muted">{t('elevators.summary.byStatus')}:</span>
        {ELEVATOR_STATUSES.map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <ElevatorStatusBadge status={s} />
            <span className="font-semibold text-text-primary">{c.by_status[s] ?? 0}</span>
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <ElevatorStatusBadge status={null} />
          <span className="font-semibold text-text-primary">{noneCount}</span>
        </span>
      </div>
    </div>
  )
}
