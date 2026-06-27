import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { AccessEventRow } from '../../types/access'
import { DecisionBadge } from './AccessBadges'
import { formatDateTime } from '../../utils/accessFormat'
import EmptyState from '../shared/EmptyState'

/**
 * Таблица истории событий доступа (общая для экрана охранника и менеджера).
 * Полный номер показывается уполномоченным ролям (§11), в отличие от
 * маскированного номера в live-ленте.
 */

interface Props {
  events: AccessEventRow[]
  onRowClick?: (event: AccessEventRow) => void
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export default function AccessEventsTable({ events, onRowClick }: Props) {
  const { t } = useTranslation()

  if (events.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🚗" title={t('accessControl.history.empty')} />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            <HeaderCell>{t('accessControl.columns.time')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.decision')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.status')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.reason')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.plate')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.direction')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.location')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.source')}</HeaderCell>
          </tr>
        </thead>
        <tbody>
          {events.map((event, idx) => {
            const isLast = idx === events.length - 1
            const decisionLabel = event.decision
            const reasonLabel = event.reason
              ? t(`accessControl.reason.${event.reason}`, { defaultValue: event.reason })
              : '—'
            const directionLabel = event.direction
              ? t(`accessControl.direction.${event.direction}`, { defaultValue: event.direction })
              : '—'
            const location =
              [
                event.zone_id != null ? `${t('accessControl.zone')} ${event.zone_id}` : null,
                event.gate_id != null ? `${t('accessControl.gate')} ${event.gate_id}` : null,
              ]
                .filter(Boolean)
                .join(' · ') || '—'

            return (
              <tr
                key={event.id}
                onClick={() => onRowClick?.(event)}
                className={cn(
                  'transition-colors duration-100',
                  !isLast && 'border-b border-border-default',
                  onRowClick && 'cursor-pointer hover:bg-bg-surface',
                )}
              >
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {formatDateTime(event.occurred_at ?? event.captured_at)}
                </td>
                <td className="px-3 py-2.5">
                  <DecisionBadge decision={decisionLabel} />
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {event.status
                    ? t(`accessControl.eventStatus.${event.status}`, { defaultValue: event.status })
                    : '—'}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-primary">{reasonLabel}</td>
                <td className="px-3 py-2.5 text-[13px] font-mono text-text-primary whitespace-nowrap">
                  {event.plate_number_normalized ?? '—'}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {directionLabel}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {location}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-muted whitespace-nowrap">
                  {event.source || '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
