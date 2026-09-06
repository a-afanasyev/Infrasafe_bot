import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import LoadingSpinner from '../shared/LoadingSpinner'
import EmptyState from '../shared/EmptyState'
import { BodyRow, HeadRow, TableShell, Td, Th } from './TableCells'
import {
  CompleteOccurrenceDialog,
  CreateOccurrenceDialog,
  GenerateOccurrencesDialog,
  RescheduleOccurrenceDialog,
} from './OccurrenceDialogs'
import { useCancelOccurrence, useElevatorOccurrences } from '../../hooks/useElevatorCalendar'
import { DASH, fmtDateOnly, fmtInstant } from '../../utils/elevatorsFormat'
import {
  OCCURRENCE_KINDS,
  type CalendarState,
  type ElevatorOccurrence,
  type OccurrenceKind,
} from '../../types/elevators'

const STATES: readonly CalendarState[] = ['planned', 'done', 'cancelled', 'all'] as const

/**
 * Вкладка «Календарь» лифта: записи графика с фильтром по виду/состоянию,
 * «Добавить пункт»/«Сгенерировать» (manager), у planned — Перенести/Отменить
 * (manager) и «Выполнено» (executor и manager).
 */
interface Props {
  elevatorId: number
  canWrite: boolean
}

export default function ElevatorCalendarTab({ elevatorId, canWrite }: Props) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<OccurrenceKind | undefined>(undefined)
  const [state, setState] = useState<CalendarState>('planned')
  const [createOpen, setCreateOpen] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [reschedule, setReschedule] = useState<ElevatorOccurrence | null>(null)
  const [complete, setComplete] = useState<ElevatorOccurrence | null>(null)
  const occurrences = useElevatorOccurrences(elevatorId, { kind, state })
  const cancel = useCancelOccurrence(elevatorId)
  const rows = occurrences.data ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            className="max-w-44"
            aria-label={t('elevators.occurrences.kindLabel')}
            value={kind ?? ''}
            onChange={(e) => setKind((e.target.value || undefined) as OccurrenceKind | undefined)}
          >
            <option value="">{t('elevators.occurrences.allKinds')}</option>
            {OCCURRENCE_KINDS.map((k) => (
              <option key={k} value={k}>{t(`elevators.occurrences.kind.${k}`)}</option>
            ))}
          </Select>
          <Select
            className="max-w-44"
            aria-label={t('elevators.occurrences.stateLabel')}
            value={state}
            onChange={(e) => setState(e.target.value as CalendarState)}
          >
            {STATES.map((s) => (
              <option key={s} value={s}>{t(`elevators.occurrences.state.${s}`)}</option>
            ))}
          </Select>
        </div>
        {canWrite && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}>{t('elevators.actions.addOccurrence')}</Button>
            <Button size="sm" variant="outline" onClick={() => setGenerateOpen(true)}>{t('elevators.actions.generate')}</Button>
          </div>
        )}
      </div>

      {occurrences.isLoading ? (
        <LoadingSpinner />
      ) : occurrences.isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : rows.length === 0 ? (
        <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
          <EmptyState icon="🗓️" title={t('elevators.occurrences.empty')} />
        </div>
      ) : (
        <TableShell>
          <thead>
            <HeadRow>
              <Th>{t('elevators.occurrences.dueOn')}</Th>
              <Th>{t('elevators.occurrences.kindLabel')}</Th>
              <Th>{t('elevators.occurrences.stateLabel')}</Th>
              <Th>{t('elevators.occurrences.doneAt')}</Th>
              <Th>{t('elevators.occurrences.comment')}</Th>
              <Th>{t('elevators.occurrences.request')}</Th>
              <Th><span className="sr-only">{t('elevators.columns.actions')}</span></Th>
            </HeadRow>
          </thead>
          <tbody>
            {rows.map((o) => (
              <BodyRow key={o.id}>
                <Td className="whitespace-nowrap font-semibold">{fmtDateOnly(o.due_on)}</Td>
                <Td>{t(`elevators.occurrences.kind.${o.kind}`)}</Td>
                <Td>{t(`elevators.occurrences.state.${o.state}`)}</Td>
                <Td className="whitespace-nowrap">{fmtInstant(o.done_at)}</Td>
                <Td className="max-w-64 truncate">{o.comment ?? DASH}</Td>
                <Td>
                  {o.request_number ? (
                    <Link to={`/dashboard?request=${o.request_number}`} className="font-semibold text-accent hover:underline">
                      №{o.request_number}
                    </Link>
                  ) : DASH}
                </Td>
                <Td>
                  {o.state === 'planned' && (
                    <div className="flex items-center gap-1.5">
                      <Button size="sm" onClick={() => setComplete(o)}>{t('elevators.actions.complete')}</Button>
                      {canWrite && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => setReschedule(o)}>{t('elevators.actions.reschedule')}</Button>
                          <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(o.id)}>
                            {t('elevators.actions.cancel')}
                          </Button>
                        </>
                      )}
                    </div>
                  )}
                </Td>
              </BodyRow>
            ))}
          </tbody>
        </TableShell>
      )}

      <CreateOccurrenceDialog elevatorId={elevatorId} open={createOpen} onClose={() => setCreateOpen(false)} />
      <GenerateOccurrencesDialog elevatorId={elevatorId} open={generateOpen} onClose={() => setGenerateOpen(false)} />
      <RescheduleOccurrenceDialog elevatorId={elevatorId} occurrence={reschedule} onClose={() => setReschedule(null)} />
      <CompleteOccurrenceDialog elevatorId={elevatorId} occurrence={complete} onClose={() => setComplete(null)} />
    </div>
  )
}
