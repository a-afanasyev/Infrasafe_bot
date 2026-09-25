import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith } from '../../../test/twaSimple'
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

async function renderShift() {
  const store = await memoryQueueWith()
  render(<QueueWrapper store={store}><ShiftPage /></QueueWrapper>, { routerEntries: ['/twa/s/shift'] })
}

describe('simple ShiftPage', () => {
  it('«Начать» → POST start, таймер; «Закончить» → «Незакрыто: 2» → «Да» → POST end', async () => {
    await renderShift()
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Начать/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/start', {}))
    expect(await screen.findByTestId('shift-timer')).toHaveTextContent('01:05')

    fireEvent.click(screen.getByRole('button', { name: /Закончить/ }))
    expect(screen.getByRole('dialog', { name: 'Закончить смену?' })).toBeInTheDocument()
    expect(await screen.findByText('Незакрыто: 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/7/end'))
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
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
