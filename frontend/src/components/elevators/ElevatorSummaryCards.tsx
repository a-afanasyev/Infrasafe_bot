import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import ElevatorStatusBadge from './ElevatorStatusBadge'
import { BodyRow, HeadRow, TableShell, Td, Th } from './TableCells'
import { ELEVATOR_STATUSES, type ElevatorSummary } from '../../types/elevators'

/**
 * Сводка реестра: всего, флаги, долгий простой, заявки без лифта; строка по
 * статусам; компактная таблица по дворам (двор → всего / не работает / в ремонте).
 */
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
        <Tile label={t('elevators.summary.noContract')} value={c.no_contract} tone="text-orange" />
        <Tile label={t('elevators.summary.certExpired')} value={c.cert_expired} tone="text-red" />
        <Tile label={t('elevators.summary.maintenanceOverdue')} value={c.maintenance_overdue} tone="text-red" />
        <Tile label={t('elevators.summary.downtimeOverThreshold')} value={c.downtime_over_threshold} tone="text-red" />
        <Tile label={t('elevators.summary.requestsWithoutElevator')} value={summary.requests_without_elevator} tone="text-orange" />
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
      {summary.yards.length > 1 && (
        <details className="text-[13px]">
          <summary className="cursor-pointer text-text-muted select-none">{t('elevators.summary.byYard')}</summary>
          <div className="mt-2 max-w-xl">
            <TableShell>
              <thead>
                <HeadRow>
                  <Th>{t('elevators.filters.yard')}</Th>
                  <Th>{t('elevators.summary.total')}</Th>
                  <Th>{t('elevators.status.not_working')}</Th>
                  <Th>{t('elevators.status.under_repair')}</Th>
                </HeadRow>
              </thead>
              <tbody>
                {summary.yards.map((y) => (
                  <BodyRow key={y.yard_id}>
                    <Td>{y.yard_name}</Td>
                    <Td>{y.counters.total}</Td>
                    <Td className={y.counters.by_status.not_working ? 'text-red font-semibold' : ''}>
                      {y.counters.by_status.not_working ?? 0}
                    </Td>
                    <Td className={y.counters.by_status.under_repair ? 'text-orange font-semibold' : ''}>
                      {y.counters.by_status.under_repair ?? 0}
                    </Td>
                  </BodyRow>
                ))}
              </tbody>
            </TableShell>
          </div>
        </details>
      )}
    </div>
  )
}
