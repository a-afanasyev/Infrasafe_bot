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
  { id: 7, entrance_number: 2, elevator_number: 1, label: 'Лифт 1, подъезд 2', current_status: 'working' },
]

// Р18: тот же лифт «В ремонте». Блокировать или нет — вердикт СЕРВЕРА
// (`resident_request_blocked`), он же учитывает тумблер Р18a.
const ELEVATORS_12_UNDER_WORKS = [
  {
    id: 7, entrance_number: 2, elevator_number: 1, label: 'Лифт 1, подъезд 2',
    current_status: 'under_repair', status_since: '2026-09-01T07:30:00Z',
    resident_request_blocked: true,
  },
]

// Р18a: тот же лифт при включённом тумблере — сервер не блокирует.
const ELEVATORS_12_UNDER_WORKS_ALLOWED = [
  { ...ELEVATORS_12_UNDER_WORKS[0], resident_request_blocked: false },
]

function mockApi(elevatorsByBuilding: Record<number, unknown[]> = { 12: ELEVATORS_12, 13: [] }) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('request-addresses')) return Promise.resolve({ data: ADDRESSES })
    if (url.includes('announcements')) {
      return Promise.resolve({ data: { emergency_phones: ['+998 71 200-00-00'] } })
    }
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

  it('ошибка загрузки лифтов: «Повторить» перезапрашивает, «К выбору адреса» возвращает', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    let attempts = 0
    mockGet.mockImplementation((url: string) => {
      if (url.includes('request-addresses')) return Promise.resolve({ data: ADDRESSES })
      attempts += 1
      return attempts === 1 ? Promise.reject(new Error('network')) : Promise.resolve({ data: ELEVATORS_12 })
    })
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    expect(await screen.findByText('Не удалось загрузить список лифтов')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'К выбору адреса' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it('черновик с индексом шага за пределами набора (флаг выключен) — показывает последний шаг, не пустоту', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'false')
    mockApi()
    sessionStorage.setItem('twa.create.draft.v2', JSON.stringify({
      step: 6, category: 'elevator', addressType: 'apartment', addressId: 5, addressLabel: 'Кв. 7, Дом 12',
      description: 'Лифт стоит', urgency: 'low',
    }))
    render(<CreatePage />)

    expect(await screen.findByText('Подтверждение')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отправить заявку' })).toBeInTheDocument()
  })

  it('черновик «лифта» с полем elevator при выключенном флаге — возврат к шагу адреса', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'false')
    mockApi()
    sessionStorage.setItem('twa.create.draft.v2', JSON.stringify({
      step: 3, category: 'elevator', addressType: 'apartment', addressId: 5, addressLabel: 'Кв. 7, Дом 12',
      description: '', urgency: 'low',
      elevator: { elevatorId: 7, elevatorLabel: 'Лифт 1, подъезд 2', elevatorStatus: 'working', operational: true },
    }))
    render(<CreatePage />)

    expect(await screen.findByText('Выберите адрес')).toBeInTheDocument()
  })

  it('черновик восстанавливает выбор лифта; смена адреса сбрасывает его', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    sessionStorage.setItem('twa.create.draft.v2', JSON.stringify({
      step: 2, category: 'elevator', addressType: 'apartment', addressId: 5, addressLabel: 'Кв. 7, Дом 12',
      description: '', urgency: 'low',
      elevator: { elevatorId: 7, elevatorLabel: 'Лифт 1, подъезд 2', elevatorStatus: 'working', operational: true },
    }))
    const user = userEvent.setup()
    render(<CreatePage />)

    expect(await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Да, работает' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Далее' })).toBeEnabled()

    // Назад к адресу и выбор дома (тот же дом, но другой уровень адреса):
    // единственный лифт автовыберется снова, а ответ «работает?» сброшен.
    await user.click(screen.getByRole('button', { name: /← Назад/ }))
    await user.click(await screen.findByRole('button', { name: /^🏢 Дом 12$/ }))
    expect(await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Да, работает' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Далее' })).toBeDisabled()
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

describe('CreatePage — Р18: лифт в работах', () => {
  it('лифт «В ремонте» виден в списке, но блокирует шаг: вопроса нет, «Далее» выключено', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi({ 12: ELEVATORS_12_UNDER_WORKS, 13: [] })
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    // лифт в списке есть и автовыбран (единственный)
    expect(await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByRole('alert')).toHaveTextContent(/Заявка не нужна/)
    expect(screen.queryByRole('button', { name: 'Да, работает' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Далее' })).toBeDisabled()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('в блоке — телефон диспетчерской ссылкой tel:', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi({ 12: ELEVATORS_12_UNDER_WORKS, 13: [] })
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    const link = await screen.findByRole('link', { name: '+998 71 200-00-00' })
    // санитизация как в публичном виджете: только цифры и «+»
    expect(link).toHaveAttribute('href', 'tel:+998712000000')
  })

  it('тумблер Р18a включён (сервер не блокирует): мягкая подсказка и обычный поток', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi({ 12: ELEVATORS_12_UNDER_WORKS_ALLOWED, 13: [] })
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))

    await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText(/уже в ремонте/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Нет, не работает' }))
    expect(screen.getByRole('button', { name: 'Далее' })).toBeEnabled()
  })

  it('серверный 409 (гонка статусов) показывает тот же блок, а не общую ошибку', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockApi()
    mockPost.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'elevator_under_works', status: 'maintenance',
            status_since: '2026-09-01T07:30:00Z', label: 'ул. Ленина 1, подъезд 2, лифт 1',
          },
        },
      },
    })
    const user = userEvent.setup()
    render(<CreatePage />)

    await goToAddress(user)
    await user.click(screen.getByRole('button', { name: /Кв\. 7, Дом 12/ }))
    await screen.findByRole('button', { name: /Подъезд 2 · лифт 1/ })
    await user.click(screen.getByRole('button', { name: 'Нет, не работает' }))
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.type(screen.getByRole('textbox'), 'Лифт стоит')
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Обычная' }))
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Заявка не нужна/)
    expect(alert).toHaveTextContent(/ул\. Ленина 1, подъезд 2, лифт 1/)
  })
})
