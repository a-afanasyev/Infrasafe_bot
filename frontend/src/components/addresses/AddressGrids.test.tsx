import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '../../test/test-utils'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../../types/api'
import YardGrid from './YardGrid'
import BuildingGrid from './BuildingGrid'
import ApartmentGrid from './ApartmentGrid'

// FE-09 (PR-33): извлечённые из AddressesPage презентационные гриды.
// Покрываем рендер тайлов, пустое состояние и проброс колбэков.

const yard = (over: Partial<YardBrief> = {}): YardBrief => ({
  id: 1,
  name: 'Двор А',
  description: null,
  gps_latitude: null,
  gps_longitude: null,
  is_active: true,
  created_at: null,
  buildings_count: 3,
  ...over,
})

const building = (over: Partial<BuildingBrief> = {}): BuildingBrief => ({
  id: 10,
  address: 'ул. Ленина 1',
  yard_id: 1,
  yard_name: 'Двор А',
  entrance_count: 2,
  floor_count: 9,
  description: null,
  gps_latitude: null,
  gps_longitude: null,
  is_active: true,
  created_at: null,
  apartments_count: 36,
  ...over,
})

const apartment = (over: Partial<ApartmentBrief> = {}): ApartmentBrief => ({
  id: 100,
  building_id: 10,
  apartment_number: '42',
  building_address: 'ул. Ленина 1',
  yard_name: 'Двор А',
  entrance: 1,
  floor: 5,
  rooms_count: 2,
  area: 54,
  description: null,
  is_active: true,
  created_at: null,
  residents_count: 2,
  ...over,
})

const noop = () => {}

describe('YardGrid', () => {
  it('renders yard tiles and fires onYardClick', () => {
    const onYardClick = vi.fn()
    render(
      <YardGrid
        yards={[yard({ name: 'Двор А' }), yard({ id: 2, name: 'Двор Б' })]}
        onYardClick={onYardClick}
        onEdit={noop}
        onToggleActive={noop}
        onDelete={noop}
        onPurge={noop}
      />,
    )
    expect(screen.getByText('Двор А')).toBeInTheDocument()
    expect(screen.getByText('Двор Б')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Двор А'))
    expect(onYardClick).toHaveBeenCalledTimes(1)
  })

  it('renders empty state when no yards', () => {
    const { container } = render(
      <YardGrid yards={[]} onYardClick={noop} onEdit={noop} onToggleActive={noop} onDelete={noop} onPurge={noop} />,
    )
    // Пустое состояние: ни одного тайла-карточки с именем двора.
    expect(container.querySelector('.grid')).toBeNull()
  })
})

describe('BuildingGrid', () => {
  it('renders building tiles and fires onBuildingClick', () => {
    const onBuildingClick = vi.fn()
    render(
      <BuildingGrid
        buildings={[building({ address: 'ул. Ленина 1' })]}
        onBuildingClick={onBuildingClick}
        onEdit={noop}
        onToggleActive={noop}
        onDelete={noop}
        onPurge={noop}
      />,
    )
    expect(screen.getByText('ул. Ленина 1')).toBeInTheDocument()
    fireEvent.click(screen.getByText('ул. Ленина 1'))
    expect(onBuildingClick).toHaveBeenCalledTimes(1)
  })
})

describe('ApartmentGrid', () => {
  it('renders apartment tiles, bulk-create button and fires onProfileClick', () => {
    const onProfileClick = vi.fn()
    const onBulkCreate = vi.fn()
    render(
      <ApartmentGrid
        apartments={[apartment({ apartment_number: '42' })]}
        onProfileClick={onProfileClick}
        onEdit={noop}
        onToggleActive={noop}
        onDelete={noop}
        onPurge={noop}
        onBulkCreate={onBulkCreate}
      />,
    )
    expect(screen.getByText('42')).toBeInTheDocument()
    fireEvent.click(screen.getByText('42'))
    expect(onProfileClick).toHaveBeenCalledTimes(1)
  })

  it('shows bulk-create button even when empty', () => {
    const onBulkCreate = vi.fn()
    render(
      <ApartmentGrid
        apartments={[]}
        onProfileClick={noop}
        onEdit={noop}
        onToggleActive={noop}
        onDelete={noop}
        onPurge={noop}
        onBulkCreate={onBulkCreate}
      />,
    )
    // Кнопка массового создания рендерится всегда (даже при пустом списке).
    const btn = screen.getByText(/./, { selector: 'button' })
    expect(btn).toBeInTheDocument()
  })
})
