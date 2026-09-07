import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { FileX2, ShieldAlert, Wrench } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import ElevatorStatusBadge from './ElevatorStatusBadge'
import { BodyRow, HeadRow, TableShell, Td, Th } from './TableCells'
import { fmtAvailability, fmtInstant } from '../../utils/elevatorsFormat'
import type { ElevatorCard, ElevatorFlags } from '../../types/elevators'
import type { UseTableSortResult } from '../../hooks/useTableSort'
import { ELEVATOR_COLUMNS, type ElevatorColumn } from './elevatorSortColumns'

/** Таблица реестра: label, статус, с какого времени, доступность 30д, флаги, заявки, «Открыть». */
interface Props {
  items: ElevatorCard[]
  /** Состояние сортировки страницы; без него заголовки статичные. */
  sort?: UseTableSortResult<ElevatorCard>
}

function FlagIcons({ flags }: { flags: ElevatorFlags }) {
  const { t } = useTranslation()
  return (
    <span className="flex items-center gap-1.5">
      {flags.no_contract && (
        <span role="img" aria-label={t('elevators.flags.no_contract')} title={t('elevators.flags.no_contract')} className="text-orange">
          <FileX2 size={15} aria-hidden />
        </span>
      )}
      {flags.cert_expired && (
        <span role="img" aria-label={t('elevators.flags.cert_expired')} title={t('elevators.flags.cert_expired')} className="text-red">
          <ShieldAlert size={15} aria-hidden />
        </span>
      )}
      {flags.maintenance_overdue && (
        <span role="img" aria-label={t('elevators.flags.maintenance_overdue')} title={t('elevators.flags.maintenance_overdue')} className="text-red">
          <Wrench size={15} aria-hidden />
        </span>
      )}
    </span>
  )
}

export default function ElevatorTable({ items, sort }: Props) {
  const { t } = useTranslation()
  /** Кликабельны только колонки, которые умеет упорядочить сервер. */
  const headProps = (column: ElevatorColumn) =>
    sort && column.serverField
      ? {
          direction: sort.direction(column.id),
          ariaSort: sort.ariaSort(column.id),
          onToggle: () => sort.toggle(column.id),
        }
      : undefined

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🛗" title={t('elevators.empty')} />
      </div>
    )
  }
  return (
    <TableShell>
      <thead>
        <HeadRow>
          {ELEVATOR_COLUMNS.map(column => (
            <Th key={column.id} sort={headProps(column)}>{t(column.labelKey)}</Th>
          ))}
        </HeadRow>
      </thead>
      <tbody>
        {items.map((row) => (
          <BodyRow key={row.id} className={row.archived_at ? 'opacity-60' : ''}>
            <Td>
              <div className="flex flex-col">
                <span className="font-semibold">{row.label}</span>
                <span className="text-[11px] text-text-muted">{row.building_address}</span>
              </div>
              {row.archived_at && (
                <span className="ml-2 rounded-full bg-bg-surface text-text-muted text-[11px] px-2 py-0.5">
                  {t('elevators.archivedBadge')}
                </span>
              )}
            </Td>
            <Td><ElevatorStatusBadge status={row.current_status} /></Td>
            <Td className="whitespace-nowrap">{fmtInstant(row.status_since)}</Td>
            <Td>{fmtAvailability(row.availability_30d)}</Td>
            <Td><FlagIcons flags={row.flags} /></Td>
            <Td className={row.open_requests_count > 0 ? 'font-semibold' : ''}>{row.open_requests_count}</Td>
            <Td>
              <Button asChild variant="outline" size="sm">
                <Link to={`/dashboard/elevators/${row.id}`}>{t('elevators.actions.open')}</Link>
              </Button>
            </Td>
          </BodyRow>
        ))}
      </tbody>
    </TableShell>
  )
}
