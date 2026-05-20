import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../../types/api'
import EmptyState from '../shared/EmptyState'
import ConfirmDialog from '../shared/ConfirmDialog'
import { cn } from '@/lib/utils'

// -- Table configs --------------------------------------------------------

const YARD_COLS = '2fr 2.5fr 0.8fr 0.8fr 1fr'
const BUILDING_COLS = '2.5fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr'
const APT_COLS = '0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr'

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

function StatusDot({ active }: { active: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn(
        'inline-block w-2 h-2 rounded-full shrink-0',
        active ? 'bg-emerald' : 'bg-text-muted'
      )} />
      <span className={cn(
        'text-[11px]',
        active ? 'text-emerald' : 'text-text-muted'
      )}>
        {active ? t('addresses.active') : t('addresses.inactive')}
      </span>
    </div>
  )
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-text-muted text-[10px] font-bold uppercase tracking-wide font-[family-name:var(--font-display)]">
      {children}
    </span>
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
  const items = yards ?? []

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🏘️" title={t('addresses.noAddresses')} subtitle={t('addresses.noAddressesDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div
        className="grid bg-bg-surface border-b border-border-default px-4 py-2.5 gap-2"
        style={{ gridTemplateColumns: YARD_COLS }}
      >
        {[t('addresses.yardName'), t('addresses.description'), t('addresses.stats.buildings'), t('addresses.status'), t('common.actions')].map(h => (
          <HeaderCell key={h}>{h}</HeaderCell>
        ))}
      </div>

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
        title={t('addressModals.confirmDeleteYard', { name: confirmDelete.name })}
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
  const items = buildings ?? []

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🏢" title={t('addresses.noBuildingsFound')} subtitle={t('addresses.noBuildingsFoundDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div
        className="grid bg-bg-surface border-b border-border-default px-4 py-2.5 gap-2"
        style={{ gridTemplateColumns: BUILDING_COLS }}
      >
        {[t('addresses.buildingAddress'), t('addresses.entrances'), t('addresses.floors'), t('addresses.stats.apartments'), t('addresses.status'), t('common.actions')].map(h => (
          <HeaderCell key={h}>{h}</HeaderCell>
        ))}
      </div>

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
        title={t('addressModals.confirmDeleteBuilding', { name: confirmDelete.address })}
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
  const items = apartments ?? []

  if (items.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🚪" title={t('addresses.noApartmentsFound')} subtitle={t('addresses.noApartmentsFoundDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div
        className="grid bg-bg-surface border-b border-border-default px-4 py-2.5 gap-2"
        style={{ gridTemplateColumns: APT_COLS }}
      >
        {[t('addresses.apartmentNumber'), t('addresses.entrance'), t('addresses.floor'), t('addresses.rooms'), t('addresses.area'), t('addresses.residentsCount'), t('addresses.status'), t('common.actions')].map(h => (
          <HeaderCell key={h}>{h}</HeaderCell>
        ))}
      </div>

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
            style={{ gridTemplateColumns: APT_COLS }}
          >
            <span className="text-xs text-text-primary font-semibold">{apt.apartment_number}</span>
            <span className="text-xs text-text-muted">{apt.entrance ?? '—'}</span>
            <span className="text-xs text-text-muted">{apt.floor ?? '—'}</span>
            <span className="text-xs text-text-muted">{apt.rooms_count ?? '—'}</span>
            <span className="text-xs text-text-muted">{apt.area ? `${apt.area} м²` : '—'}</span>
            <span className="text-xs text-text-primary">{apt.residents_count}</span>
            <StatusDot active={apt.is_active} />
            <div onClick={e => e.stopPropagation()} className="flex items-center gap-2">
              <button onClick={() => onEditApartment?.(apt)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-accent">
                {t('common.edit')}
              </button>
              <button onClick={() => onToggleApartment?.(apt.id, !apt.is_active)} className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-amber">
                {apt.is_active ? t('addresses.deactivate') : t('addresses.activate')}
              </button>
              {apt.is_active ? (
                <button
                  onClick={() => setConfirmDelete({ open: true, id: apt.id, number: apt.apartment_number })}
                  className="bg-transparent border-none cursor-pointer text-[11px] font-[family-name:var(--font-display)] text-red"
                >
                  {t('common.delete')}
                </button>
              ) : (
                <button
                  onClick={() => setConfirmPurge({ open: true, id: apt.id, number: apt.apartment_number })}
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
        title={t('addressModals.confirmDeleteApartment', { name: confirmDelete.number })}
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
