import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import ResidentsPage from './ResidentsPage'
import type { ResidentListItem, ResidentListResponse, ResidentStats } from '../types/api'

// Страница читает данные хуками без пропсов — мокируем сами хуки (как
// WorkReportsArchivePage.test.tsx), чтобы проверять поведение экрана, а не
// сетевой слой: какие параметры уходят в запрос при смене фильтров и что
// пагинация не остаётся на прошлой странице.
const { listQuery, statsQuery, useResidentsSpy } = vi.hoisted(() => ({
  listQuery: {
    data: undefined as ResidentListResponse | undefined,
    isLoading: false,
    isError: false,
  },
  statsQuery: { data: undefined as ResidentStats | undefined },
  useResidentsSpy: vi.fn(),
}))

vi.mock('../hooks/useResidents', () => ({
  useResidents: (...args: unknown[]) => {
    useResidentsSpy(...args)
    return listQuery
  },
  useResidentStats: () => statsQuery,
  useResidentsWebSocket: () => undefined,
}))

// Адресный каскад — чужой домен; тут важно лишь, что опции появляются.
vi.mock('../hooks/useAddresses', () => ({
  useYards: () => ({ data: [{ id: 7, name: 'Двор-7' }] }),
  useAllBuildings: () => ({ data: [{ id: 70, address: 'ул. Тестовая 1' }] }),
  useAllApartments: () => ({ data: [{ id: 700, apartment_number: '42' }] }),
}))

function makeResident(over: Partial<ResidentListItem> = {}): ResidentListItem {
  return {
    id: 1,
    telegram_id: 5001,
    username: 'ivanov',
    first_name: 'Иван',
    last_name: 'Иванов',
    phone: '+998901112233',
    status: 'approved',
    verification_status: 'pending',
    language: 'ru',
    created_at: '2026-07-01T10:00:00Z',
    apartments_count: 1,
    primary_address: 'Двор-7 · ул. Тестовая 1 · кв. 42',
    ...over,
  }
}

function lastCall() {
  return useResidentsSpy.mock.calls[useResidentsSpy.mock.calls.length - 1]
}

beforeEach(() => {
  listQuery.data = { items: [makeResident()], total: 1, limit: 25, offset: 0 }
  listQuery.isLoading = false
  listQuery.isError = false
  statsQuery.data = {
    total: 12, pending: 3, approved: 8, blocked: 1,
    verification_pending: 5, verification_requested: 2,
    verified: 4, verification_rejected: 1,
  }
  useResidentsSpy.mockClear()
})

describe('ResidentsPage', () => {
  it('показывает жителя и его основной адрес', () => {
    render(<ResidentsPage />)
    expect(screen.getByText('Иван Иванов')).toBeInTheDocument()
    expect(screen.getByText('Двор-7 · ул. Тестовая 1 · кв. 42')).toBeInTheDocument()
  })

  it('выводит счётчики обеих осей', () => {
    render(<ResidentsPage />)
    expect(screen.getByText('12')).toBeInTheDocument()  // всего
    expect(screen.getByText('2')).toBeInTheDocument()   // запрошены документы
  })

  it('пустой список показывает заглушку, а не таблицу', () => {
    listQuery.data = { items: [], total: 0, limit: 25, offset: 0 }
    render(<ResidentsPage />)
    expect(screen.getByText(/Жители не найдены/)).toBeInTheDocument()
  })

  it('ошибка запроса не роняет страницу', () => {
    listQuery.isError = true
    render(<ResidentsPage />)
    expect(useResidentsSpy).toHaveBeenCalled()
  })

  it('фильтр статуса уходит в запрос', async () => {
    const user = userEvent.setup()
    render(<ResidentsPage />)
    await user.click(screen.getByRole('button', { name: 'Заблокирован' }))
    expect(lastCall()[0]).toEqual({ status: 'blocked' })
  })

  it('фильтр верификации уходит в запрос отдельной осью', async () => {
    const user = userEvent.setup()
    render(<ResidentsPage />)
    await user.click(screen.getByRole('button', { name: 'Запрошены документы' }))
    expect(lastCall()[0]).toEqual({ verification_status: 'requested' })
  })

  it('выбор двора шлёт yard_id, выбор дома перекрывает его building_id', async () => {
    const user = userEvent.setup()
    render(<ResidentsPage />)

    await user.selectOptions(screen.getByDisplayValue('Все дворы'), '7')
    expect(lastCall()[0]).toEqual({ yard_id: 7 })

    await user.selectOptions(screen.getByDisplayValue('Все дома'), '70')
    // Дом ЗАМЕНЯЕТ двор, а не добавляется к нему: двор — родитель дома,
    // одновременная передача обоих сузила бы выборку дважды одним и тем же.
    expect(lastCall()[0]).toEqual({ building_id: 70 })
  })

  it('смена фильтра возвращает на первую страницу', async () => {
    listQuery.data = { items: [makeResident()], total: 60, limit: 25, offset: 0 }
    const user = userEvent.setup()
    render(<ResidentsPage />)

    await user.click(screen.getByRole('button', { name: 'Далее' }))
    expect(lastCall()[2]).toEqual({ limit: 25, offset: 25 })

    await user.click(screen.getByRole('button', { name: 'Заблокирован' }))
    expect(lastCall()[2]).toEqual({ limit: 25, offset: 0 })
  })

  it('страница, уехавшая за конец списка, предлагает вернуться в начало', async () => {
    // Polling 30с может сократить total, пока менеджер стоит на дальней
    // странице: пустая выдача при offset > 0 — не «ничего не найдено».
    listQuery.data = { items: [makeResident()], total: 60, limit: 25, offset: 0 }
    const user = userEvent.setup()
    const { rerender } = render(<ResidentsPage />)
    await user.click(screen.getByRole('button', { name: 'Далее' }))

    // Список сократился фоновым перезапросом — вторая страница опустела.
    listQuery.data = { items: [], total: 5, limit: 25, offset: 25 }
    rerender(<ResidentsPage />)

    expect(screen.getByText(/Страница за пределами списка/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'В начало списка' }))
    expect(lastCall()[2]).toEqual({ limit: 25, offset: 0 })
  })

  it('пагинация не показывается, когда всё влезло на страницу', () => {
    render(<ResidentsPage />)
    expect(screen.queryByRole('button', { name: 'Далее' })).not.toBeInTheDocument()
  })
})
