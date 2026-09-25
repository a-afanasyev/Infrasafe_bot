import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor, within } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, stubTelegram, unstubTelegram } from '../../../test/twaSimple'
import PoolPage from './PoolPage'

// «Взять»: POST /claim; исход — на весь экран (галка / крест), не тостом;
// 409 already_claimed — «Уже взяли» и плитка исчезает; вне смены — только
// крупная «Начать смену».

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

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
    expect(await screen.findByRole('status')).toHaveTextContent('Заявка ваша')
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('success')
  })

  it('409 already_claimed — «Уже взяли», плитка убрана, вибрация ошибки', async () => {
    const { haptic } = stubTelegram()
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'already_claimed' } } })
    await renderPool()
    fireEvent.click(within(await screen.findByTestId('tile-260926-002')).getByRole('button', { name: /Взять/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Уже взяли')
    expect(screen.queryByTestId('tile-260926-002')).toBeNull()
    expect(screen.getByTestId('tile-260926-001')).toBeInTheDocument()
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('error')
    expect(haptic.notificationOccurred).not.toHaveBeenCalledWith('success')
  })

  it('403 not_eligible — свой текст на весь экран; прочая ошибка — «Не получилось взять» и «Ещё раз»', async () => {
    mockPost.mockRejectedValueOnce({ response: { status: 403, data: { detail: 'not_eligible' } } })
    await renderPool()
    fireEvent.click(within(await screen.findByTestId('tile-260926-001')).getByRole('button', { name: /Взять/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Эту заявку взять нельзя')
    fireEvent.click(screen.getByRole('button', { name: /Понятно/ }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())

    mockPost.mockRejectedValueOnce({ response: { status: 500 } }).mockResolvedValueOnce({ data: {} })
    fireEvent.click(within(await screen.findByTestId('tile-260926-001')).getByRole('button', { name: /Взять/ }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не получилось взять')
    expect(alert).not.toHaveTextContent('Не отправилось')
    fireEvent.click(screen.getByRole('button', { name: /Ещё раз/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(3))
    expect(await screen.findByRole('status')).toHaveTextContent('Заявка ваша')
  })

  it('вне смены — «Начать смену» ведёт на экран смены', async () => {
    pool = { on_shift: false, items: [] }
    await renderPool()
    fireEvent.click(await screen.findByRole('button', { name: /Начать смену/ }))
    expect(await screen.findByText('SHIFT SCREEN')).toBeInTheDocument()
  })
})
