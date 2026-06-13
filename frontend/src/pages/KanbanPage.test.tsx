import { describe, it, expect, vi } from 'vitest'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import { testI18n } from '../test/test-utils'
import { TopbarProvider } from '../contexts/TopbarContext'
import KanbanPage from './KanbanPage'

// The board pulls a WebSocket + kanban query we don't care about here — stub it.
// onCardClick is surfaced so we can also drive the manual (non-deep-link) path.
// Partial mock: stub the default export (board UI) but keep named exports
// (FROZEN_STATUSES / VALID_TRANSITIONS) that RequestDetailModal imports from here.
vi.mock('../components/kanban/KanbanBoard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../components/kanban/KanbanBoard')>()
  return {
    ...actual,
    default: ({ onCardClick }: { onCardClick: (n: string) => void }) => (
      <button onClick={() => onCardClick('260101-009')}>open-card</button>
    ),
  }
})
vi.mock('../components/callcenter/CallCenterModal', () => ({ default: () => null }))

// Reads the live location.search so we can assert the deep-link query got stripped.
function LocationProbe() {
  const { search } = useLocation()
  return <div data-testid="search">{search}</div>
}

function makeRequest(number: string, over: Record<string, unknown> = {}) {
  return {
    request_number: number,
    status: 'В работе',
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

function mockRequestEndpoints() {
  server.use(
    http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
    http.get('*/api/v2/requests/:number', ({ params }) =>
      HttpResponse.json(makeRequest(String(params.number)))),
  )
}

function renderAt(entry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter initialEntries={[entry]}>
          <TopbarProvider>
            <LocationProbe />
            <KanbanPage />
          </TopbarProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  )
}

describe('KanbanPage — deep-link reader (?request=)', () => {
  it('opens the detail modal for ?request= and strips the deep-link query', async () => {
    mockRequestEndpoints()
    renderAt('/dashboard?request=260101-001&reopen_sequence=2&related_request=260101-000&reopen_chain_id=abc')

    // Modal opened for the linked request (urgency badge renders once data loaded).
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
    // All deep-link params consumed and removed from the URL.
    expect(screen.getByTestId('search')).toHaveTextContent('')
  })

  it('does nothing without a ?request= param (no modal)', async () => {
    mockRequestEndpoints()
    renderAt('/dashboard')
    // Manual board is present; no detail modal until a card is clicked.
    expect(screen.getByText('open-card')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Срочная')).not.toBeInTheDocument()
    })
  })

  it('wires onOpenRelated so the manual card path opens the modal too', async () => {
    mockRequestEndpoints()
    renderAt('/dashboard')
    await userEvent.click(screen.getByText('open-card'))
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
  })
})
