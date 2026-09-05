import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '../../../test/test-utils'
import CreatePage from './CreatePage'

// Шаг «Лифт» мастера создания заявки (Ф4a-3): появляется только для
// категории elevator при включённом модуле, грузит лифты дома (для квартиры —
// её building_id из request-addresses), требует выбор лифта и «работает?»,
// кладёт elevator_id/elevator_operational в POST /requests.

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}))

vi.mock('../../twaClient', () => ({
  twaClient: { get: mockGet, post: mockPost },
}))

const ADDRESSES = {
  yards: [{ id: 1, label: 'Двор 1' }],
  buildings: [{ id: 12, label: 'Дом 12', yard_id: 1 }, { id: 13, label: 'Дом 13', yard_id: 1 }],
  apartments: [{ id: 5, label: 'Кв. 7, Дом 12', building_id: 12, yard_id: 1 }],
}

const ELEVATORS_12 = [
  { id: 7, entrance_number: 2, elevator_number: 1, label: 'Лифт 1, подъезд 2', current_status: 'under_repair' },
]

function mockApi(elevatorsByBuilding: Record<number, unknown[]> = { 12: ELEVATORS_12, 13: [] }) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('request-addresses')) return Promise.resolve({ data: ADDRESSES })
    const m = /for-building\/(\d+)/.exec(url)
    if (m) return Promise.resolve({ data: elevatorsByBuilding[Number(m[1])] ?? [] })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  mockPost.mockResolvedValue({ data: { request_number: '260906-001' } })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  sessionStorage.clear()
})

afterEach(() => vi.unstubAllEnvs())

async function goToAddress(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Лифт' }))
  await screen.findByRole('button', { name: /Кв\. 7, Дом 12/ })
}

describe('CreatePage — шаг «Лифт»', () => {
  it('квартира → лифты её дома; единственный лифт автовыбран; POST несёт elevator_id/elevator_operational', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    const elevatorBtn = await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })
    expect(elevatorBtn).toHaveAttribute('aria-pressed', 'true')
    expect(mockGet).toHaveBeenCalledWith('/api/v2/elevators/for-building/12', { params: { lang: 'ru' } })
    // Мягкая подсказка по статусу «в ремонте» — не блокирует.
    expect(screen.getByText(/уже в ремонте/)).toBeInTheDocument()

    const next = screen.getByRole('button', { name: 'Далее' })
    expect(next).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Нет, не работает' }))
    expect(next).toBeEnabled()
    await user.click(next)

    await user.type(screen.getByRole('textbox'), 'Лифт стоит')
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Далее' })) // фото — пропускаем
    await user.click(screen.getByRole('button', { name: 'Обычная' }))

    expect(screen.getByText(/Лифт 1, подъезд 2 · не работает/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    expect(mockPost).toHaveBeenCalledWith('/api/v2/requests', {
      category: 'elevator',
      address_type: 'apartment',
      address_id: 5,
      description: 'Лифт стоит',
      urgency: 'low',
      elevator_id: 7,
      elevator_operational: false,
    })
  })

  it('двор: подсказка выбрать дом или квартиру, продолжить нельзя', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Двор 1/ }))

    expect(await screen.findByText(/выберите дом или квартиру/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Далее' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'К выбору адреса' }))
    expect(screen.getByText('Выберите адрес')).toBeInTheDocument()
  })

  it('в доме нет лифтов: сообщение и возврат к категории', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Дом 13/ }))

    expect(await screen.findByText(/лифты не заведены/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Далее' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Назад к категории' }))
    expect(screen.getByText('Выберите категорию')).toBeInTheDocument()
  })

  it('флаг выключен: после адреса сразу описание, лифты не запрашиваются', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'false')
    mockApi()
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    expect(await screen.findByText('Опишите проблему')).toBeInTheDocument()
    expect(mockGet.mock.calls.some(([url]) => String(url).includes('for-building'))).toBe(false)
  })

  it('другая категория при включённом флаге: шага «Лифт» нет', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    const user = userEvent.setup()
    render(<CreatePage />)

    await user.click(screen.getByRole('button', { name: 'Сантехника' }))
    await user.click(await screen.findByRole('button', { name: /Кв\. 7, Дом 12/ }))

    expect(await screen.findByText('Опишите проблему')).toBeInTheDocument()
    expect(mockGet.mock.calls.some(([url]) => String(url).includes('for-building'))).toBe(false)
  })
})
