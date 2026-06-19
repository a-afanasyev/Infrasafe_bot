import { useEffect, useMemo, useState, useCallback } from 'react'
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
  usePurgeYard,
  useDeleteBuilding,
  usePurgeBuilding,
  useDeleteApartment,
  usePurgeApartment,
  useUpdateYard,
  useUpdateBuilding,
  useUpdateApartment,
  useAddressesWebSocket,
} from '../hooks/useAddresses'
import type {
  YardBrief,
  BuildingBrief,
  ApartmentBrief,
} from '../types/api'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import ModerationPanel from '../components/addresses/ModerationPanel'
import AddressTable from '../components/addresses/AddressTable'
import AddressStatsBar from '../components/addresses/AddressStatsBar'
import YardGrid from '../components/addresses/YardGrid'
import BuildingGrid from '../components/addresses/BuildingGrid'
import ApartmentGrid from '../components/addresses/ApartmentGrid'
import AddressTabBar from '../components/addresses/AddressTabBar'
import AddressBreadcrumb from '../components/addresses/AddressBreadcrumb'
import AddressModals, { type ConfirmState } from '../components/addresses/AddressModals'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// ── Types ───────────────────────────────────────────────────────────

type View = 'directory' | 'moderation'
type Level = 'yards' | 'buildings' | 'apartments' | 'all-buildings' | 'all-apartments'

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
  const [confirmState, setConfirmState] = useState<ConfirmState>({ open: false, title: '', description: '', onConfirm: () => {} })

  useEffect(() => {
    try { localStorage.setItem('addresses_view_mode', viewMode) } catch { /* localStorage unavailable */ }
  }, [viewMode])

  // Queries
  useAddressesWebSocket()

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
  const purgeYard = usePurgeYard()
  const deleteBuilding = useDeleteBuilding()
  const purgeBuilding = usePurgeBuilding()
  const deleteApartment = useDeleteApartment()
  const purgeApartment = usePurgeApartment()
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
  ), [searchQuery, level, t])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  // Stats-bar click handlers (вынесены в AddressStatsBar)
  const onStatsYards = () => { setView('directory'); goToYards() }
  const onStatsBuildings = () => { setView('directory'); setLevel('all-buildings'); setFilterYardId(null); setSelectedYard(null); setSelectedBuilding(null) }
  const onStatsApartments = () => { setView('directory'); setLevel('all-apartments'); setFilterYardId(null); setFilterBuildingId(null); setSelectedYard(null); setSelectedBuilding(null) }
  const onStatsResidents = () => { setView('moderation') }

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
      <AddressStatsBar
        stats={stats}
        onYardsClick={onStatsYards}
        onBuildingsClick={onStatsBuildings}
        onApartmentsClick={onStatsApartments}
        onResidentsClick={onStatsResidents}
      />

      {/* Tab bar */}
      <AddressTabBar
        view={view}
        onViewChange={setView}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showInactive={showInactive}
        onShowInactiveChange={setShowInactive}
        moderationCount={moderationItems.length}
      />

      {/* Content area */}
      {view === 'moderation' ? (
        <ModerationPanel />
      ) : (
        <>
          {/* Breadcrumb / Title */}
          <AddressBreadcrumb
            level={level}
            selectedYard={selectedYard}
            selectedBuilding={selectedBuilding}
            yards={yards}
            filterYardId={filterYardId}
            filterBuildingId={filterBuildingId}
            filterBuildings={filterBuildings}
            onFilterYardChange={setFilterYardId}
            onFilterBuildingChange={setFilterBuildingId}
            goToYards={goToYards}
            goToBuildings={goToBuildings}
          />
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
              onPurgeApartment={(id) => purgeApartment.mutate(id)}
            />
          ) : (
            <>
              {viewMode === 'tile' ? (
                <>
                  {level === 'yards' && (
                    <YardGrid
                      yards={filteredYards}
                      onYardClick={handleYardClick}
                      onEdit={(yard) => setEditingYard(yard)}
                      onToggleActive={(yard) => updateYard.mutate({ id: yard.id, is_active: !yard.is_active })}
                      onDelete={(yard) => setConfirmState({ open: true, title: t('addressModals.deleteYardTitle'), description: t('addressModals.confirmDeleteYard', { name: yard.name }), onConfirm: () => deleteYard.mutate(yard.id) })}
                      onPurge={(yard) => setConfirmState({ open: true, title: t('common.deletePermanently'), description: t('addressModals.confirmPurgeYard', { name: yard.name }), onConfirm: () => purgeYard.mutate(yard.id) })}
                    />
                  )}
                  {level === 'buildings' && (
                    <BuildingGrid
                      buildings={filteredBuildings}
                      onBuildingClick={handleBuildingClick}
                      onEdit={(building) => setEditingBuilding(building)}
                      onToggleActive={(building) => updateBuilding.mutate({ id: building.id, is_active: !building.is_active })}
                      onDelete={(building) => setConfirmState({ open: true, title: t('addressModals.deleteBuildingTitle'), description: t('addressModals.confirmDeleteBuilding', { name: building.address }), onConfirm: () => deleteBuilding.mutate(building.id) })}
                      onPurge={(building) => setConfirmState({ open: true, title: t('common.deletePermanently'), description: t('addressModals.confirmPurgeBuilding', { name: building.address }), onConfirm: () => purgeBuilding.mutate(building.id) })}
                    />
                  )}
                  {level === 'apartments' && (
                    <ApartmentGrid
                      apartments={filteredApartments}
                      onProfileClick={(apt) => setProfileApartmentId(apt.id)}
                      onEdit={(apt) => setEditingApartment(apt)}
                      onToggleActive={(apt) => updateApartment.mutate({ id: apt.id, is_active: !apt.is_active })}
                      onDelete={(apt) => setConfirmState({ open: true, title: t('addressModals.deleteApartmentTitle'), description: t('addressModals.confirmDeleteApartment', { name: apt.apartment_number }), onConfirm: () => deleteApartment.mutate(apt.id) })}
                      onPurge={(apt) => setConfirmState({ open: true, title: t('common.deletePermanently'), description: t('addressModals.confirmPurgeApartment', { name: apt.apartment_number }), onConfirm: () => purgeApartment.mutate(apt.id) })}
                      onBulkCreate={() => setShowBulkCreate(true)}
                    />
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
                  onPurgeYard={(id) => purgeYard.mutate(id)}
                  onDeleteBuilding={(id) => deleteBuilding.mutate(id)}
                  onPurgeBuilding={(id) => purgeBuilding.mutate(id)}
                  onDeleteApartment={(id) => deleteApartment.mutate(id)}
                  onPurgeApartment={(id) => purgeApartment.mutate(id)}
                />
                </>
              )}
            </>
          )}
        </>
      )}

      <AddressModals
        level={level}
        yards={yards}
        apartments={apartments}
        selectedYard={selectedYard}
        selectedBuilding={selectedBuilding}
        editingYard={editingYard}
        setEditingYard={setEditingYard}
        editingBuilding={editingBuilding}
        setEditingBuilding={setEditingBuilding}
        editingApartment={editingApartment}
        setEditingApartment={setEditingApartment}
        addObjectOpen={addObjectOpen}
        setAddObjectOpen={setAddObjectOpen}
        showCreateModal={showCreateModal}
        setShowCreateModal={setShowCreateModal}
        showBulkCreate={showBulkCreate}
        setShowBulkCreate={setShowBulkCreate}
        profileApartmentId={profileApartmentId}
        setProfileApartmentId={setProfileApartmentId}
        confirmState={confirmState}
        setConfirmState={setConfirmState}
      />
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────
