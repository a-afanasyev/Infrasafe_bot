import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '../shared/LoadingSpinner'
import EmptyState from '../shared/EmptyState'
import CreateRepairDialog from './CreateRepairDialog'
import { BodyRow, HeadRow, TableShell, Td, Th } from './TableCells'
import { usePersonName } from '../../hooks/usePersonName'
import { useBulkConfirmRequests, useElevatorRequests } from '../../hooks/useElevators'
import { tCategory, tStatus, tUrgency } from '../../i18n/apiMaps'
import { fmtInstant } from '../../utils/elevatorsFormat'
import {
  CONFIRMABLE_REQUEST_STATUSES,
  MAX_BULK_CONFIRM,
  type ElevatorBulkConfirmItem,
  type ElevatorDetail,
} from '../../types/elevators'

/**
 * Вкладка «Заявки»: список заявок лифта с чекбоксами у подтверждаемых
 * (статус «Выполнена» — канон MANAGER_CONFIRM), групповая приёмка с per-item
 * результатом и кнопка «Создать ремонт». Кнопки записи — только manager.
 */
interface Props {
  elevator: ElevatorDetail
  canWrite: boolean
}

export default function ElevatorRequestsTab({ elevator, canWrite }: Props) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const [includeClosed, setIncludeClosed] = useState(false)
  const [selected, setSelected] = useState<readonly string[]>([])
  const [results, setResults] = useState<ElevatorBulkConfirmItem[] | null>(null)
  const [repairOpen, setRepairOpen] = useState(false)
  const requests = useElevatorRequests(elevator.id, includeClosed)
  const bulk = useBulkConfirmRequests(elevator.id)

  const toggle = (num: string, checked: boolean) =>
    setSelected((prev) => (checked ? [...prev, num] : prev.filter((n) => n !== num)))

  const confirmSelected = () =>
    bulk.mutate([...selected], {
      onSuccess: (items) => {
        setResults(items)
        setSelected([])
      },
    })

  const rows = requests.data ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-[13px] text-text-secondary">
          <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
          {t('elevators.requests.includeClosed')}
        </label>
        {canWrite && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] text-text-muted">{t('elevators.requests.selected', { count: selected.length })}</span>
            <Button
              size="sm"
              disabled={selected.length === 0 || selected.length > MAX_BULK_CONFIRM || bulk.isPending}
              onClick={confirmSelected}
            >
              {t('elevators.actions.confirmSelected')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setRepairOpen(true)}>
              {t('elevators.actions.createRepair')}
            </Button>
          </div>
        )}
      </div>

      {results && (
        <div className="bg-bg-card border border-border-default rounded-default p-3 text-[13px] flex flex-col gap-1">
          <span className="font-semibold text-text-primary">{t('elevators.requests.resultTitle')}</span>
          {results.map((r) => (
            <span key={r.request_number} className={r.ok ? 'text-green' : 'text-red'}>
              №{r.request_number} — {r.ok ? t('elevators.requests.resultOk') : `${t('elevators.requests.resultFail')}: ${r.error ?? r.error_kind ?? ''}`}
            </span>
          ))}
        </div>
      )}

      {requests.isLoading ? (
        <LoadingSpinner />
      ) : requests.isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : rows.length === 0 ? (
        <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
          <EmptyState icon="📋" title={t('elevators.requests.empty')} />
        </div>
      ) : (
        <TableShell>
          <thead>
            <HeadRow>
              {canWrite && <Th />}
              <Th>{t('elevators.requests.number')}</Th>
              <Th>{t('elevators.requests.status')}</Th>
              <Th>{t('elevators.requests.category')}</Th>
              <Th>{t('elevators.requests.urgency')}</Th>
              <Th>{t('elevators.requests.created')}</Th>
              <Th>{t('elevators.requests.operational')}</Th>
              <Th>{t('elevators.requests.executor')}</Th>
              <Th>{t('elevators.requests.applicant')}</Th>
            </HeadRow>
          </thead>
          <tbody>
            {rows.map((r) => {
              const confirmable = CONFIRMABLE_REQUEST_STATUSES.includes(r.status)
              return (
                <BodyRow key={r.request_number}>
                  {canWrite && (
                    <Td>
                      {confirmable && (
                        <input
                          type="checkbox"
                          aria-label={r.request_number}
                          checked={selected.includes(r.request_number)}
                          onChange={(e) => toggle(r.request_number, e.target.checked)}
                        />
                      )}
                    </Td>
                  )}
                  <Td>
                    <Link to={`/dashboard?request=${r.request_number}`} className="font-semibold text-accent hover:underline">
                      №{r.request_number}
                    </Link>
                  </Td>
                  <Td>{tStatus(r.status, t)}</Td>
                  <Td>{tCategory(r.category, t)}</Td>
                  <Td>{tUrgency(r.urgency, t)}</Td>
                  <Td className="whitespace-nowrap">{fmtInstant(r.created_at)}</Td>
                  <Td>
                    {r.elevator_operational === null ? '—' : r.elevator_operational ? t('elevators.requests.yes') : t('elevators.requests.no')}
                  </Td>
                  <Td>{r.executor_name ? personName(r.executor_name) : '—'}</Td>
                  <Td>{r.applicant_name ? personName(r.applicant_name) : '—'}</Td>
                </BodyRow>
              )
            })}
          </tbody>
        </TableShell>
      )}

      <CreateRepairDialog elevator={elevator} open={repairOpen} onClose={() => setRepairOpen(false)} />
    </div>
  )
}
