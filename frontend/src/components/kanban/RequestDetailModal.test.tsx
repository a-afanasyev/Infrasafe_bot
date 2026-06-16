import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import RequestDetailModal from './RequestDetailModal'

// useHasRole gates the manager-only urgency editor — mock it per test.
const mockHasRole = vi.fn()
vi.mock('../../hooks/useHasRole', () => ({ useHasRole: (r: string) => mockHasRole(r) }))

function noop() {}

function makeRequest(over: Record<string, unknown> = {}) {
  return {
    request_number: '260101-001',
    status: 'В работе',          // active (non-terminal) by default
    category: 'electricity',
    urgency: 'high',
    source: 'web',
    description: 'desc',
    address: 'addr',
    apartment_id: null,
    executor_id: null,
    executor_name: null,
    created_at: '2026-01-01T12:00:00Z',
    updated_at: null,
    manager_confirmed: false,
    ...over,
  }
}

function mockEndpoints(req: Record<string, unknown>) {
  server.use(
    http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
    http.get('*/api/v2/requests/:number', () => HttpResponse.json(req)),
  )
}

async function renderModal(req: Record<string, unknown>) {
  mockEndpoints(req)
  render(<RequestDetailModal requestNumber={String(req.request_number)} onClose={noop} />)
  // Wait until the request data loaded (urgency badge text appears).
  await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
}

beforeEach(() => {
  mockHasRole.mockReset()
})

describe('RequestDetailModal — manager urgency editor gating (TASK 17)', () => {
  it('manager + active status → urgency is an editable dropdown trigger', async () => {
    mockHasRole.mockReturnValue(true) // manager
    await renderModal(makeRequest({ urgency: 'high', status: 'В работе' }))
    // The editable variant renders a <button> trigger (DropdownMenu); badge-only is a <span>.
    expect(screen.getByRole('button', { name: /Срочная/ })).toBeInTheDocument()
  })

  it('non-manager → urgency is badge only (no dropdown)', async () => {
    mockHasRole.mockReturnValue(false) // executor/applicant
    await renderModal(makeRequest({ urgency: 'high', status: 'В работе' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
    expect(screen.getByText('Срочная')).toBeInTheDocument()
  })

  it('manager + terminal status (Принято) → urgency badge only, frozen', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'high', status: 'Принято' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
    expect(screen.getByText('Срочная')).toBeInTheDocument()
  })

  it('manager + terminal status (Отменена) → urgency badge only, frozen', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'high', status: 'Отменена' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
  })

  it('dual-read: legacy-russian stored urgency still renders + stays editable for manager', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'Срочная', status: 'В работе' }))
    // tUrgency('Срочная') → 'Срочная' via dual-read; editable trigger present.
    expect(screen.getByRole('button', { name: /Срочная/ })).toBeInTheDocument()
  })
})

describe('RequestDetailModal — status dropdown «В работе» executor gating (FE-129)', () => {
  // Bug: выбор «В работе» из статус-дропдауна для заявки из «Закуп» без
  // исполнителя открывал модалку выбора исполнителя и слал executor_id →
  // backend 422 «manager_purchase_done: unexpected field 'executor_id'».
  // Модалка назначения нужна только при взятии из «Новая».
  async function selectStatus(req: Record<string, unknown>, target: string) {
    mockHasRole.mockReturnValue(true)
    let patchBody: unknown = null
    server.use(
      http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
      http.get('*/api/v2/requests/:number', () => HttpResponse.json(req)),
      http.patch('*/api/v2/requests/:number', async ({ request }) => {
        patchBody = await request.json()
        return HttpResponse.json({ ...req, status: target })
      }),
    )
    render(<RequestDetailModal requestNumber={String(req.request_number)} onClose={noop} />)
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: new RegExp(String(req.status)) }))
    await user.click(await screen.findByRole('menuitem', { name: new RegExp(target) }))
    return () => patchBody
  }

  it('«Закуп» → «В работе» without executor: commits directly, no executor modal, no executor_id', async () => {
    const getBody = await selectStatus(
      makeRequest({ status: 'Закуп', executor_id: null, urgency: 'high' }),
      'В работе',
    )
    await waitFor(() => expect(getBody()).toEqual({ status: 'В работе' }))
    expect(screen.queryByText('Назначить исполнителя')).not.toBeInTheDocument()
  })

  it('«Новая» → «В работе» without executor: opens the executor modal (no direct PATCH)', async () => {
    const getBody = await selectStatus(
      makeRequest({ status: 'Новая', executor_id: null, urgency: 'high' }),
      'В работе',
    )
    expect(await screen.findByText('Назначить исполнителя')).toBeInTheDocument()
    expect(getBody()).toBeNull()
  })
})

describe('RequestDetailModal — FE-07 per-request state reset', () => {
  it('clears the manager-note field when a different request opens (render-time reset, no remount)', async () => {
    mockHasRole.mockReturnValue(true)
    server.use(
      http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
      http.get('*/api/v2/requests/:number', ({ params }) =>
        HttpResponse.json(makeRequest({ request_number: params.number, status: 'В работе' }))),
    )
    const { rerender } = render(
      <RequestDetailModal requestNumber="260101-001" onClose={noop} />,
    )
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())

    const note = screen.getByPlaceholderText('Добавить заметку...')
    await userEvent.type(note, 'черновик')
    expect(note).toHaveValue('черновик')

    // Switch to a different request — state must reset without a key-remount.
    rerender(<RequestDetailModal requestNumber="260101-002" onClose={noop} />)
    await waitFor(() =>
      expect(screen.getByPlaceholderText('Добавить заметку...')).toHaveValue(''),
    )
  })
})
