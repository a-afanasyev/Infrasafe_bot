import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import LoadingSpinner from '../shared/LoadingSpinner'
import EmptyState from '../shared/EmptyState'
import ElevatorStatusBadge from './ElevatorStatusBadge'
import { BodyRow, HeadRow, TableShell, Td, Th } from './TableCells'
import { useElevatorEvents } from '../../hooks/useElevators'
import { fmtInstant } from '../../utils/elevatorsFormat'
import type { ElevatorStatus } from '../../types/elevators'

/** Журнал событий лифта (GET /{id}/events): время, вид, old→new, источник, актор, причина, заявка. */
export default function ElevatorEventsTab({ elevatorId }: { elevatorId: number }) {
  const { t } = useTranslation()
  const events = useElevatorEvents(elevatorId)

  if (events.isLoading) return <LoadingSpinner />
  if (events.isError) return <p className="text-[13px] text-red">{t('common.error')}</p>
  const rows = events.data ?? []
  if (rows.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="📜" title={t('elevators.events.empty')} />
      </div>
    )
  }

  return (
    <TableShell>
      <thead>
        <HeadRow>
          <Th>{t('elevators.events.time')}</Th>
          <Th>{t('elevators.events.kind')}</Th>
          <Th>{t('elevators.events.transition')}</Th>
          <Th>{t('elevators.events.source')}</Th>
          <Th>{t('elevators.events.actor')}</Th>
          <Th>{t('elevators.events.reason')}</Th>
          <Th>{t('elevators.events.request')}</Th>
        </HeadRow>
      </thead>
      <tbody>
        {rows.map((ev) => (
          <BodyRow key={ev.id}>
            <Td className="whitespace-nowrap">{fmtInstant(ev.occurred_at)}</Td>
            <Td>{t(`elevators.events.kinds.${ev.event_kind}`, { defaultValue: ev.event_kind })}</Td>
            <Td>
              {ev.event_kind === 'status_changed' ? (
                <span className="flex items-center gap-1.5">
                  <ElevatorStatusBadge status={(ev.old_status as ElevatorStatus | null) ?? null} />
                  <span className="text-text-muted">→</span>
                  <ElevatorStatusBadge status={(ev.new_status as ElevatorStatus | null) ?? null} />
                </span>
              ) : '—'}
            </Td>
            <Td>{t(`elevators.events.sources.${ev.source}`, { defaultValue: ev.source })}</Td>
            <Td>{ev.actor_user_id !== null ? `#${ev.actor_user_id}` : t('elevators.events.system')}</Td>
            <Td className="max-w-64 truncate" >{ev.reason ?? '—'}</Td>
            <Td>
              {ev.request_number ? (
                <Link to={`/dashboard?request=${ev.request_number}`} className="font-semibold text-accent hover:underline">
                  №{ev.request_number}
                </Link>
              ) : '—'}
            </Td>
          </BodyRow>
        ))}
      </tbody>
    </TableShell>
  )
}
