import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor, within } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, stubTelegram, unstubTelegram } from '../../../test/twaSimple'
import PoolPage from './PoolPage'

// «Взять»: POST /claim; 409 already_claimed — «Уже взяли» и плитка исчезает;
// вне смены — только крупная «Начать смену».

const { mockGet, mockPost, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))
vi.mock('sonner', () => ({ toast: toastMock }))

let pool: { on_shift: boolean; items: unknown[] }

const ITEM = (n: string, extra = {}) => ({
  request_number: n,
  status: 'Новая',
  category: 'cleaning',
  building_address: 'Дом 5',
  entrance: 2,
  apartment_number: '45',
  description_first_line: 'Мусор у лифта',
  photo_media_id: null,
  ...extra,
})

beforeEach(() => {
  pool = { on_shift: true, items: [ITEM('260926-001'), ITEM('260926-002', { building_address: null, address: 'Двор' })] }
  mockGet.mockReset()
  mockPost.mockReset()
  Object.values(toastMock).forEach((f) => f.mockReset())
  mockGet.mockImplementation((url: string) => {
    if (url === '/api/v2/requests/pool') return Promise.resolve({ data: pool })
    if (url === '/api/v2/executor/shifts/current') return Promise.resolve({ data: { id: 1, start_time: new Date().toISOString() } })
    return Promise.reject(new Error(url))
  })
})

afterEach(() => unstubTelegram())

async function renderPool() {
  const store = await memoryQueueWith()
  return render(
    <QueueWrapper store={store}>
      <Routes>
        <Route path="/twa/s/pool" element={<PoolPage />} />
        <Route path="/twa/s/shift" element={<div>SHIFT SCREEN</div>} />
      </Routes>
    </QueueWrapper>,
    { routerEntries: ['/twa/s/pool'] },
  )
}

describe('PoolPage', () => {
  it('плитки: адрес «дом · подъезд · кв», иначе строка адреса; «Взять» → POST /claim', async () => {
    const { haptic } = stubTelegram()
    mockPost.mockResolvedValue({ data: {} })
    await renderPool()
    expect(await screen.findByText('Дом 5 · Подъезд 2 · кв 45')).toBeInTheDocument()
    expect(screen.getByText('Двор')).toBeInTheDocument()

    fireEvent.click(within(screen.getByTestId('tile-260926-001')).getByRole('button', { name: /Взять/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/requests/260926-001/claim'))
    await waitFor(() => expect(screen.queryByTestId('tile-260926-001')).toBeNull())
    expect(toastMock.success).toHaveBeenCalledWith('Заявка ваша')
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('success')
  })

  it('409 already_claimed — «Уже взяли», плитка убрана, вибрация ошибки', async () => {
    const { haptic } = stubTelegram()
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'already_claimed' } } })
    await renderPool()
    fireEvent.click(within(await screen.findByTestId('tile-260926-002')).getByRole('button', { name: /Взять/ }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Уже взяли'))
    expect(screen.queryByTestId('tile-260926-002')).toBeNull()
    expect(screen.getByTestId('tile-260926-001')).toBeInTheDocument()
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('error')
    expect(haptic.notificationOccurred).not.toHaveBeenCalledWith('success')
  })

  it('вне смены — «Начать смену» ведёт на экран смены', async () => {
    pool = { on_shift: false, items: [] }
    await renderPool()
    fireEvent.click(await screen.findByRole('button', { name: /Начать смену/ }))
    expect(await screen.findByText('SHIFT SCREEN')).toBeInTheDocument()
  })
})
