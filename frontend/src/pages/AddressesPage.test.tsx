import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import AddressesPage from './AddressesPage'
import type { YardBrief, BuildingBrief, ApartmentBrief } from '../types/api'

// TEST-068 Phase 3: страница была 0/120 строк. Данные — через мок хук-модуля
// (паттерн ResidentsPage.test): предмет — поведение экрана (уровни каталога,
// поиск, режимы, модерация), а не сетевой слой (он покрыт useAddresses.test).

const { queries, mutateSpy, buildingsSpy } = vi.hoisted(() => ({
  queries: {
    yards: [] as YardBrief[],
    buildings: [] as BuildingBrief[],
    apartments: [] as ApartmentBrief[],
    moderation: [] as unknown[],
  },
  mutateSpy: vi.fn(),
  buildingsSpy: vi.fn(),
}))

vi.mock('../hooks/useAddresses', () => {
  const mutation = () => ({ mutate: mutateSpy, isPending: false })
  return {
    useAddressStats: () => ({
      data: { yards: 2, buildings: 5, apartments: 40, residents: 90 },
    }),
    useYards: () => ({ data: queries.yards, isLoading: false }),
    useBuildings: (yardId: number | null) => {
      buildingsSpy(yardId)
      return { data: yardId === null ? [] : queries.buildings, isLoading: false }
    },
    useApartments: (buildingId: number | null) => ({
      data: buildingId === null ? [] : queries.apartments,
      isLoading: false,
    }),
    useAllBuildings: () => ({ data: queries.buildings, isLoading: false }),
    useAllApartments: () => ({ data: queries.apartments, isLoading: false }),
    usePendingModeration: () => ({ data: queries.moderation }),
    useDeleteYard: mutation,
    usePurgeYard: mutation,
    useDeleteBuilding: mutation,
    usePurgeBuilding: mutation,
    useDeleteApartment: mutation,
    usePurgeApartment: mutation,
    useUpdateYard: mutation,
    useUpdateBuilding: mutation,
    useUpdateApartment: mutation,
    useCreateYard: mutation,
    useCreateBuilding: mutation,
    useCreateApartment: mutation,
    useBulkCreateApartments: mutation,
    useApproveModeration: mutation,
    useRejectModeration: mutation,
    useAddressesWebSocket: () => undefined,
  }
})

function makeYard(over: Partial<YardBrief> = {}): YardBrief {
  return {
    id: 1, name: 'Двор Тестовый', description: null,
    gps_latitude: null, gps_longitude: null, is_active: true,
    created_at: null, buildings_count: 2, ...over,
  }
}

function makeBuilding(over: Partial<BuildingBrief> = {}): BuildingBrief {
  return {
    id: 10, address: 'ул. Кирпичная 5', yard_id: 1, yard_name: 'Двор Тестовый',
    entrance_count: 2, floor_count: 9, description: null,
    gps_latitude: null, gps_longitude: null, is_active: true,
    created_at: null, apartments_count: 20, ...over,
  }
}

function makeApartment(over: Partial<ApartmentBrief> = {}): ApartmentBrief {
  return {
    id: 100, building_id: 10, apartment_number: '42',
    building_address: 'ул. Кирпичная 5', yard_name: 'Двор Тестовый',
    entrance: 1, floor: 3, rooms_count: 2, area: 54,
    description: null, is_active: true, created_at: null, ...over,
  }
}

beforeEach(() => {
  queries.yards = [makeYard(), makeYard({ id: 2, name: 'Двор Второй' })]
  queries.buildings = [makeBuilding()]
  queries.apartments = [makeApartment()]
  queries.moderation = [{ id: 1 }, { id: 2 }]
  mutateSpy.mockClear()
  buildingsSpy.mockClear()
  localStorage.clear()
})

describe('AddressesPage — уровни каталога', () => {
  it('стартует со списка дворов', () => {
    render(<AddressesPage />)
    expect(screen.getByText('Двор Тестовый')).toBeInTheDocument()
    expect(screen.getByText('Двор Второй')).toBeInTheDocument()
    // Дома ещё не запрашивались: уровень дворов держит yardId=null.
    expect(buildingsSpy).toHaveBeenLastCalledWith(null)
  })

  it('клик по двору проваливается в его дома', async () => {
    render(<AddressesPage />)
    await userEvent.click(screen.getByText('Двор Тестовый'))
    expect(buildingsSpy).toHaveBeenLastCalledWith(1)
    expect(screen.getByText(/Кирпичная 5/)).toBeInTheDocument()
  })

  it('клик по дому проваливается в квартиры', async () => {
    render(<AddressesPage />)
    await userEvent.click(screen.getByText('Двор Тестовый'))
    await userEvent.click(screen.getByText(/Кирпичная 5/))
    expect(screen.getByText(/42/)).toBeInTheDocument()
  })
})

describe('AddressesPage — вкладка модерации', () => {
  it('таб показывает счётчик очереди и открывает панель', async () => {
    render(<AddressesPage />)
    const tab = screen.getByText(/\(2\)/)
    await userEvent.click(tab)
    // Дворы каталога скрыты — контент заменён панелью модерации.
    expect(screen.queryByText('Двор Тестовый')).not.toBeInTheDocument()
  })
})

describe('AddressesPage — режим отображения', () => {
  it('переключение на таблицу запоминается в localStorage', async () => {
    render(<AddressesPage />)
    const tableBtn = screen.getByTitle(/табли/i)
    await userEvent.click(tableBtn)
    expect(localStorage.getItem('addresses_view_mode')).toBe('table')
  })

  it('битое значение в localStorage не ломает страницу', () => {
    localStorage.setItem('addresses_view_mode', 'garbage')
    render(<AddressesPage />)
    expect(screen.getByText('Двор Тестовый')).toBeInTheDocument()
  })
})
