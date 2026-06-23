import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../../test/test-utils'
import { server } from '../../../test/msw/server'

vi.mock('../../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ haptic: vi.fn(), showBackButton: () => () => {} }),
}))

import MyShiftsPage from './MyShiftsPage'

const ACTIVE_SHIFT = {
  id: 5, user_id: 1, status: 'active',
  start_time: '2026-07-01T09:00:00Z', end_time: '2026-07-01T17:00:00Z', notes: null,
}

const INCOMING_TRANSFER = {
  id: 7, shift_id: 99, status: 'assigned', reason: 'illness', urgency_level: 'normal',
  comment: null, from_executor_id: 2, to_executor_id: 1,
  from_executor_name: 'Иван', to_executor_name: 'Я',
  direction: 'incoming', can_respond: true,
  shift_start_time: '2026-07-02T09:00:00Z', created_at: '2026-06-30T10:00:00Z',
}

function seed(opts: { shifts?: unknown[]; transfers?: unknown[] } = {}) {
  server.use(
    http.get('*/api/v2/executor/shifts/me', () =>
      HttpResponse.json(opts.shifts ?? [ACTIVE_SHIFT])),
    http.get('*/api/v2/executor/shifts/transfers', () =>
      HttpResponse.json(opts.transfers ?? [])),
  )
}

describe('TWA MyShiftsPage — transfers (PR-T2)', () => {
  beforeEach(() => server.resetHandlers())

  it('shows «Передать смену» for an active shift and opens the sheet', async () => {
    const user = userEvent.setup()
    seed()
    render(<MyShiftsPage />)

    const initiate = await screen.findByRole('button', { name: /Передать смену/ })
    await user.click(initiate)

    // Лист открылся: причины-пилюли видны.
    expect(await screen.findByText('Болезнь')).toBeInTheDocument()
    expect(screen.getByText('Загруженность')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отправить' })).toBeInTheDocument()
  })

  it('POSTs the initiated transfer with the shift_id', async () => {
    const user = userEvent.setup()
    let captured: Record<string, unknown> | null = null
    seed()
    server.use(
      http.post('*/api/v2/executor/shifts/transfers', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({ ...INCOMING_TRANSFER, shift_id: 5, direction: 'outgoing', can_respond: false }, { status: 201 })
      }),
    )

    render(<MyShiftsPage />)
    await user.click(await screen.findByRole('button', { name: /Передать смену/ }))
    await user.click(await screen.findByText('Загруженность'))   // reason=workload
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await waitFor(() => expect(captured).not.toBeNull())
    expect(captured!.shift_id).toBe(5)
    expect(captured!.reason).toBe('workload')
  })

  it('renders an incoming transfer with Принять and POSTs accept', async () => {
    const user = userEvent.setup()
    let respondBody: Record<string, unknown> | null = null
    seed({ transfers: [INCOMING_TRANSFER] })
    server.use(
      http.post('*/api/v2/executor/shifts/transfers/7/respond', async ({ request }) => {
        respondBody = await request.json()
        return HttpResponse.json({ ...INCOMING_TRANSFER, status: 'completed', can_respond: false })
      }),
    )

    render(<MyShiftsPage />)
    const accept = await screen.findByRole('button', { name: 'Принять' })
    await user.click(accept)

    await waitFor(() => expect(respondBody).not.toBeNull())
    expect(respondBody!.action).toBe('accept')
  })

  it('hides «Передать смену» when the shift already has an active transfer', async () => {
    seed({
      transfers: [{ ...INCOMING_TRANSFER, id: 8, shift_id: 5, direction: 'outgoing', status: 'pending', can_respond: false }],
    })
    render(<MyShiftsPage />)

    // дождаться, пока отрисуются и карточка смены, и карточка передачи (обе с #5).
    await screen.findByText('Мои передачи')
    await waitFor(() => expect(screen.getAllByText(/#5/).length).toBeGreaterThan(1))
    expect(screen.queryByRole('button', { name: /Передать смену/ })).not.toBeInTheDocument()
  })
})
