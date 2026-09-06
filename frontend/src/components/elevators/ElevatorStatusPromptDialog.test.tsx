import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import ElevatorStatusPromptDialog from './ElevatorStatusPromptDialog'
import { MAX_BULK_CONFIRM, MAX_REASON_LEN } from '../../types/elevators'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

// Подсказка «Лифт работает?» после подтверждения заявки: выбор другого статуса
// → PUT с reason/request_number; тот же статус — «без изменений» без запроса.

function renderPrompt(onClose = vi.fn(), requestNumbers: readonly string[] = ['260905-001']) {
  render(
    <ElevatorStatusPromptDialog
      open
      elevatorId={7}
      elevatorLabel="Лифт 1, подъезд 2"
      currentStatus="working"
      requestNumbers={requestNumbers}
      onClose={onClose}
    />,
  )
  return onClose
}

beforeEach(() => {
  vi.mocked(toast.info).mockReset()
  vi.mocked(toast.success).mockReset()
})

describe('ElevatorStatusPromptDialog', () => {
  it('показывает лифт и текущий статус, помечает текущий статус', () => {
    renderPrompt()
    expect(screen.getByText('Лифт Лифт 1, подъезд 2: сейчас «Работает». Лифт работает?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Работает · текущий/ })).toBeInTheDocument()
  })

  it('другой статус → PUT /elevators/7/status с reason и request_number, закрытие', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/elevators/7/status', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ changed: true, old_status: 'working', new_status: 'not_working', status_since: null, notified_residents: 3 })
      }),
    )
    const onClose = renderPrompt()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Не работает' }))
    await waitFor(() =>
      expect(body).toEqual({
        status: 'not_working',
        reason: 'подтверждение заявки 260905-001',
        request_number: '260905-001',
      }),
    )
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(toast.success).toHaveBeenCalledWith('Статус изменён, уведомлено жителей: 3')
  })

  it('несколько заявок → reason со списком, request_number не передаётся', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/elevators/7/status', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ changed: true, old_status: 'working', new_status: 'under_repair', status_since: null, notified_residents: 0 })
      }),
    )
    renderPrompt(vi.fn(), ['260905-001', '260905-002'])
    await userEvent.setup().click(screen.getByRole('button', { name: 'В ремонте' }))
    await waitFor(() =>
      expect(body).toEqual({
        status: 'under_repair',
        reason: 'подтверждение 2 заявок: 260905-001, 260905-002',
        request_number: null,
      }),
    )
  })

  it('50 заявок (MAX_BULK_CONFIRM) — reason ≤ MAX_REASON_LEN, первые 5 и «+45»', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/elevators/7/status', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ changed: true, old_status: 'working', new_status: 'not_working', status_since: null, notified_residents: 0 })
      }),
    )
    const numbers = Array.from({ length: MAX_BULK_CONFIRM }, (_, i) => `260905-${String(i + 1).padStart(3, '0')}`)
    renderPrompt(vi.fn(), numbers)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Не работает' }))
    await waitFor(() => expect(body).not.toBeNull())
    const reason = String(body!.reason)
    expect(reason.length).toBeLessThanOrEqual(MAX_REASON_LEN)
    expect(reason).toBe('подтверждение 50 заявок: 260905-001, 260905-002, 260905-003, 260905-004, 260905-005 +45')
    expect(body!.request_number).toBeNull()
  })

  it('тот же статус — «без изменений» без запроса', async () => {
    const onClose = renderPrompt()
    await userEvent.setup().click(screen.getByRole('button', { name: /^Работает/ }))
    expect(toast.info).toHaveBeenCalledWith('Статус не изменился')
    expect(onClose).toHaveBeenCalled()
  })

  it('«Оставить как есть» просто закрывает', async () => {
    const onClose = renderPrompt()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Оставить как есть' }))
    expect(onClose).toHaveBeenCalled()
    expect(toast.info).not.toHaveBeenCalled()
  })
})
