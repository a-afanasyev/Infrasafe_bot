import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useAddressStats,
  useYards,
  useBuildings,
  useApartments,
  usePendingModeration,
  useDeleteYard,
  useDeleteBuilding,
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
import BulkCreateModal from '../components/addresses/BulkCreateModal'
import ModerationPanel from '../components/addresses/ModerationPanel'
import ApartmentProfileModal from '../components/addresses/ApartmentProfileModal'
import AddressTable from '../components/addresses/AddressTable'
import ConfirmDialog from '../components/shared/ConfirmDialog'

// ── Types ───────────────────────────────────────────────────────────

type View = 'directory' | 'moderation'
type Level = 'yards' | 'buildings' | 'apartments'

// ── Shared styles ───────────────────────────────────────────────────

const primaryBtnStyle: React.CSSProperties = {
  background: 'var(--accent)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: '13px',
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

const tabStyle = (active: boolean): React.CSSProperties => ({
  background: active ? 'var(--accent)' : 'var(--bg-card)',
  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
  borderRadius: 20,
  cursor: 'pointer',
  fontSize: '13px',
  color: active ? '#fff' : 'var(--text-secondary)',
  padding: '6px 16px',
  fontFamily: 'var(--font-display)',
  fontWeight: active ? 600 : 400,
  transition: 'all 0.15s',
})

const cardBaseStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '16px',
  cursor: 'pointer',
  transition: 'border-color 0.15s, box-shadow 0.15s',
  position: 'relative',
}

const menuBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: 'var(--text-muted)',
  fontSize: '18px',
  padding: '2px 6px',
  lineHeight: 1,
  borderRadius: 'var(--radius-sm)',
}

const menuDropdownStyle: React.CSSProperties = {
  position: 'absolute',
  top: '100%',
  right: 0,
  marginTop: 4,
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
  zIndex: 10,
  minWidth: 160,
  overflow: 'hidden',
}

const menuItemStyle: React.CSSProperties = {
  width: '100%',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  padding: '8px 14px',
  textAlign: 'left',
  fontSize: '13px',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-display)',
  display: 'block',
}

const menuItemDangerStyle: React.CSSProperties = {
  ...menuItemStyle,
  color: 'var(--red, #ef4444)',
}

const badgeStyle = (color: string): React.CSSProperties => ({
  background: color + '22',
  color,
  borderRadius: 12,
  padding: '2px 8px',
  fontSize: '11px',
  fontWeight: 600,
  fontFamily: 'var(--font-mono)',
})

const toggleBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: '16px',
  padding: '4px 10px',
  lineHeight: 1,
  transition: 'all 0.15s',
}

const dotStyle = (active: boolean): React.CSSProperties => ({
  width: 8,
  height: 8,
  borderRadius: '50%',
  background: active ? 'var(--emerald, #10b981)' : 'var(--text-muted)',
  flexShrink: 0,
})

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
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        style={menuBtnStyle}
        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
      >
        ...
      </button>
      {open && (
        <div style={menuDropdownStyle}>
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
      style={danger ? menuItemDangerStyle : menuItemStyle}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-card)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'none')}
    >
      {label}
    </button>
  )
}

// ── Main component ──────────────────────────────────────────────────

export default function AddressesPage() {
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

  // Mutations
  const deleteYard = useDeleteYard()
  const deleteBuilding = useDeleteBuilding()
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
    setLevel('apartments')
    setSelectedBuilding(building)
  }, [])

  // Search filter
  const filterBySearch = useCallback((name: string) => {
    if (!searchQuery) return true
    return name.toLowerCase().includes(searchQuery.toLowerCase())
  }, [searchQuery])

  // Topbar actions
  const addLabel = level === 'yards' ? 'двор' : level === 'buildings' ? 'здание' : 'квартиру'

  const actionsNode = useMemo(() => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <input
        type="text"
        placeholder="Поиск..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '6px 12px',
          fontSize: '13px',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-display)',
          outline: 'none',
          width: '200px',
        }}
      />
      <button
        onClick={() => setShowCreateModal(true)}
        style={primaryBtnStyle}
      >
        + Добавить {addLabel}
      </button>
    </div>
  ), [searchQuery, addLabel])

  useEffect(() => {
    setActions(actionsNode)
    return clearActions
  }, [setActions, clearActions, actionsNode])

  // Stats
  const STATS = [
    {
      label: 'Дворы',
      value: stats ? `${stats.yards_active}/${stats.yards_total}` : '-',
      iconBg: 'var(--blue)',
      icon: '\u{1F3D8}',
      onClick: () => { setView('directory'); goToYards() },
    },
    {
      label: 'Здания',
      value: stats?.buildings_total ?? '-',
      iconBg: 'var(--emerald)',
      icon: '\u{1F3E2}',
      onClick: () => { setView('directory'); goToYards() },
    },
    {
      label: 'Квартиры',
      value: stats?.apartments_total ?? '-',
      iconBg: 'var(--amber)',
      icon: '\u{1F3E0}',
      onClick: () => { setView('directory'); goToYards() },
    },
    {
      label: 'Жители',
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
    (level === 'apartments' && apartmentsLoading)

  // Filtered data
  const filteredYards = yards.filter(y => filterBySearch(y.name))
  const filteredBuildings = buildings.filter(b => filterBySearch(b.address))
  const filteredApartments = apartments.filter(a => filterBySearch(a.apartment_number))

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Stats bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {STATS.map(card => (
          <div
            key={card.label}
            onClick={card.onClick}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '16px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              cursor: 'pointer',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
          >
            <div style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: card.iconBg + '22',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '22px',
              flexShrink: 0,
            }}>
              {card.icon}
            </div>
            <div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '22px',
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}>
                {card.value}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
                {card.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button onClick={() => setView('directory')} style={tabStyle(view === 'directory')}>
          Справочник
        </button>
        <button onClick={() => setView('moderation')} style={tabStyle(view === 'moderation')}>
          Модерация{moderationItems.length > 0 ? ` (${moderationItems.length})` : ''}
        </button>

        <div style={{ flex: 1 }} />

        {/* View toggle */}
        {view === 'directory' && (
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => setViewMode('tile')}
              style={{
                ...toggleBtnStyle,
                background: viewMode === 'tile' ? 'var(--accent)' : 'transparent',
                border: viewMode === 'tile' ? '1px solid var(--accent)' : '1px solid var(--border)',
                color: viewMode === 'tile' ? '#fff' : 'var(--text-muted)',
              }}
              title="Плитка"
            >{'\u229E'}</button>
            <button
              onClick={() => setViewMode('table')}
              style={{
                ...toggleBtnStyle,
                background: viewMode === 'table' ? 'var(--accent)' : 'transparent',
                border: viewMode === 'table' ? '1px solid var(--accent)' : '1px solid var(--border)',
                color: viewMode === 'table' ? '#fff' : 'var(--text-muted)',
              }}
              title="Таблица"
            >{'\u2630'}</button>
          </div>
        )}

        {/* Show inactive toggle */}
        {view === 'directory' && (
          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '12px',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-display)',
          }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Показать неактивные
          </label>
        )}
      </div>

      {/* Content area */}
      {view === 'moderation' ? (
        <ModerationPanel />
      ) : (
        <>
          {/* Breadcrumb */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 13,
            fontFamily: 'var(--font-display)',
          }}>
            <span
              onClick={goToYards}
              style={{
                cursor: 'pointer',
                color: level === 'yards' ? 'var(--text-primary)' : 'var(--accent)',
                fontWeight: level === 'yards' ? 600 : 400,
              }}
            >
              Дворы
            </span>
            {selectedYard && (
              <>
                <span style={{ color: 'var(--text-muted)' }}>&rsaquo;</span>
                <span
                  onClick={goToBuildings}
                  style={{
                    cursor: level === 'buildings' ? 'default' : 'pointer',
                    color: level === 'buildings' ? 'var(--text-primary)' : 'var(--accent)',
                    fontWeight: level === 'buildings' ? 600 : 400,
                  }}
                >
                  {selectedYard.name}
                </span>
              </>
            )}
            {selectedBuilding && (
              <>
                <span style={{ color: 'var(--text-muted)' }}>&rsaquo;</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                  {selectedBuilding.address}
                </span>
              </>
            )}
          </div>

          {isLoading ? (
            <LoadingSpinner />
          ) : (
            <>
              {viewMode === 'tile' ? (
                <>
                  {/* Yards grid */}
                  {level === 'yards' && (
                    filteredYards.length === 0 ? (
                      <EmptyState icon="\u{1F3D8}" title="Дворы не найдены" subtitle="Добавьте первый двор" />
                    ) : (
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                        gap: '16px',
                      }}>
                        {filteredYards.map(yard => (
                          <div
                            key={yard.id}
                            onClick={() => handleYardClick(yard)}
                            style={cardBaseStyle}
                            onMouseEnter={e => {
                              e.currentTarget.style.borderColor = 'var(--accent)'
                              e.currentTarget.style.boxShadow = '0 0 0 1px var(--accent)'
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.borderColor = 'var(--border)'
                              e.currentTarget.style.boxShadow = 'none'
                            }}
                          >
                            {/* Header */}
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                                <div style={dotStyle(yard.is_active)} />
                                <div style={{
                                  fontFamily: 'var(--font-display)',
                                  fontWeight: 600,
                                  fontSize: '15px',
                                  color: 'var(--text-primary)',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}>
                                  {yard.name}
                                </div>
                              </div>
                              <ActionMenu>
                                {(close) => (
                                  <>
                                    <MenuItem label="Редактировать" onClick={() => { close(); setEditingYard(yard) }} />
                                    <MenuItem
                                      label={yard.is_active ? 'Деактивировать' : 'Активировать'}
                                      onClick={() => {
                                        close()
                                        updateYard.mutate({ id: yard.id, is_active: !yard.is_active })
                                      }}
                                    />
                                    <div style={{ height: 1, background: 'var(--border)', margin: '0 8px' }} />
                                    <MenuItem
                                      label="Удалить"
                                      danger
                                      onClick={() => {
                                        close()
                                        setConfirmState({
                                          open: true,
                                          title: 'Удалить двор',
                                          description: `Удалить двор "${yard.name}"? Это действие нельзя отменить.`,
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
                              <div style={{
                                fontSize: '13px',
                                color: 'var(--text-secondary)',
                                marginBottom: 10,
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                                lineHeight: '1.4',
                              }}>
                                {yard.description}
                              </div>
                            )}

                            {/* Footer */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                              <span style={badgeStyle('var(--blue)')}>
                                {yard.buildings_count} {pluralize(yard.buildings_count, 'здание', 'здания', 'зданий')}
                              </span>
                              {!yard.is_active && (
                                <span style={badgeStyle('var(--text-muted)')}>неактивен</span>
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
                      <EmptyState icon="\u{1F3E2}" title="Здания не найдены" subtitle="Добавьте первое здание" />
                    ) : (
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                        gap: '16px',
                      }}>
                        {filteredBuildings.map(building => (
                          <div
                            key={building.id}
                            onClick={() => handleBuildingClick(building)}
                            style={cardBaseStyle}
                            onMouseEnter={e => {
                              e.currentTarget.style.borderColor = 'var(--accent)'
                              e.currentTarget.style.boxShadow = '0 0 0 1px var(--accent)'
                            }}
                            onMouseLeave={e => {
                              e.currentTarget.style.borderColor = 'var(--border)'
                              e.currentTarget.style.boxShadow = 'none'
                            }}
                          >
                            {/* Header */}
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                                <div style={dotStyle(building.is_active)} />
                                <div style={{
                                  fontFamily: 'var(--font-display)',
                                  fontWeight: 600,
                                  fontSize: '15px',
                                  color: 'var(--text-primary)',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}>
                                  {building.address}
                                </div>
                              </div>
                              <ActionMenu>
                                {(close) => (
                                  <>
                                    <MenuItem label="Редактировать" onClick={() => { close(); setEditingBuilding(building) }} />
                                    <MenuItem
                                      label={building.is_active ? 'Деактивировать' : 'Активировать'}
                                      onClick={() => {
                                        close()
                                        updateBuilding.mutate({ id: building.id, is_active: !building.is_active })
                                      }}
                                    />
                                    <div style={{ height: 1, background: 'var(--border)', margin: '0 8px' }} />
                                    <MenuItem
                                      label="Удалить"
                                      danger
                                      onClick={() => {
                                        close()
                                        setConfirmState({
                                          open: true,
                                          title: 'Удалить здание',
                                          description: `Удалить здание "${building.address}"? Это действие нельзя отменить.`,
                                          onConfirm: () => deleteBuilding.mutate(building.id),
                                        })
                                      }}
                                    />
                                  </>
                                )}
                              </ActionMenu>
                            </div>

                            {/* Details */}
                            <div style={{
                              fontSize: '13px',
                              color: 'var(--text-secondary)',
                              marginBottom: 10,
                              display: 'flex',
                              gap: 12,
                            }}>
                              <span>{building.entrance_count} {pluralize(building.entrance_count, 'подъезд', 'подъезда', 'подъездов')}</span>
                              <span>{building.floor_count} {pluralize(building.floor_count, 'этаж', 'этажа', 'этажей')}</span>
                            </div>

                            {/* Footer */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                              <span style={badgeStyle('var(--amber)')}>
                                {building.apartments_count} {pluralize(building.apartments_count, 'квартира', 'квартиры', 'квартир')}
                              </span>
                              {!building.is_active && (
                                <span style={badgeStyle('var(--text-muted)')}>неактивно</span>
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
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => setShowBulkCreate(true)}
                          style={{
                            ...primaryBtnStyle,
                            background: 'var(--bg-card)',
                            color: 'var(--accent)',
                            border: '1px solid var(--accent)',
                          }}
                        >
                          Автозаполнение
                        </button>
                      </div>

                      {filteredApartments.length === 0 ? (
                        <EmptyState icon="\u{1F3E0}" title="Квартиры не найдены" subtitle="Добавьте квартиры вручную или используйте автозаполнение" />
                      ) : (
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                          gap: '16px',
                        }}>
                          {filteredApartments.map(apt => (
                            <div
                              key={apt.id}
                              style={{ ...cardBaseStyle, cursor: 'pointer' }}
                              onClick={() => setProfileApartmentId(apt.id)}
                              onMouseEnter={e => {
                                e.currentTarget.style.borderColor = 'var(--accent)'
                                e.currentTarget.style.boxShadow = '0 0 0 1px var(--accent)'
                              }}
                              onMouseLeave={e => {
                                e.currentTarget.style.borderColor = 'var(--border)'
                                e.currentTarget.style.boxShadow = 'none'
                              }}
                            >
                              {/* Header */}
                              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                  <div style={dotStyle(apt.is_active)} />
                                  <div style={{
                                    fontFamily: 'var(--font-mono)',
                                    fontWeight: 700,
                                    fontSize: '20px',
                                    color: 'var(--text-primary)',
                                  }}>
                                    {apt.apartment_number}
                                  </div>
                                </div>
                                <ActionMenu>
                                  {(close) => (
                                    <>
                                      <MenuItem label="Редактировать" onClick={() => { close(); setEditingApartment(apt) }} />
                                      <MenuItem
                                        label={apt.is_active ? 'Деактивировать' : 'Активировать'}
                                        onClick={() => {
                                          close()
                                          updateApartment.mutate({ id: apt.id, is_active: !apt.is_active })
                                        }}
                                      />
                                      <div style={{ height: 1, background: 'var(--border)', margin: '0 8px' }} />
                                      <MenuItem
                                        label="Удалить"
                                        danger
                                        onClick={() => {
                                          close()
                                          setConfirmState({
                                            open: true,
                                            title: 'Удалить квартиру',
                                            description: `Удалить квартиру ${apt.apartment_number}? Это действие нельзя отменить.`,
                                            onConfirm: () => deleteApartment.mutate(apt.id),
                                          })
                                        }}
                                      />
                                    </>
                                  )}
                                </ActionMenu>
                              </div>

                              {/* Details */}
                              <div style={{
                                fontSize: '12px',
                                color: 'var(--text-secondary)',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: 3,
                              }}>
                                {apt.building_address && (
                                  <div style={{ color: 'var(--text-muted)' }}>{apt.building_address}</div>
                                )}
                                <div style={{ display: 'flex', gap: 12 }}>
                                  {apt.floor != null && <span>Этаж: {apt.floor}</span>}
                                  {apt.entrance != null && <span>Подъезд: {apt.entrance}</span>}
                                  {apt.area != null && <span>{apt.area} м&sup2;</span>}
                                </div>
                              </div>

                              {/* Footer */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                                <span style={badgeStyle('var(--violet)')}>
                                  {apt.residents_count} {pluralize(apt.residents_count, 'житель', 'жителя', 'жителей')}
                                </span>
                                {!apt.is_active && (
                                  <span style={badgeStyle('var(--text-muted)')}>неактивна</span>
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
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => setShowBulkCreate(true)}
                      style={{
                        ...primaryBtnStyle,
                        background: 'var(--bg-card)',
                        color: 'var(--accent)',
                        border: '1px solid var(--accent)',
                      }}
                    >
                      Автозаполнение
                    </button>
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
                  onDeleteApartment={(id) => deleteApartment.mutate(id)}
                />
                </>
              )}
            </>
          )}
        </>
      )}

      {/* Yard modals */}
      {editingYard && (
        <YardFormModal yard={editingYard} onClose={() => setEditingYard(null)} />
      )}
      {showCreateModal && level === 'yards' && (
        <YardFormModal onClose={() => setShowCreateModal(false)} />
      )}

      {/* Building modals */}
      {editingBuilding && selectedYard && (
        <BuildingFormModal
          building={editingBuilding}
          yardId={selectedYard.id}
          yards={yards}
          onClose={() => setEditingBuilding(null)}
        />
      )}
      {showCreateModal && level === 'buildings' && selectedYard && (
        <BuildingFormModal
          yardId={selectedYard.id}
          yards={yards}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {/* Apartment modals */}
      {editingApartment && selectedBuilding && (
        <ApartmentFormModal
          apartment={editingApartment}
          buildingId={selectedBuilding.id}
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
        confirmLabel="Удалить"
        onConfirm={confirmState.onConfirm}
        variant="danger"
      />
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────

function pluralize(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100
  const lastDigit = abs % 10
  if (abs > 10 && abs < 20) return many
  if (lastDigit > 1 && lastDigit < 5) return few
  if (lastDigit === 1) return one
  return many
}
