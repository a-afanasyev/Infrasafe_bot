import { describe, it, expect, vi } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { render, screen } from '@/test/test-utils'
import type { AddressStats, YardBrief, BuildingBrief } from '@/types/api'
import AddressStatsBar from './AddressStatsBar'
import AddressBreadcrumb from './AddressBreadcrumb'
import AddressTabBar from './AddressTabBar'

// TEST-068 Phase 3: presentational компоненты адресов (вынесены в PR-33/FE-09).
// Проверяем форматы значений и проброс колбэков — поведение, не разметку.

const STATS: AddressStats = {
  yards_total: 5,
  yards_active: 3,
  buildings_total: 6,
  buildings_active: 6,
  apartments_total: 120,
  apartments_active: 100,
  residents_approved: 2,
  residents_pending: 1,
}

const YARD: YardBrief = {
  id: 1, name: 'Двор-1', description: null, gps_latitude: null,
  gps_longitude: null, is_active: true, created_at: null, buildings_count: 6,
}

const BUILDING: BuildingBrief = {
  id: 10, address: 'Дом 14V', yard_id: 1, yard_name: 'Двор-1', entrance_count: 2,
  floor_count: 9, description: null, gps_latitude: null, gps_longitude: null,
  is_active: true, created_at: null, apartments_count: 54,
}

describe('AddressStatsBar', () => {
  const noop = () => {}

  it('renders active/total values for each tile', () => {
    render(
      <AddressStatsBar stats={STATS} onYardsClick={noop} onBuildingsClick={noop}
        onApartmentsClick={noop} onResidentsClick={noop} />,
    )
    expect(screen.getByText('3/5')).toBeInTheDocument()      // yards
    expect(screen.getByText('6/6')).toBeInTheDocument()      // buildings
    expect(screen.getByText('100/120')).toBeInTheDocument()  // apartments
    expect(screen.getByText('2/3')).toBeInTheDocument()      // residents approved/(approved+pending)
  })

  it('renders dashes when stats are undefined', () => {
    render(
      <AddressStatsBar stats={undefined} onYardsClick={noop} onBuildingsClick={noop}
        onApartmentsClick={noop} onResidentsClick={noop} />,
    )
    expect(screen.getAllByText('-')).toHaveLength(4)
  })

  it('fires the matching callback when a tile is clicked', () => {
    const onYardsClick = vi.fn()
    const onResidentsClick = vi.fn()
    render(
      <AddressStatsBar stats={STATS} onYardsClick={onYardsClick} onBuildingsClick={() => {}}
        onApartmentsClick={() => {}} onResidentsClick={onResidentsClick} />,
    )
    fireEvent.click(screen.getByText('3/5'))
    fireEvent.click(screen.getByText('2/3'))
    expect(onYardsClick).toHaveBeenCalledTimes(1)
    expect(onResidentsClick).toHaveBeenCalledTimes(1)
  })
})

describe('AddressBreadcrumb', () => {
  const base = {
    yards: [YARD], filterYardId: null, filterBuildingId: null, filterBuildings: [],
    onFilterYardChange: () => {}, onFilterBuildingChange: () => {},
    goToYards: () => {}, goToBuildings: () => {},
  }

  it('shows the yard name and calls goToYards on the root crumb', () => {
    const goToYards = vi.fn()
    render(
      <AddressBreadcrumb {...base} level="buildings" selectedYard={YARD}
        selectedBuilding={null} goToYards={goToYards} />,
    )
    expect(screen.getByText('Двор-1')).toBeInTheDocument()
    // Корневая крошка «Дворов» (ключ addresses.stats.yards в ru.json) кликабельна.
    fireEvent.click(screen.getByText('Дворов'))
    expect(goToYards).toHaveBeenCalledTimes(1)
  })

  it('shows the building crumb at apartment level', () => {
    render(
      <AddressBreadcrumb {...base} level="apartments" selectedYard={YARD}
        selectedBuilding={BUILDING} />,
    )
    expect(screen.getByText('Дом 14V')).toBeInTheDocument()
  })

  it('all-buildings flat view exposes a yard filter select', () => {
    const onFilterYardChange = vi.fn()
    render(
      <AddressBreadcrumb {...base} level="all-buildings" selectedYard={null}
        selectedBuilding={null} onFilterYardChange={onFilterYardChange} />,
    )
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: '1' } })
    expect(onFilterYardChange).toHaveBeenCalledWith(1)
  })
})

describe('AddressTabBar', () => {
  const base = {
    view: 'directory' as const, onViewChange: () => {}, viewMode: 'tile' as const,
    onViewModeChange: () => {}, showInactive: false, onShowInactiveChange: () => {},
    moderationCount: 0,
  }

  it('appends the moderation count when > 0', () => {
    render(<AddressTabBar {...base} moderationCount={3} />)
    expect(screen.getByText(/\(3\)/)).toBeInTheDocument()
  })

  it('switches view on tab click', () => {
    const onViewChange = vi.fn()
    render(<AddressTabBar {...base} onViewChange={onViewChange} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[1]) // moderation tab
    expect(onViewChange).toHaveBeenCalledWith('moderation')
  })

  it('toggles show-inactive via the checkbox', () => {
    const onShowInactiveChange = vi.fn()
    render(<AddressTabBar {...base} onShowInactiveChange={onShowInactiveChange} />)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(onShowInactiveChange).toHaveBeenCalledWith(true)
  })

  it('hides the view-mode toggle outside the directory view', () => {
    const { rerender } = render(<AddressTabBar {...base} view="moderation" />)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    rerender(<AddressTabBar {...base} view="directory" />)
    expect(screen.getByRole('checkbox')).toBeInTheDocument()
  })
})
