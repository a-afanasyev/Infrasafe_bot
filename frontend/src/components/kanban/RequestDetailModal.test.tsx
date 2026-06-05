import { describe, it, expect, beforeEach, vi } from 'vitest'
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
