import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useAddressStats,
  useYards,
  useBuildings,
  useApartments,
  useAllBuildings,
  useAllApartments,
  usePendingModeration,
  useDeleteYard,
  useDeleteBuilding,
  usePurgeBuilding,
  useDeleteApartment,
  useUpdateYard,
  useUpdateBuilding,
  useUpdateApartment,
} from '../hooks/useAddresses'
import type {
  YardBrief,
  BuildingBrief,
  ApartmentBrief,
} from '../types/api'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import YardFormModal from '../components/addresses/YardFormModal'
import BuildingFormModal from '../components/addresses/BuildingFormModal'
import ApartmentFormModal from '../components/addresses/ApartmentFormModal'
import AddObjectModal from '../components/addresses/AddObjectModal'
import BulkCreateModal from '../components/addresses/BulkCreateModal'
import ModerationPanel from '../components/addresses/ModerationPanel'
import ApartmentProfileModal from '../components/addresses/ApartmentProfileModal'
import AddressTable from '../components/addresses/AddressTable'
import ConfirmDialog from '../components/shared/ConfirmDialog'
import { usePageTitle } from '../hooks/usePageTitle'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'

// ── Types ───────────────────────────────────────────────────────────

type View = 'directory' | 'moderation'
type Level = 'yards' | 'buildings' | 'apartments' | 'all-buildings' | 'all-apartments'

// ── Action Menu (dropdown with click-outside) ───────────────────────

function ActionMenu({ children }: { children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        className="bg-transparent border-none cursor-pointer text-text-muted text-lg px-1.5 py-0.5 leading-none rounded-sm hover:bg-bg-surface"
      >
        ...
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 bg-bg-surface border border-border-default rounded-default shadow-[0_8px_24px_rgba(0,0,0,0.25)] z-10 min-w-[160px] overflow-hidden">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

function MenuItem({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick() }}
      className={cn(
        'w-full bg-transparent border-none cursor-pointer py-2 px-3.5 text-left text-[13px] font-[family-name:var(--font-display)] block hover:bg-bg-card',
        danger ? 'text-red' : 'text-text-primary'
      )}
    >
      {label}
    </button>
  )
}

// ── Main component ──────────────────────────────────────────────────

export default function AddressesPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.addresses'))
  const { setActions, clearActions } = useTopbar()

  // State
  const [view, setView] = useState<View>('directory')
  const [level, setLevel] = useState<Level>('yards')
  const [selectedYard, setSelectedYard] = useState<YardBrief | null>(null)
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingBrief | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Modal states
  const [editingYard, setEditingYard] = useState<YardBrief | null>(null)
  const [editingBuilding, setEditingBuilding] = useState<BuildingBrief | null>(null)
  const [editingApartment, setEditingApartment] = useState<ApartmentBrief | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [addObjectOpen, setAddObjectOpen] = useState(false)
  const [showBulkCreate, setShowBulkCreate] = useState(false)
  const [viewMode, setViewMode] = useState<'tile' | 'table'>(() => {
    try {
      const stored = localStorage.getItem('addresses_view_mode')
      return (stored === 'tile' || stored === 'table') ? stored : 'tile'
    } catch { return 'tile' }
  })
  const [profileApartmentId, setProfileApartmentId] = useState<number | null>(null)
  const [confirmState, setConfirmState] = useState<{
    open: boolean
    title: string
    description: string
    onConfirm: () => void
  }>({ open: false, title: '', description: '', onConfirm: () => {} })

  useEffect(() => {
    try { localStorage.setItem('addresses_view_mode', viewMode) } catch {}
  }, [viewMode])

  // Queries
  const { data: stats } = useAddressStats()
  const { data: yards = [], isLoading: yardsLoading } = useYards(showInactive)
  const { data: buildings = [], isLoading: buildingsLoading } = useBuildings(
    selectedYard?.id ?? null,
    showInactive,
  )
  const { data: apartments = [], isLoading: apartmentsLoading } = useApartments(
    selectedBuilding?.id ?? null,
    showInactive,
  )
  const { data: moderationItems = [] } = usePendingModeration()

  // Flat view filters
  const [filterYardId, setFilterYardId] = useState<number | null>(null)
  const [filterBuildingId, setFilterBuildingId] = useState<number | null>(null)
  const { data: allBuildings = [], isLoading: allBuildingsLoading } = useAllBuildings(
    level === 'all-buildings' ? filterYardId : undefined,
    level === 'all-buildings' ? showInactive : undefined,
  )
  const { data: allApartments = [], isLoading: allApartmentsLoading } = useAllApartments(
    level === 'all-apartments' ? filterYardId : undefined,
    level === 'all-apartments' ? filterBuildingId : undefined,
    level === 'all-apartments' ? showInactive : undefined,
  )
  // Buildings for the apartment filter dropdown (scoped by filterYardId)
  const { data: filterBuildings = [] } = useAllBuildings(
    level === 'all-apartments' ? filterYardId : undefined,
    false,
  )

  // Mutations
  const deleteYard = useDeleteYard()
  const deleteBuilding = useDeleteBuilding()
  const purgeBuilding = usePurgeBuilding()
  const deleteApartment = useDeleteApartment()
  const updateYard = useUpdateYard()
  const updateBuilding = useUpdateBuilding()
  const updateApartment = useUpdateApartment()

  // Navigation helpers
  const goToYards = useCallback(() => {
    setLevel('yards')
    setSelectedYard(null)
    setSelectedBuilding(null)
  }, [])

  const goToBuildings = useCallback(() => {
    setLevel('buildings')
    setSelectedBuilding(null)
  }, [])

  const handleYardClick = useCallback((yard: YardBrief) => {
    setLevel('buildings')
    setSelectedYard(yard)
    setSelectedBuilding(null)
  }, [])

  const handleBuildingClick = useCallback((building: BuildingBrief) => {
    // When navigating from flat buildings view, set the yard context too
    if (!selectedYard || selectedYard.id !== building.yard_id) {
      const yard = yards.find(y => y.id === building.yard_id)
      if (yard) setSelectedYard(yard)
    }
    setLevel('apartments')
    setSelectedBuilding(building)
  }, [selectedYard, yards])

  // Search filter
  const filterBySearch = useCallback((name: string) => {
    if (!searchQuery) return true
    return name.toLowerCase().includes(searchQuery.toLowerCase())
  }, [searchQuery])

  // Topbar actions
  const actionsNode = useMemo(() => (
    <div className="flex items-center gap-2">
      <Input
        type="text"
        placeholder={t('common.search')}
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        className="w-[200px]"
      />
      {level === 'apartments' ? (
        <Button onClick={() => setShowCreateModal(true)}>
          + {t('addressModals.addApartment')}
        </Button>
      ) : (
        <Button onClick={() => setAddObjectOpen(true)}>
          + {t('addresses.addObject')}
        </Button>
      )}
    </div>
  ), [searchQuery, level])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  // Stats
  const STATS = [
    {
      label: t('addresses.stats.yards'),
      value: stats ? `${stats.yards_active}/${stats.yards_total}` : '-',
      iconBg: 'var(--blue)',
      icon: '\u{1F3D8}',
      onClick: () => { setView('directory'); goToYards() },
    },
    {
      label: t('addresses.stats.buildings'),
      // Display active/total to match the yards card and the building list,
      // which already filters by is_active. Soft-deleted rows would otherwise
      // make the header counter disagree with what the user sees below it.
      value: stats ? `${stats.buildings_active}/${stats.buildings_total}` : '-',
      iconBg: 'var(--emerald)',
      icon: '\u{1F3E2}',
      onClick: () => { setView('directory'); setLevel('all-buildings'); setFilterYardId(null); setSelectedYard(null); setSelectedBuilding(null) },
    },
    {
      label: t('addresses.stats.apartments'),
      value: stats ? `${stats.apartments_active}/${stats.apartments_total}` : '-',
      iconBg: 'var(--amber)',
      icon: '\u{1F3E0}',
      onClick: () => { setView('directory'); setLevel('all-apartments'); setFilterYardId(null); setFilterBuildingId(null); setSelectedYard(null); setSelectedBuilding(null) },
    },
    {
      label: t('addresses.stats.residents'),
      value: stats ? `${stats.residents_approved}+${stats.residents_pending}` : '-',
      iconBg: 'var(--violet)',
      icon: '\u{1F465}',
      onClick: () => { setView('moderation') },
    },
  ]

  // Loading state
  const isLoading =
    (level === 'yards' && yardsLoading) ||
    (level === 'buildings' && buildingsLoading) ||
    (level === 'apartments' && apartmentsLoading) ||
    (level === 'all-buildings' && allBuildingsLoading) ||
    (level === 'all-apartments' && allApartmentsLoading)

  // Filtered data
  const filteredYards = yards.filter(y => filterBySearch(y.name))
  const filteredBuildings = buildings.filter(b => filterBySearch(b.address))
  const filteredApartments = apartments.filter(a => filterBySearch(a.apartment_number))

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {STATS.map(card => (
          <div
            key={card.label}
            onClick={card.onClick}
            className="bg-bg-card border border-border-default rounded-default p-4 flex items-center gap-3.5 cursor-pointer transition-colors hover:border-accent"
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center text-[22px] shrink-0"
              style={{ background: card.iconBg + '22' }}
            >
              {card.icon}
            </div>
            <div>
              <div className="font-[family-name:var(--font-mono)] text-[22px] font-semibold text-text-primary">
                {card.value}
              </div>
              <div className="text-[11px] text-text-muted mt-0.5">
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setView('directory')}
          className={cn(
            'rounded-full cursor-pointer text-[13px] px-4 py-1.5 font-[family-name:var(--font-display)] transition-all border',
            view === 'directory'
              ? 'bg-accent border-accent text-white font-semibold'
              : 'bg-bg-card border-border-default text-text-secondary font-normal'
          )}
        >
          {t('addresses.directory')}
        </button>
        <button
          onClick={() => setView('moderation')}
          className={cn(
            'rounded-full cursor-pointer text-[13px] px-4 py-1.5 font-[family-name:var(--font-display)] transition-all border',
            view === 'moderation'
              ? 'bg-accent border-accent text-white font-semibold'
              : 'bg-bg-card border-border-default text-text-secondary font-normal'
          )}
        >
          {t('addresses.moderation')}{moderationItems.length > 0 ? ` (${moderationItems.length})` : ''}
        </button>

        <div className="flex-1" />

        {/* View toggle */}
        {view === 'directory' && (
          <div className="flex gap-1">
            <button
              onClick={() => setViewMode('tile')}
              className={cn(
                'border rounded-md cursor-pointer text-base px-2.5 py-1 leading-none transition-all',
                viewMode === 'tile'
                  ? 'bg-accent border-accent text-white'
                  : 'bg-transparent border-border-default text-text-muted'
              )}
              title={t('employees.viewTile')}
            >{'\u229E'}</button>
            <button
              onClick={() => setViewMode('table')}
              className={cn(
                'border rounded-md cursor-pointer text-base px-2.5 py-1 leading-none transition-all',
                viewMode === 'table'
                  ? 'bg-accent border-accent text-white'
                  : 'bg-transparent border-border-default text-text-muted'
              )}
              title={t('employees.viewTable')}
            >{'\u2630'}</button>
          </div>
        )}

        {/* Show inactive toggle */}
        {view === 'directory' && (
          <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer font-[family-name:var(--font-display)]">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
              className="accent-accent"
            />
            {t('addresses.showInactive')}
          </label>
        )}
      </div>

      {/* Content area */}
      {view === 'moderation' ? (
        <ModerationPanel />
      ) : (
        <>
          {/* Breadcrumb / Title */}
          {level === 'all-buildings' ? (
            <div className="flex items-center gap-3 text-[13px] font-[family-name:var(--font-display)]">
              <span className="text-text-primary font-semibold">{t('addresses.allBuildings')}</span>
              <Select
                value={filterYardId ?? ''}
                onChange={e => setFilterYardId(e.target.value ? Number(e.target.value) : null)}
                className="w-[250px] text-xs"
              >
                <option value="">{t('addresses.allYards')}</option>
                {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
              </Select>
            </div>
          ) : level === 'all-apartments' ? (
            <div className="flex items-center gap-3 text-[13px] font-[family-name:var(--font-display)]">
              <span className="text-text-primary font-semibold">{t('addresses.allApartments')}</span>
              <Select
                value={filterYardId ?? ''}
                onChange={e => { setFilterYardId(e.target.value ? Number(e.target.value) : null); setFilterBuildingId(null) }}
                className="w-[250px] text-xs"
              >
                <option value="">{t('addresses.allYards')}</option>
                {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
              </Select>
              <Select
                value={filterBuildingId ?? ''}
                onChange={e => setFilterBuildingId(e.target.value ? Number(e.target.value) : null)}
                className="w-[250px] text-xs"
              >
                <option value="">{t('addresses.allBuildings')}</option>
                {filterBuildings.map(b => <option key={b.id} value={b.id}>{b.address}</option>)}
              </Select>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[13px] font-[family-name:var(--font-display)]">
              <span
                onClick={goToYards}
                className={cn(
                  'cursor-pointer',
                  level === 'yards' ? 'text-text-primary font-semibold' : 'text-accent'
                )}
              >
                {t('addresses.stats.yards')}
              </span>
              {selectedYard && (
                <>
                  <span className="text-text-muted">&rsaquo;</span>
                  <span
                    onClick={goToBuildings}
                    className={cn(
                      level === 'buildings' ? 'text-text-primary font-semibold cursor-default' : 'text-accent cursor-pointer'
                    )}
                  >
                    {selectedYard.name}
                  </span>
                </>
              )}
              {selectedBuilding && (
                <>
                  <span className="text-text-muted">&rsaquo;</span>
                  <span className="text-text-primary font-semibold">
                    {selectedBuilding.address}
                  </span>
                </>
              )}
            </div>
          )}

          {isLoading ? (
            <LoadingSpinner />
          ) : level === 'all-buildings' ? (
            <AddressTable
              level="buildings"
              buildings={allBuildings.filter(b => filterBySearch(b.address))}
              onBuildingClick={handleBuildingClick}
              onEditBuilding={(building) => setEditingBuilding(building)}
              onToggleBuilding={(id, active) => updateBuilding.mutate({ id, is_active: active })}
              onDeleteBuilding={(id) => deleteBuilding.mutate(id)}
              onPurgeBuilding={(id) => purgeBuilding.mutate(id)}
            />
          ) : level === 'all-apartments' ? (
            <AddressTable
              level="apartments"
              apartments={allApartments.filter(a => filterBySearch(a.apartment_number))}
              onApartmentClick={(apt) => setProfileApartmentId(apt.id)}
              onEditApartment={(apt) => setEditingApartment(apt)}
              onToggleApartment={(id, active) => updateApartment.mutate({ id, is_active: active })}
              onDeleteApartment={(id) => deleteApartment.mutate(id)}
            />
          ) : (
            <>
              {viewMode === 'tile' ? (
                <>
                  {/* Yards grid */}
                  {level === 'yards' && (
                    filteredYards.length === 0 ? (
                      <EmptyState icon={'\u{1F3D8}'} title={t('addresses.noAddresses')} subtitle={t('addresses.noAddressesDesc')} />
                    ) : (
                      <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
                        {filteredYards.map(yard => (
                          <div
                            key={yard.id}
                            onClick={() => handleYardClick(yard)}
                            className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
                          >
                            {/* Header */}
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center gap-2 flex-1 min-w-0">
                                <div className={cn('w-2 h-2 rounded-full shrink-0', yard.is_active ? 'bg-emerald' : 'bg-text-muted')} />
                                <div className="font-[family-name:var(--font-display)] font-semibold text-[15px] text-text-primary truncate">
                                  {yard.name}
                                </div>
                              </div>
                              <ActionMenu>
                                {(close) => (
                                  <>
                                    <MenuItem label={t('common.edit')} onClick={() => { close(); setEditingYard(yard) }} />
                                    <MenuItem
                                      label={yard.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                                      onClick={() => {
                                        close()
                                        updateYard.mutate({ id: yard.id, is_active: !yard.is_active })
                                      }}
                                    />
                                    <div className="h-px bg-border-default mx-2" />
                                    <MenuItem
                                      label={t('common.delete')}
                                      danger
                                      onClick={() => {
                                        close()
                                        setConfirmState({
                                          open: true,
                                          title: t('addressModals.confirmDeleteYard', { name: yard.name }),
                                          description: t('addressModals.confirmDeleteYard', { name: yard.name }),
                                          onConfirm: () => deleteYard.mutate(yard.id),
                                        })
                                      }}
                                    />
                                  </>
                                )}
                              </ActionMenu>
                            </div>

                            {/* Description */}
                            {yard.description && (
                              <div className="text-[13px] text-text-secondary mb-2.5 line-clamp-2 leading-snug">
                                {yard.description}
                              </div>
                            )}

                            {/* Footer */}
                            <div className="flex items-center gap-2 mt-1">
                              <span className="bg-blue/[.13] text-blue rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
                                {t('addresses.building', { count: yard.buildings_count })}
                              </span>
                              {!yard.is_active && (
                                <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  )}

                  {/* Buildings grid */}
                  {level === 'buildings' && (
                    filteredBuildings.length === 0 ? (
                      <EmptyState icon={'\u{1F3E2}'} title={t('addresses.noBuildingsFound')} subtitle={t('addresses.noBuildingsFoundDesc')} />
                    ) : (
                      <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
                        {filteredBuildings.map(building => (
                          <div
                            key={building.id}
                            onClick={() => handleBuildingClick(building)}
                            className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
                          >
                            {/* Header */}
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center gap-2 flex-1 min-w-0">
                                <div className={cn('w-2 h-2 rounded-full shrink-0', building.is_active ? 'bg-emerald' : 'bg-text-muted')} />
                                <div className="font-[family-name:var(--font-display)] font-semibold text-[15px] text-text-primary truncate">
                                  {building.address}
                                </div>
                              </div>
                              <ActionMenu>
                                {(close) => (
                                  <>
                                    <MenuItem label={t('common.edit')} onClick={() => { close(); setEditingBuilding(building) }} />
                                    <MenuItem
                                      label={building.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                                      onClick={() => {
                                        close()
                                        updateBuilding.mutate({ id: building.id, is_active: !building.is_active })
                                      }}
                                    />
                                    <div className="h-px bg-border-default mx-2" />
                                    {building.is_active ? (
                                      <MenuItem
                                        label={t('common.delete')}
                                        danger
                                        onClick={() => {
                                          close()
                                          setConfirmState({
                                            open: true,
                                            title: t('addressModals.confirmDeleteBuilding', { name: building.address }),
                                            description: t('addressModals.confirmDeleteBuilding', { name: building.address }),
                                            onConfirm: () => deleteBuilding.mutate(building.id),
                                          })
                                        }}
                                      />
                                    ) : (
                                      <MenuItem
                                        label={t('common.deletePermanently')}
                                        danger
                                        onClick={() => {
                                          close()
                                          setConfirmState({
                                            open: true,
                                            title: t('common.deletePermanently'),
                                            description: t('addressModals.confirmPurgeBuilding', { name: building.address }),
                                            onConfirm: () => purgeBuilding.mutate(building.id),
                                          })
                                        }}
                                      />
                                    )}
                                  </>
                                )}
                              </ActionMenu>
                            </div>

                            {/* Details */}
                            <div className="text-[13px] text-text-secondary mb-2.5 flex gap-3">
                              <span>{t('addresses.entrance', { count: building.entrance_count })}</span>
                              <span>{t('addresses.floor', { count: building.floor_count })}</span>
                            </div>

                            {/* Footer */}
                            <div className="flex items-center gap-2 mt-1">
                              <span className="bg-amber/[.13] text-amber rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
                                {t('addresses.apartment', { count: building.apartments_count })}
                              </span>
                              {!building.is_active && (
                                <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  )}

                  {/* Apartments grid */}
                  {level === 'apartments' && (
                    <>
                      {/* Bulk create button */}
                      <div className="flex justify-end">
                        <Button variant="outline" onClick={() => setShowBulkCreate(true)}>
                          {t('addresses.bulkCreate')}
                        </Button>
                      </div>

                      {filteredApartments.length === 0 ? (
                        <EmptyState icon={'\u{1F3E0}'} title={t('addresses.noApartmentsFound')} subtitle={t('addresses.noApartmentsFoundDesc')} />
                      ) : (
                        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
                          {filteredApartments.map(apt => (
                            <div
                              key={apt.id}
                              className="bg-bg-card border border-border-default rounded-default p-4 cursor-pointer transition-all relative hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]"
                              onClick={() => setProfileApartmentId(apt.id)}
                            >
                              {/* Header */}
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <div className={cn('w-2 h-2 rounded-full shrink-0', apt.is_active ? 'bg-emerald' : 'bg-text-muted')} />
                                  <div className="font-[family-name:var(--font-mono)] font-bold text-xl text-text-primary">
                                    {apt.apartment_number}
                                  </div>
                                </div>
                                <ActionMenu>
                                  {(close) => (
                                    <>
                                      <MenuItem label={t('common.edit')} onClick={() => { close(); setEditingApartment(apt) }} />
                                      <MenuItem
                                        label={apt.is_active ? t('addresses.deactivate') : t('addresses.activate')}
                                        onClick={() => {
                                          close()
                                          updateApartment.mutate({ id: apt.id, is_active: !apt.is_active })
                                        }}
                                      />
                                      <div className="h-px bg-border-default mx-2" />
                                      <MenuItem
                                        label={t('common.delete')}
                                        danger
                                        onClick={() => {
                                          close()
                                          setConfirmState({
                                            open: true,
                                            title: t('addressModals.confirmDeleteApartment', { name: apt.apartment_number }),
                                            description: t('addressModals.confirmDeleteApartment', { name: apt.apartment_number }),
                                            onConfirm: () => deleteApartment.mutate(apt.id),
                                          })
                                        }}
                                      />
                                    </>
                                  )}
                                </ActionMenu>
                              </div>

                              {/* Details */}
                              <div className="text-xs text-text-secondary flex flex-col gap-0.5">
                                {apt.building_address && (
                                  <div className="text-text-muted">{apt.building_address}</div>
                                )}
                                <div className="flex gap-3">
                                  {apt.floor != null && <span>{t('addresses.floor')}: {apt.floor}</span>}
                                  {apt.entrance != null && <span>{t('addresses.entrance')}: {apt.entrance}</span>}
                                  {apt.area != null && <span>{apt.area} м&sup2;</span>}
                                </div>
                              </div>

                              {/* Footer */}
                              <div className="flex items-center gap-2 mt-2.5">
                                <span className="bg-violet/[.13] text-violet rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">
                                  {t('addresses.resident', { count: apt.residents_count })}
                                </span>
                                {!apt.is_active && (
                                  <span className="bg-text-muted/[.13] text-text-muted rounded-xl px-2 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)]">{t('addresses.inactive')}</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </>
              ) : (
                <>
                {level === 'apartments' && (
                  <div className="flex justify-end">
                    <Button variant="outline" onClick={() => setShowBulkCreate(true)}>
                      {t('addresses.bulkCreate')}
                    </Button>
                  </div>
                )}
                <AddressTable
                  level={level}
                  yards={level === 'yards' ? filteredYards : undefined}
                  buildings={level === 'buildings' ? filteredBuildings : undefined}
                  apartments={level === 'apartments' ? filteredApartments : undefined}
                  onYardClick={handleYardClick}
                  onBuildingClick={handleBuildingClick}
                  onApartmentClick={(apt) => setProfileApartmentId(apt.id)}
                  onEditYard={(yard) => setEditingYard(yard)}
                  onEditBuilding={(building) => setEditingBuilding(building)}
                  onEditApartment={(apt) => setEditingApartment(apt)}
                  onToggleYard={(id, active) => updateYard.mutate({ id, is_active: active })}
                  onToggleBuilding={(id, active) => updateBuilding.mutate({ id, is_active: active })}
                  onToggleApartment={(id, active) => updateApartment.mutate({ id, is_active: active })}
                  onDeleteYard={(id) => deleteYard.mutate(id)}
                  onDeleteBuilding={(id) => deleteBuilding.mutate(id)}
                  onPurgeBuilding={(id) => purgeBuilding.mutate(id)}
                  onDeleteApartment={(id) => deleteApartment.mutate(id)}
                />
                </>
              )}
            </>
          )}
        </>
      )}

      {/* Yard edit modal */}
      {editingYard && (
        <YardFormModal yard={editingYard} onClose={() => setEditingYard(null)} />
      )}

      {/* Building edit modal */}
      {editingBuilding && (
        <BuildingFormModal
          building={editingBuilding}
          yardId={editingBuilding.yard_id}
          yards={yards}
          onClose={() => setEditingBuilding(null)}
        />
      )}

      {/* Unified create object modal */}
      <AddObjectModal
        open={addObjectOpen}
        onClose={() => setAddObjectOpen(false)}
        yards={yards}
        preselectedYardId={level === 'buildings' ? selectedYard?.id : undefined}
      />

      {/* Apartment modals */}
      {editingApartment && (
        <ApartmentFormModal
          apartment={editingApartment}
          buildingId={editingApartment.building_id}
          onClose={() => setEditingApartment(null)}
        />
      )}
      {showCreateModal && level === 'apartments' && selectedBuilding && (
        <ApartmentFormModal
          buildingId={selectedBuilding.id}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {showBulkCreate && selectedBuilding && (
        <BulkCreateModal
          buildingId={selectedBuilding.id}
          buildingAddress={selectedBuilding.address}
          onClose={() => setShowBulkCreate(false)}
        />
      )}

      {profileApartmentId !== null && (
        <ApartmentProfileModal
          apartmentId={profileApartmentId}
          onClose={() => setProfileApartmentId(null)}
          onEdit={() => {
            const apt = apartments?.find(a => a.id === profileApartmentId)
            if (apt) {
              setProfileApartmentId(null)
              setEditingApartment(apt)
            }
          }}
        />
      )}

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState(prev => ({ ...prev, open }))}
        title={confirmState.title}
        description={confirmState.description}
        confirmLabel={t('common.delete')}
        onConfirm={confirmState.onConfirm}
        variant="danger"
      />
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────
