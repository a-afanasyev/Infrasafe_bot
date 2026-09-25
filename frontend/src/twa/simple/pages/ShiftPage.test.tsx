import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, queued } from '../../../test/twaSimple'
import type { QueueItem } from '../queue/types'
import ShiftPage from './ShiftPage'

// Смена простого режима: круглая «Начать» / «Закончить», таймер; перед
// завершением — «Да / Нет» со счётчиком незакрытых заявок.

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

let current: { id: number; start_time: string } | null

beforeEach(() => {
  current = null
  mockGet.mockReset()
  mockPost.mockReset()
  mockGet.mockImplementation((url: string) => {
    if (url === '/api/v2/executor/shifts/current') return Promise.resolve({ data: current })
    if (url === '/api/v2/requests') {
      return Promise.resolve({
        data: [
          { request_number: '1', status: 'В работе', category: 'x', created_at: '2026-09-26T08:00:00Z' },
          { request_number: '2', status: 'Возвращена', category: 'x', created_at: '2026-09-26T08:00:00Z' },
        ],
      })
    }
    return Promise.reject(new Error(url))
  })
  mockPost.mockImplementation((url: string) => {
    if (url === '/api/v2/executor/shifts/start') {
      current = { id: 7, start_time: new Date(Date.now() - 65.5 * 60_000).toISOString() }
      return Promise.resolve({ data: current })
    }
    if (url === '/api/v2/executor/shifts/7/end') {
      current = null
      return Promise.resolve({ data: {} })
    }
    return Promise.reject(new Error(url))
  })
})

async function renderShift(items: QueueItem[] = []) {
  const store = await memoryQueueWith(items)
  render(<QueueWrapper store={store}><ShiftPage /></QueueWrapper>, { routerEntries: ['/twa/s/shift'] })
}

describe('simple ShiftPage', () => {
  it('«Начать» → POST start, таймер; «Закончить» → «Незакрыто: 2» → «Да» → POST end', async () => {
    await renderShift()
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Начать/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/start', {}))
    expect(await screen.findByRole('status')).toHaveTextContent('Смена начата')
    expect(await screen.findByTestId('shift-timer')).toHaveTextContent('01:05')

    fireEvent.click(screen.getByRole('button', { name: /Закончить/ }))
    expect(screen.getByRole('dialog', { name: 'Закончить смену?' })).toBeInTheDocument()
    expect(await screen.findByText('Незакрыто: 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/7/end'))
    expect(await screen.findByText('Смена закончена')).toBeInTheDocument()
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
  })

  it('ошибка старта — крест на весь экран и «Ещё раз»', async () => {
    mockPost.mockRejectedValueOnce({ response: { status: 500 } })
    await renderShift()
    fireEvent.click(await screen.findByRole('button', { name: /Начать/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Не получилось')
    fireEvent.click(screen.getByRole('button', { name: /Ещё раз/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2))
  })

  it('«Закончить» при неотправленных фото — «Фото ждёт: N» и предупреждение', async () => {
    current = { id: 7, start_time: new Date().toISOString() }
    mockPost.mockReturnValue(new Promise(() => {}))
    await renderShift([queued('260926-001', { noShift: true })])
    fireEvent.click(await screen.findByRole('button', { name: /Закончить/ }))
    expect(await screen.findByText('Фото ждёт: 1')).toBeInTheDocument()
    expect(screen.getByText('Сначала дождитесь отправки фото')).toBeInTheDocument()
  })

  it('«Незакрыто: N» не показывается, пока задачи не загружены', async () => {
    current = { id: 7, start_time: new Date().toISOString() }
    const base = mockGet.getMockImplementation()!
    mockGet.mockImplementation((url: string) => (url === '/api/v2/requests' ? new Promise(() => {}) : base(url)))
    await renderShift()
    fireEvent.click(await screen.findByRole('button', { name: /Закончить/ }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.queryByText(/Незакрыто/)).toBeNull()
  })

  it('«Нет» — смена продолжается', async () => {
    current = { id: 7, start_time: new Date().toISOString() }
    await renderShift()
    fireEvent.click(await screen.findByRole('button', { name: /Закончить/ }))
    fireEvent.click(screen.getByRole('button', { name: /Нет/ }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
