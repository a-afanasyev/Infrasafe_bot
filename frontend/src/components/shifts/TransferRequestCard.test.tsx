import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import type { TransferOut } from '../../types/api'
import TransferRequestCard from './TransferRequestCard'

const EMPLOYEES = [
  { id: 5, first_name: 'Электрик', last_name: 'Тест1', phone: '+998901111113', specialization: ['electrician'], active_shift_id: null, verification_status: 'verified', status: 'approved' },
]

function transfer(over: Partial<TransferOut> = {}): TransferOut {
  return {
    id: 1, shift_id: 94, from_executor_name: 'Сантехник Тест1', to_executor_name: null,
    status: 'pending', reason: 'illness', urgency_level: 'normal', comment: null,
    created_at: '2026-06-22T21:39:00Z', ...over,
  }
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true })
  server.use(http.get('*/api/v2/shifts/employees', () => HttpResponse.json(EMPLOYEES)))
})

describe('TransferRequestCard', () => {
  it('pending: assigns an executor via approve (POST handle action=approve + to_executor_id)', async () => {
    let body: Record<string, unknown> | null = null
    let calledId: string | null = null
    server.use(
      http.post('*/api/v2/shifts/transfers/:id/handle', async ({ request, params }) => {
        calledId = String(params.id)
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 1, status: 'assigned' })
      }),
    )
    const user = userEvent.setup()
    render(<TransferRequestCard transfer={transfer()} />)

    await user.click(screen.getByRole('button', { name: 'Назначить' }))
    await user.selectOptions(await screen.findByRole('combobox'), '5')
    await user.click(screen.getByRole('button', { name: 'Назначить' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(calledId).toBe('1')
    expect(body).toEqual({ action: 'approve', to_executor_id: 5 })
  })

  it('assigned: rejects via POST handle action=reject', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/transfers/:id/handle', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 1, status: 'rejected' })
      }),
    )
    const user = userEvent.setup()
    render(<TransferRequestCard transfer={transfer({ status: 'assigned', to_executor_name: 'Электрик Тест1' })} />)

    await user.click(screen.getByRole('button', { name: 'Отклонить' }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ action: 'reject' })
  })

  it('hides action buttons for non-managers', () => {
    useAuthStore.setState({ user: { id: 2, roles: ['executor'] }, isAuthenticated: true })
    render(<TransferRequestCard transfer={transfer()} />)
    expect(screen.queryByRole('button', { name: 'Назначить' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Отменить' })).not.toBeInTheDocument()
    // карточка всё равно отображает суть запроса
    expect(screen.getByText('Сантехник Тест1 → ?')).toBeInTheDocument()
  })
})
