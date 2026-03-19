import { useState } from 'react'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../../types/api'
import EmptyState from '../shared/EmptyState'
import ConfirmDialog from '../shared/ConfirmDialog'

// -- Table configs --------------------------------------------------------

const YARD_HEADERS = ['Название', 'Описание', 'Зданий', 'Статус', 'Действия']
const YARD_COLS = '2fr 2.5fr 0.8fr 0.8fr 1fr'

const BUILDING_HEADERS = ['Адрес', 'Подъезды', 'Этажи', 'Квартир', 'Статус', 'Действия']
const BUILDING_COLS = '2.5fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr'

const APT_HEADERS = ['Номер', 'Подъезд', 'Этаж', 'Комнат', 'Площадь', 'Жителей', 'Статус', 'Действия']
const APT_COLS = '0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr'

// -- Styles ---------------------------------------------------------------

const containerStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  overflow: 'hidden',
}

const headerRowStyle: React.CSSProperties = {
  display: 'grid',
  background: 'var(--bg-surface)',
  borderBottom: '1px solid var(--border)',
  padding: '10px 16px',
  gap: '8px',
}

const headerCellStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  fontFamily: 'var(--font-display)',
}

const cellTextStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-primary)',
}

const mutedCellStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted)',
}

const actionBtnBase: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontSize: 11,
  fontFamily: 'var(--font-display)',
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
  onDeleteBuilding?: (id: number) => void
  onDeleteApartment?: (id: number) => void
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{
        display: 'inline-block',
        width: 8, height: 8, borderRadius: '50%',
        background: active ? 'var(--emerald)' : 'var(--text-muted)',
      }} />
      <span style={{ fontSize: 11, color: active ? 'var(--emerald)' : 'var(--text-muted)' }}>
        {active ? 'Активен' : 'Неактивен'}
      </span>
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
}: AddressTableProps) {
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null }>({ open: false, id: null })
  const items = yards ?? []

  if (items.length === 0) {
    return (
      <div style={containerStyle}>
        <EmptyState icon="🏘️" title="Нет дворов" subtitle="Создайте первый двор" />
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={{ ...headerRowStyle, gridTemplateColumns: YARD_COLS }}>
        {YARD_HEADERS.map(h => (
          <span key={h} style={headerCellStyle}>{h}</span>
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
            style={{
              display: 'grid',
              gridTemplateColumns: YARD_COLS,
              padding: '10px 16px',
              gap: '8px',
              borderBottom: isLast ? 'none' : '1px solid var(--border)',
              alignItems: 'center',
              background: isHovered ? 'var(--bg-surface)' : 'transparent',
              transition: 'background 0.1s',
              cursor: 'pointer',
            }}
          >
            <span style={{ ...cellTextStyle, fontWeight: 600 }}>{yard.name}</span>
            <span style={{
              ...mutedCellStyle,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {yard.description ?? '—'}
            </span>
            <span style={cellTextStyle}>{yard.buildings_count}</span>
            <StatusDot active={yard.is_active} />
            <div onClick={e => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button onClick={() => onEditYard?.(yard)} style={{ ...actionBtnBase, color: 'var(--accent)' }}>
                Редактировать
              </button>
              <button onClick={() => onToggleYard?.(yard.id, !yard.is_active)} style={{ ...actionBtnBase, color: 'var(--amber)' }}>
                {yard.is_active ? 'Деактивировать' : 'Активировать'}
              </button>
              <button
                onClick={() => setConfirmDelete({ open: true, id: yard.id })}
                style={{ ...actionBtnBase, color: 'var(--red)' }}
              >
                Удалить
              </button>
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title="Удалить двор"
        description="Удалить двор? Это действие нельзя отменить."
        confirmLabel="Удалить"
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteYard?.(confirmDelete.id)
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
}: AddressTableProps) {
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null }>({ open: false, id: null })
  const items = buildings ?? []

  if (items.length === 0) {
    return (
      <div style={containerStyle}>
        <EmptyState icon="🏢" title="Нет зданий" subtitle="Создайте первое здание" />
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={{ ...headerRowStyle, gridTemplateColumns: BUILDING_COLS }}>
        {BUILDING_HEADERS.map(h => (
          <span key={h} style={headerCellStyle}>{h}</span>
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
            style={{
              display: 'grid',
              gridTemplateColumns: BUILDING_COLS,
              padding: '10px 16px',
              gap: '8px',
              borderBottom: isLast ? 'none' : '1px solid var(--border)',
              alignItems: 'center',
              background: isHovered ? 'var(--bg-surface)' : 'transparent',
              transition: 'background 0.1s',
              cursor: 'pointer',
            }}
          >
            <span style={{ ...cellTextStyle, fontWeight: 600 }}>{bld.address}</span>
            <span style={cellTextStyle}>{bld.entrance_count}</span>
            <span style={cellTextStyle}>{bld.floor_count}</span>
            <span style={cellTextStyle}>{bld.apartments_count}</span>
            <StatusDot active={bld.is_active} />
            <div onClick={e => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button onClick={() => onEditBuilding?.(bld)} style={{ ...actionBtnBase, color: 'var(--accent)' }}>
                Редактировать
              </button>
              <button onClick={() => onToggleBuilding?.(bld.id, !bld.is_active)} style={{ ...actionBtnBase, color: 'var(--amber)' }}>
                {bld.is_active ? 'Деактивировать' : 'Активировать'}
              </button>
              <button
                onClick={() => setConfirmDelete({ open: true, id: bld.id })}
                style={{ ...actionBtnBase, color: 'var(--red)' }}
              >
                Удалить
              </button>
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title="Удалить здание"
        description="Удалить здание? Это действие нельзя отменить."
        confirmLabel="Удалить"
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteBuilding?.(confirmDelete.id)
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
}: AddressTableProps) {
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<{ open: boolean; id: number | null }>({ open: false, id: null })
  const items = apartments ?? []

  if (items.length === 0) {
    return (
      <div style={containerStyle}>
        <EmptyState icon="🚪" title="Нет квартир" subtitle="Создайте первую квартиру" />
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={{ ...headerRowStyle, gridTemplateColumns: APT_COLS }}>
        {APT_HEADERS.map(h => (
          <span key={h} style={headerCellStyle}>{h}</span>
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
            style={{
              display: 'grid',
              gridTemplateColumns: APT_COLS,
              padding: '10px 16px',
              gap: '8px',
              borderBottom: isLast ? 'none' : '1px solid var(--border)',
              alignItems: 'center',
              background: isHovered ? 'var(--bg-surface)' : 'transparent',
              transition: 'background 0.1s',
              cursor: 'pointer',
            }}
          >
            <span style={{ ...cellTextStyle, fontWeight: 600 }}>{apt.apartment_number}</span>
            <span style={mutedCellStyle}>{apt.entrance ?? '—'}</span>
            <span style={mutedCellStyle}>{apt.floor ?? '—'}</span>
            <span style={mutedCellStyle}>{apt.rooms_count ?? '—'}</span>
            <span style={mutedCellStyle}>{apt.area ? `${apt.area} м²` : '—'}</span>
            <span style={cellTextStyle}>{apt.residents_count}</span>
            <StatusDot active={apt.is_active} />
            <div onClick={e => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button onClick={() => onEditApartment?.(apt)} style={{ ...actionBtnBase, color: 'var(--accent)' }}>
                Редактировать
              </button>
              <button onClick={() => onToggleApartment?.(apt.id, !apt.is_active)} style={{ ...actionBtnBase, color: 'var(--amber)' }}>
                {apt.is_active ? 'Деактивировать' : 'Активировать'}
              </button>
              <button
                onClick={() => setConfirmDelete({ open: true, id: apt.id })}
                style={{ ...actionBtnBase, color: 'var(--red)' }}
              >
                Удалить
              </button>
            </div>
          </div>
        )
      })}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(prev => ({ ...prev, open }))}
        title="Удалить квартиру"
        description="Удалить квартиру? Это действие нельзя отменить."
        confirmLabel="Удалить"
        onConfirm={() => {
          if (confirmDelete.id !== null) onDeleteApartment?.(confirmDelete.id)
        }}
        variant="danger"
      />
    </div>
  )
}
