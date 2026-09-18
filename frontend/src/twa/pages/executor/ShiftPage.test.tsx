import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, waitFor, fireEvent } from '../../../test/test-utils'
import ShiftPage from './ShiftPage'

// TEST-068: экран смены исполнителя — старт/завершение смены, таймер,
// переход в «Мои смены».

const { mockGet, mockPost, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost } }))
vi.mock('sonner', () => ({ toast: toastMock }))

let current: { id: number; start_time: string } | null

function renderPage() {
  render(
    <Routes>
      <Route path="/twa/exec/shift" element={<ShiftPage />} />
      <Route path="/twa/exec/shifts" element={<div>MY SHIFTS</div>} />
    </Routes>,
    { routerEntries: ['/twa/exec/shift'] },
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  toastMock.error.mockReset()
  current = null
  mockGet.mockImplementation((url: string) =>
    url === '/api/v2/executor/shifts/current' ? Promise.resolve({ data: current }) : Promise.reject(new Error(url)),
  )
  mockPost.mockImplementation((url: string) => {
    if (url === '/api/v2/executor/shifts/start') {
      current = { id: 1, start_time: new Date(Date.now() - 65_000).toISOString() }
      return Promise.resolve({ data: current })
    }
    if (url === '/api/v2/executor/shifts/1/end') {
      current = null
      return Promise.resolve({ data: { ok: true } })
    }
    return Promise.reject(new Error(url))
  })
})

describe('ShiftPage', () => {
  it('без смены — «Смена не начата»; старт → POST и таймер активной смены; завершение → POST end', async () => {
    renderPage()
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Начать смену/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/start', {}))
    expect(await screen.findByText('Смена активна')).toBeInTheDocument()
    // Смена началась 65 с назад → таймер показывает 00:01:0x.
    await waitFor(() => expect(screen.getByText(/^00:01:0\d$/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /Завершить смену/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/executor/shifts/1/end'))
    expect(await screen.findByText('Смена не начата')).toBeInTheDocument()
  })

  it('ошибка старта → toast.error, экран остаётся без смены', async () => {
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'Уже есть активная смена' } } })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Начать смену/ }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(screen.getByText('Смена не начата')).toBeInTheDocument()
  })

  it('«Мои смены» ведёт на список смен', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Мои смены/ }))
    expect(await screen.findByText('MY SHIFTS')).toBeInTheDocument()
  })
})
