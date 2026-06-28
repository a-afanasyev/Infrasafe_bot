import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, fireEvent } from '../../../test/test-utils'
import { server } from '../../../test/msw/server'

// src/twa/** исключён из coverage, но импорт useTelegramSDK всё равно
// исполняется — мокаем, чтобы не трогать реальный Telegram-рантайм.
vi.mock('../../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({
    haptic: vi.fn(),
    showBackButton: () => () => {},
  }),
}))

import VehiclesTab from './VehiclesTab'
import PassesTab from './PassesTab'
import PassNewPage from './PassNewPage'

const vehiclesPage = {
  items: [
    {
      id: 1,
      plate_number_original: '01A123BC',
      plate_number_normalized: '01A123BC',
      plate_country: 'UZ',
      plate_type: null,
      brand: 'Chevrolet',
      model: 'Cobalt',
      color: 'белый',
      vehicle_class: null,
      status: 'active',
      blocked_reason: null,
      blocked_by_user_id: null,
      blocked_at: null,
      apartments: [],
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

const emptyPage = { items: [], total: 0, limit: 50, offset: 0 }

describe('TWA Access — VehiclesTab', () => {
  beforeEach(() => server.resetHandlers())

  it('renders vehicle list and "my requests" empty state from API', async () => {
    server.use(
      http.get('*/api/v1/access/my/vehicles', () => HttpResponse.json(vehiclesPage)),
      http.get('*/api/v1/access/my/requests', () => HttpResponse.json(emptyPage)),
    )

    render(<VehiclesTab />)

    expect(await screen.findByText('01A123BC')).toBeInTheDocument()
    expect(screen.getByText(/Chevrolet/)).toBeInTheDocument()
    expect(screen.getByText('Активен')).toBeInTheDocument()
    // Заявок нет
    expect(await screen.findByText('Заявок нет')).toBeInTheDocument()
  })
})

describe('TWA Access — PassesTab cancel', () => {
  beforeEach(() => server.resetHandlers())

  it('cancels an active pass via POST /passes/{id}/cancel', async () => {
    let cancelled: number | null = null
    server.use(
      http.get('*/api/v1/access/my/passes', () =>
        HttpResponse.json({
          items: [
            {
              id: 42,
              pass_type: 'guest',
              apartment_id: 7,
              created_by_user_id: 1,
              zone_id: 1,
              plate_number_original: null,
              plate_number_normalized: null,
              valid_from: null,
              valid_until: '2026-07-01T12:00:00Z',
              max_entries: 1,
              used_entries: 0,
              status: 'active',
              source: 'resident',
              created_at: '2026-06-28T10:00:00Z',
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
      http.post('*/api/v1/access/passes/42/cancel', () => {
        cancelled = 42
        return HttpResponse.json({ ok: true, pass_id: 42, status: 'revoked', replayed: false })
      }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<PassesTab />)

    const cancelBtn = await screen.findByRole('button', { name: 'Отменить' })
    await userEvent.click(cancelBtn)

    await waitFor(() => expect(cancelled).toBe(42))
  })
})

describe('TWA Access — PassNewPage', () => {
  beforeEach(() => server.resetHandlers())

  it('auto-selects the single apartment and POSTs a correct pass body', async () => {
    let captured: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/profile/apartments', () =>
        HttpResponse.json([{ apartment_id: 7, full_address: 'Дом 1, кв. 5' }]),
      ),
      http.post('*/api/v1/access/passes', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 99,
          pass_type: 'taxi',
          apartment_id: 7,
          created_by_user_id: 1,
          zone_id: 1,
          plate_number_original: null,
          plate_number_normalized: null,
          valid_from: null,
          valid_until: '2026-07-01T12:00:00Z',
          max_entries: 1,
          used_entries: 0,
          status: 'active',
          source: 'resident',
          created_at: '2026-06-28T10:00:00Z',
        })
      }),
    )

    render(<PassNewPage />)

    // Single apartment shown (auto-selected, no select buttons).
    expect(await screen.findByText('🏠 Дом 1, кв. 5')).toBeInTheDocument()

    // Pick pass type "Такси".
    await userEvent.click(screen.getByRole('button', { name: 'Такси' }))

    // Set valid_until via the datetime-local input.
    const dt = document.querySelector('input[type="datetime-local"]') as HTMLInputElement
    fireEvent.change(dt, { target: { value: '2026-07-01T15:00' } })

    const submit = screen.getByRole('button', { name: 'Заказать' })
    await waitFor(() => expect(submit).toBeEnabled())
    await userEvent.click(submit)

    await waitFor(() => expect(captured).not.toBeNull())
    expect(captured!.apartment_id).toBe(7)
    expect(captured!.pass_type).toBe('taxi')
    expect(captured!.max_entries).toBe(1)
    expect(typeof captured!.valid_until).toBe('string')
  })
})
