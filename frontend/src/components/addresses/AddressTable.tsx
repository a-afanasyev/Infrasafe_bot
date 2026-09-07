import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Pencil, Power, PowerOff, Trash2 } from 'lucide-react'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../../types/api'
import EmptyState from '../shared/EmptyState'
import ConfirmDialog from '../shared/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { useApartmentBalances, paymentsEnabled } from '@/hooks/useApartmentBalances'
import { formatBalanceCell, formatBusinessDate } from '../payment/format'
import { cn } from '@/lib/utils'
import { SortIndicator, type SortHeaderProps } from '../shared/SortIndicator'
import { useTableSort, type UseTableSortResult } from '../../hooks/useTableSort'
import {
  apartmentColumns,
  BUILDING_COLUMNS,
  houseLabel,
  YARD_COLUMNS,
  type GridColumn,
} from './addressSortColumns'

// -- Table configs --------------------------------------------------------

const YARD_COLS = '2fr 2.5fr 0.8fr 0.8fr 1fr'
const BUILDING_COLS = '2.5fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr'
// дом · номер · подъезд/этаж · площадь · жителей · счёт · [баланс] · статус · действия
const APT_COLS = '0.7fr 0.7fr 0.9fr 0.7fr 0.5fr 1.1fr 1.1fr 0.35fr 0.9fr'
const APT_COLS_NO_BALANCE = '0.7fr 0.7fr 0.9fr 0.7fr 0.5fr 1.1fr 0.35fr 0.9fr'

/**
 * Номера квартир и домов — текст («1G», «10»), поэтому обычная сортировка даёт
 * 1, 10, 100, 11, 2. Числовой коллатор восстанавливает человеческий порядок.
 * Создаётся один раз на модуль: конструктор Intl дорогой.
 */
const naturalOrder = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function byHouseThenNumber(a: ApartmentBrief, b: ApartmentBrief): number {
  const house = naturalOrder.compare(houseLabel(a.building_address), houseLabel(b.building_address))
  return house !== 0 ? house : naturalOrder.compare(a.apartment_number, b.apartment_number)
}

// -- Component ------------------------------------------------------------

interface AddressTableProps {
  level: 'yards' | 'buildings' | 'apartments'
  yards?: YardBrief[]
  buildings?: BuildingBrief[]
  apartments?: ApartmentBrief[]
  onYardClick?: (yard: YardBrief) => void
  onBuildingClick?: (building: BuildingBrief) => void
  onApartmentClick?: (apt: ApartmentBrief) => void
  onEditYard?: (yard: YardBrief) => void
  onEditBuilding?: (building: BuildingBrief) => void
  onEditApartment?: (apt: ApartmentBrief) => void
  onToggleYard?: (id: number, active: boolean) => void
  onToggleBuilding?: (id: number, active: boolean) => void
  onToggleApartment?: (id: number, active: boolean) => void
  onDeleteYard?: (id: number) => void
  /** Hard-delete an already-soft-deleted yard (is_active=False). */
  onPurgeYard?: (id: number) => void
  onDeleteBuilding?: (id: number) => void
  /** Hard-delete an already-soft-deleted building (is_active=False). */
  onPurgeBuilding?: (id: number) => void
  onDeleteApartment?: (id: number) => void
  /** Hard-delete an already-soft-deleted apartment (is_active=False). */
  onPurgeApartment?: (id: number) => void
}

/** `labelled={false}` — только кружок: в таблице квартир подпись повторялась бы
 *  в каждой строке, значение цвета объясняет легенда над заголовками. */
function StatusDot({ active, labelled = true }: { active: boolean; labelled?: boolean }) {
  const { t } = useTranslation()
  const label = active ? t('addresses.active') : t('addresses.inactive')
  return (
    <div className="flex items-center gap-1.5">
      <span
        role="img"
        aria-label={label}
        title={label}
        className={cn(
          'inline-block w-2 h-2 rounded-full shrink-0',
          active ? 'bg-emerald' : 'bg-text-muted'
        )}
      />
      {labelled && (
        <span className={cn(
          'text-[11px]',
          active ? 'text-emerald' : 'text-text-muted'
        )}>
          {label}
        </span>
      )}
    </div>
  )
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('inline-block w-2 h-2 rounded-full shrink-0', className)} />
      {label}
    </span>
  )
}

/** Компактная кнопка-иконка строки таблицы: доступное имя обязательно —
 *  без подписи иконка иначе неотличима для скринридера. */
function RowAction({ label, onClick, className, children }: {
  label: string
  onClick: () => void
  className?: string
  children: React.ReactNode
}) {
  return (
    <Button
      variant="ghost"
      className={cn('h-7 w-7 p-0', className)}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}

const HEADER_CLASS =
  'text-text-muted text-[10px] font-bold uppercase tracking-wide font-[family-name:var(--font-display)]'

/**
 * Ячейка шапки grid-«таблицы». Индикатор сортировки рендерится ВНУТРИ неё:
 * каждый прямой ребёнок шапки — отдельная колонка сетки, соседний элемент
 * сдвинул бы все последующие. Роль `columnheader` нужна, чтобы `aria-sort`
 * был легален вне настоящей `<table>`.
 */
function HeaderCell({ children, sort }: { children: React.ReactNode; sort?: SortHeaderProps }) {
  if (!sort) return <span className={HEADER_CLASS}>{children}</span>
  return (
    <span className={HEADER_CLASS} role="columnheader" aria-sort={sort.ariaSort}>
      <SortIndicator {...sort}>{children}</SortIndicator>
    </span>
  )
}

/** Шапка целиком: подписи из описаний колонок, сортируемые — кнопками. */
function GridHeader<T extends { id: number }>({
  columns,
  sort,
  cols,
}: {
  columns: readonly GridColumn<T>[]
  sort: UseTableSortResult<T>
  cols: string
}) {
  const { t } = useTranslation()
  return (
    <div
      className="grid bg-bg-surface border-b border-border-default px-4 py-2.5 gap-2"
      style={{ gridTemplateColumns: cols }}
      role="row"
    >
      {columns.map(c => (
        <HeaderCell
          key={c.id}
          sort={
            c.value
              ? {
                  direction: sort.direction(c.id),
                  ariaSort: sort.ariaSort(c.id),
                  onToggle: () => sort.toggle(c.id),
                }
              : undefined
          }
        >
          {t(c.labelKey)}
        </HeaderCell>
      ))}
    </div>
  )
}

export default function AddressTable(props: AddressTableProps) {
  const { level } = props

  if (level === 'yards') return <YardsTable {...props} />
  if (level === 'buildings') return <BuildingsTable {...props} />
  return <ApartmentsTable {...props} />
}

// -- Yards ----------------------------------------------------------------

function YardsTable({
  yards,
  onYardClick,
  onEditYard,
  onToggleYard,
  onDeleteYard,
  onPurgeYard,
}: AddressTableProps) {
  const { t } = useTranslation()
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  // Carry the display name into the dialog state — otherwise the confirm
  // template renders `…""?` because the i18n placeholder gets an empty string.
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null; name: string }>({ open: false, id: null, name: '' })
  const [confirmPurge, setConfirmPurge] = useState<{ open: boolean; id: number | null; name: string }>({ open: false, id: null, name: '' })
  const source = yards ?? []
  const sort = useTableSort(YARD_COLUMNS, 'addresses_yards_sort_v1')
  const items = sort.sortRows(source)

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🏘️" title={t('addresses.noAddresses')} subtitle={t('addresses.noAddressesDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <GridHeader columns={YARD_COLUMNS} sort={sort} cols={YARD_COLS} />

      {items.map((yard, idx) => {
        const isLast = idx === items.length - 1
        const isHovered = hoveredId === yard.id

        return (
          <div
            key={yard.id}
            onClick={() => onYardClick?.(yard)}
            onMouseEnter={() => setHoveredId(yard.id)}
            onMouseLeave={() => setHoveredId(null)}
            className={cn(
              'grid px-4 py-2.5 gap-2 items-center cursor-pointer transition-colors duration-100',
              !isLast && 'border-b border-border-default',
              isHovered ? 'bg-bg-surface' : 'bg-transparent'
            )}
            style={{ gridTemplateColumns: YARD_COLS }}
          >
            <span className="text-xs text-text-primary font-semibold">{yard.name}</span>
            <span className="text-xs text-text-muted truncate">
              {yard.description ?? '—'}
            </span>
            <span className="text-xs text-text-primary">{yard.buildings_count}</span>
            <StatusDot active={yard.is_active} />
            <div onClick={e => e.stopPropagation()} className="flex items-center gap-2">
              <button onClick={() => onEditYard?.(yard)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-accent">
                {t('common.edit')}
              </button>
              <button onClick={() => onToggleYard?.(yard.id, !yard.is_active)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-amber">
                {yard.is_active ? t('addresses.deactivate') : t('addresses.activate')}
              </button>
              {yard.is_active ? (
                <button
                  onClick={() => setConfirmDelete({ open: true, id: yard.id, name: yard.name })}
                  className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-red"
                >
                  {t('common.delete')}
                </button>
              ) : (
                <button
                  onClick={() => setConfirmPurge({ open: true, id: yard.id, name: yard.name })}
                  className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-red"
                >
                  {t('common.deletePermanently')}
                </button>
              )}
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title={t('addressModals.deleteYardTitle')}
        description={t('addressModals.confirmDeleteYard', { name: confirmDelete.name })}
        confirmLabel={t('common.delete')}
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteYard?.(confirmDelete.id)
        }}
        variant="danger"
      />
      <ConfirmDialog
        open={confirmPurge.open}
        onOpenChange={(open) => setConfirmPurge(prev => ({ ...prev, open }))}
        title={t('common.deletePermanently')}
        description={t('addressModals.confirmPurgeYard', { name: confirmPurge.name })}
        confirmLabel={t('common.deletePermanently')}
        onConfirm={() => {
          if (confirmPurge.id !== null) onPurgeYard?.(confirmPurge.id)
        }}
        variant="danger"
      />
    </div>
  )
}

// -- Buildings ------------------------------------------------------------

function BuildingsTable({
  buildings,
  onBuildingClick,
  onEditBuilding,
  onToggleBuilding,
  onDeleteBuilding,
  onPurgeBuilding,
}: AddressTableProps) {
  const { t } = useTranslation()
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null; address: string }>({ open: false, id: null, address: '' })
  // Purge is a separate, more dangerous confirm — keep state isolated so the
  // dialog text and the mutation it triggers can't be mixed up.
  const [confirmPurge, setConfirmPurge] = useState<{ open: boolean; id: number | null; address: string }>({ open: false, id: null, address: '' })
  const source = buildings ?? []
  const sort = useTableSort(BUILDING_COLUMNS, 'addresses_buildings_sort_v1')
  const items = sort.sortRows(source)

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🏢" title={t('addresses.noBuildingsFound')} subtitle={t('addresses.noBuildingsFoundDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <GridHeader columns={BUILDING_COLUMNS} sort={sort} cols={BUILDING_COLS} />

      {items.map((bld, idx) => {
        const isLast = idx === items.length - 1
        const isHovered = hoveredId === bld.id

        return (
          <div
            key={bld.id}
            onClick={() => onBuildingClick?.(bld)}
            onMouseEnter={() => setHoveredId(bld.id)}
            onMouseLeave={() => setHoveredId(null)}
            className={cn(
              'grid px-4 py-2.5 gap-2 items-center cursor-pointer transition-colors duration-100',
              !isLast && 'border-b border-border-default',
              isHovered ? 'bg-bg-surface' : 'bg-transparent'
            )}
            style={{ gridTemplateColumns: BUILDING_COLS }}
          >
            <span className="text-xs text-text-primary font-semibold">{bld.address}</span>
            <span className="text-xs text-text-primary">{bld.entrance_count}</span>
            <span className="text-xs text-text-primary">{bld.floor_count}</span>
            <span className="text-xs text-text-primary">{bld.apartments_count}</span>
            <StatusDot active={bld.is_active} />
            <div onClick={e => e.stopPropagation()} className="flex items-center gap-2">
              <button onClick={() => onEditBuilding?.(bld)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-accent">
                {t('common.edit')}
              </button>
              <button onClick={() => onToggleBuilding?.(bld.id, !bld.is_active)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-amber">
                {bld.is_active ? t('addresses.deactivate') : t('addresses.activate')}
              </button>
              {bld.is_active ? (
                <button
                  onClick={() => setConfirmDelete({ open: true, id: bld.id, address: bld.address })}
                  className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-red"
                >
                  {t('common.delete')}
                </button>
              ) : (
                <button
                  onClick={() => setConfirmPurge({ open: true, id: bld.id, address: bld.address })}
                  className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-red"
                >
                  {t('common.deletePermanently')}
                </button>
              )}
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title={t('addressModals.deleteBuildingTitle')}
        description={t('addressModals.confirmDeleteBuilding', { name: confirmDelete.address })}
        confirmLabel={t('common.delete')}
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteBuilding?.(confirmDelete.id)
        }}
        variant="danger"
      />
      <ConfirmDialog
        open={confirmPurge.open}
        onOpenChange={(open) => setConfirmPurge(prev => ({ ...prev, open }))}
        title={t('common.deletePermanently')}
        description={t('addressModals.confirmPurgeBuilding', { name: confirmPurge.address })}
        confirmLabel={t('common.deletePermanently')}
        onConfirm={() => {
          if (confirmPurge.id !== null) onPurgeBuilding?.(confirmPurge.id)
        }}
        variant="danger"
      />
    </div>
  )
}

/**
 * Баланс строки. Состояния РАЗДЕЛЕНЫ намеренно: недоступность сервиса и
 * отсутствие выгрузки никогда не должны выглядеть как «долгов нет».
 */
function BalanceCell({ account, balances }: {
  account?: string | null
  balances: ReturnType<typeof useApartmentBalances>
}) {
  const { t } = useTranslation()
  if (!account) return <span className="text-xs text-text-muted">—</span>
  if (balances.state === 'loading') return <span className="inline-block h-3 w-16 rounded-sm bg-bg-surface animate-pulse" />
  if (balances.state === 'error') return <span className="text-xs text-text-muted">{t('addresses.balanceUnavailable')}</span>

  const snapshot = balances.map[account.trim()]
  const cell = formatBalanceCell(snapshot)
  if (!cell) return <span className="text-xs text-text-muted">{t('addresses.balanceNoData')}</span>

  const stale = balances.asOf !== null && snapshot.as_of !== balances.asOf
  return (
    <span className="flex items-center gap-1 text-xs font-semibold" title={snapshot.filename}>
      <span className={cn(
        cell.tone === 'debt' && 'text-red',
        cell.tone === 'prepayment' && 'text-emerald',
        cell.tone === 'zero' && 'text-text-muted',
      )}>
        {cell.text}
      </span>
      {stale && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-amber shrink-0"
          title={formatBusinessDate(snapshot.as_of)}
          aria-label={t('addresses.balanceMixedDates')}
        />
      )}
    </span>
  )
}

// -- Apartments -----------------------------------------------------------

function ApartmentsTable({
  apartments,
  onApartmentClick,
  onEditApartment,
  onToggleApartment,
  onDeleteApartment,
  onPurgeApartment,
}: AddressTableProps) {
  const { t } = useTranslation()
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null; number: string }>({ open: false, id: null, number: '' })
  const [confirmPurge, setConfirmPurge] = useState<{ open: boolean; id: number | null; number: string }>({ open: false, id: null, number: '' })
  const source = apartments ?? []
  const showBalance = paymentsEnabled()
  // Счета берём из НЕсортированного списка: иначе появилась бы петля
  // «строки → счета → балансы → строки», когда сортируем по балансу.
  // Ключ запроса всё равно строится из отсортированных счетов, так что
  // переупорядочивание строк кэш не роняет.
  const balances = useApartmentBalances(useMemo(() => source.map(a => a.account_number), [source]))
  const columns = useMemo(() => apartmentColumns(showBalance, balances), [showBalance, balances])
  // Порядок по умолчанию — прежняя группировка «дом → номер»; он же вторичный
  // ключ, чтобы при сортировке по площади квартиры одного размера не шли вразнобой.
  const sort = useTableSort(columns, 'addresses_apartments_sort_v1', byHouseThenNumber)
  const items = sort.sortRows(source)
  const cols = showBalance ? APT_COLS : APT_COLS_NO_BALANCE

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🚪" title={t('addresses.noApartmentsFound')} subtitle={t('addresses.noApartmentsFoundDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-2 border-b border-border-default text-[11px] text-text-muted">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <LegendSwatch className="bg-emerald" label={t('addresses.active')} />
          <LegendSwatch className="bg-text-muted" label={t('addresses.inactive')} />
          {showBalance && <LegendSwatch className="bg-red" label={t('paymentControl.debt')} />}
          {showBalance && <LegendSwatch className="bg-emerald" label={t('paymentControl.prepayment')} />}
        </div>
        {showBalance && balances.state === 'ready' && balances.asOf && (
          <div className="flex flex-wrap items-center gap-x-2">
            <span>{`${t('paymentControl.asOf')}: ${formatBusinessDate(balances.asOf)}${balances.source ? ` · ${balances.source}` : ''}`}</span>
            {balances.mixedDates && <span className="text-amber">{t('addresses.balanceMixedDates')}</span>}
          </div>
        )}
      </div>

      <GridHeader columns={columns} sort={sort} cols={cols} />

      {items.map((apt, idx) => {
        const isLast = idx === items.length - 1
        const isHovered = hoveredId === apt.id

        return (
          <div
            key={apt.id}
            onClick={() => onApartmentClick?.(apt)}
            onMouseEnter={() => setHoveredId(apt.id)}
            onMouseLeave={() => setHoveredId(null)}
            className={cn(
              'grid px-4 py-2.5 gap-2 items-center cursor-pointer transition-colors duration-100',
              !isLast && 'border-b border-border-default',
              isHovered ? 'bg-bg-surface' : 'bg-transparent'
            )}
            style={{ gridTemplateColumns: cols }}
          >
            <span className="text-xs text-text-muted truncate" title={apt.building_address ?? undefined}>
              {houseLabel(apt.building_address)}
            </span>
            <span className="text-xs text-text-primary font-semibold">{apt.apartment_number}</span>
            <span className="text-xs text-text-muted">{`${apt.entrance ?? '—'} / ${apt.floor ?? '—'}`}</span>
            <span className="text-xs text-text-muted">{apt.area ? `${apt.area} м²` : '—'}</span>
            <span className="text-xs text-text-primary">{apt.residents_count}</span>
            <span className="text-xs text-text-muted font-mono truncate" title={apt.account_number ?? undefined}>
              {apt.account_number || '—'}
            </span>
            {showBalance && <BalanceCell account={apt.account_number} balances={balances} />}
            <StatusDot active={apt.is_active} labelled={false} />
            <div onClick={e => e.stopPropagation()} className="flex items-center gap-1">
              <RowAction label={t('common.edit')} className="text-accent" onClick={() => onEditApartment?.(apt)}>
                <Pencil className="h-3.5 w-3.5" />
              </RowAction>
              <RowAction
                label={apt.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                className="text-amber"
                onClick={() => onToggleApartment?.(apt.id, !apt.is_active)}
              >
                {apt.is_active ? <PowerOff className="h-3.5 w-3.5" /> : <Power className="h-3.5 w-3.5" />}
              </RowAction>
              <RowAction
                label={apt.is_active ? t('common.delete') : t('common.deletePermanently')}
                className="text-red"
                onClick={() => (apt.is_active
                  ? setConfirmDelete({ open: true, id: apt.id, number: apt.apartment_number })
                  : setConfirmPurge({ open: true, id: apt.id, number: apt.apartment_number }))}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </RowAction>
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title={t('addressModals.deleteApartmentTitle')}
        description={t('addressModals.confirmDeleteApartment', { name: confirmDelete.number })}
        confirmLabel={t('common.delete')}
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteApartment?.(confirmDelete.id)
        }}
        variant="danger"
      />
      <ConfirmDialog
        open={confirmPurge.open}
        onOpenChange={(open) => setConfirmPurge(prev => ({ ...prev, open }))}
        title={t('common.deletePermanently')}
        description={t('addressModals.confirmPurgeApartment', { name: confirmPurge.number })}
        confirmLabel={t('common.deletePermanently')}
        onConfirm={() => {
          if (confirmPurge.id !== null) onPurgeApartment?.(confirmPurge.id)
        }}
        variant="danger"
      />
    </div>
  )
}
