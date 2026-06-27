import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { waitFor, renderHook as rawRenderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { renderHook, testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useAccessEvents,
  useAccessVehicles,
  useResolveEvent,
  useCreateVehicle,
  useUpdateVehicleStatus,
  useCreateTaxiPass,
  useReviewRequest,
} from './useAccessRegistry'

// Тосты мутаций мокаем, чтобы (а) не нужен смонтированный <Toaster> и (б) можно
// проверить текст (i18n) сообщения об успехе/ошибке.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

// Свой QueryClient + провайдеры — чтобы шпионить за invalidateQueries (стандартный
// renderHook из test-utils создаёт клиент внутри и наружу его не отдаёт).
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
}
function wrapperFor(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(I18nextProvider, { i18n: testI18n }, children),
    )
}

// Хуки реестра доступа поверх MSW (как useEmployees.test). accessClient бьёт по
// same-origin baseURL .../api/v1/access; wildcard-хэндлеры это матчат.

describe('useAccessEvents', () => {
  it('возвращает конверт {items,total,...}', async () => {
    server.use(
      http.get('*/api/v1/access/events', () =>
        HttpResponse.json({
          items: [{ id: 1, event_id: 'E-1', decision: 'allow', captured_at: '2026-06-26T10:00:00Z' }],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    )
    const { result } = renderHook(() => useAccessEvents({ limit: 50, offset: 0 }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items).toHaveLength(1)
    expect(result.current.data?.total).toBe(1)
  })

  it('прокидывает фильтр decision в query-параметры запроса', async () => {
    let seenUrl = ''
    server.use(
      http.get('*/api/v1/access/events', ({ request }) => {
        seenUrl = request.url
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })
      }),
    )
    const { result } = renderHook(() =>
      useAccessEvents({ decision: 'manual_review', limit: 50, offset: 0 }),
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = new URL(seenUrl)
    expect(url.searchParams.get('decision')).toBe('manual_review')
    expect(url.searchParams.get('limit')).toBe('50')
  })
})

describe('useAccessVehicles', () => {
  it('возвращает список авто', async () => {
    server.use(
      http.get('*/api/v1/access/vehicles', () =>
        HttpResponse.json({
          items: [
            {
              id: 7,
              plate_number_original: '01A123BC',
              plate_number_normalized: '01A123BC',
              brand: 'Chevrolet',
              model: 'Cobalt',
              status: 'active',
              apartments: [],
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    )
    const { result } = renderHook(() => useAccessVehicles({ limit: 50, offset: 0 }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items[0].brand).toBe('Chevrolet')
  })
})

describe('useResolveEvent', () => {
  it('POST резолюции события (manual_open)', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/events/E-9/resolve', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true, decision_id: 5, status: 'allowed' })
      }),
    )
    const { result } = renderHook(() => useResolveEvent())
    result.current.mutate({
      eventId: 'E-9',
      payload: { action: 'manual_open', reason: 'гость', barrier_id: 1, decision_id: 5 },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ action: 'manual_open', barrier_id: 1, decision_id: 5 })
  })
})

// ── Мутации менеджера ────────────────────────────────────────────────────────
describe('useCreateVehicle', () => {
  it('POST /vehicles с телом + инвалидирует access-vehicles + toast успеха', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/vehicles', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            id: 10,
            plate_number_original: '01A123BC',
            plate_number_normalized: '01A123BC',
            status: 'active',
            apartments: [],
          },
          { status: 201 },
        )
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useCreateVehicle(), { wrapper: wrapperFor(qc) })
    result.current.mutate({
      plate_number_original: '01A123BC',
      apartment_id: 5,
      relation_type: 'owner',
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({
      plate_number_original: '01A123BC',
      apartment_id: 5,
      relation_type: 'owner',
    })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-vehicles'] })
    expect(toast.success).toHaveBeenCalledWith('Автомобиль добавлен')
  })

  it('409 → понятный toast «авто уже существует»', async () => {
    server.use(
      http.post('*/api/v1/access/vehicles', () =>
        HttpResponse.json({ detail: 'duplicate' }, { status: 409 }),
      ),
    )
    const qc = makeClient()
    const { result } = rawRenderHook(() => useCreateVehicle(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ plate_number_original: '01A123BC' })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('Такой автомобиль уже существует')
  })
})

describe('useUpdateVehicleStatus', () => {
  it('PATCH /vehicles/{id}/status с reason + инвалидирует список и деталь', async () => {
    let body: unknown = null
    server.use(
      http.patch('*/api/v1/access/vehicles/10/status', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          id: 10,
          plate_number_original: '01A123BC',
          plate_number_normalized: '01A123BC',
          status: 'blocked',
          apartments: [],
        })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useUpdateVehicleStatus(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ vehicleId: 10, payload: { status: 'blocked', reason: 'долг' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ status: 'blocked', reason: 'долг' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-vehicles'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-vehicle-detail'] })
    expect(toast.success).toHaveBeenCalledWith('Автомобиль заблокирован')
  })
})

describe('useCreateTaxiPass', () => {
  it('POST /passes/taxi с телом + инвалидирует access-passes', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/passes/taxi', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            id: 3,
            pass_type: 'taxi',
            apartment_id: 5,
            zone_id: 1,
            valid_until: '2026-07-01T10:00:00.000Z',
            max_entries: 1,
            used_entries: 0,
            status: 'active',
            created_at: '2026-06-27T10:00:00Z',
          },
          { status: 201 },
        )
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useCreateTaxiPass(), { wrapper: wrapperFor(qc) })
    result.current.mutate({
      apartment_id: 5,
      zone_id: 1,
      valid_until: '2026-07-01T10:00:00.000Z',
      max_entries: 1,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ apartment_id: 5, zone_id: 1, max_entries: 1 })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-passes'] })
    expect(toast.success).toHaveBeenCalledWith('Taxi-пропуск создан')
  })
})

describe('useReviewRequest', () => {
  it('POST /requests/{id}/review (approve) + инвалидирует заявки и авто', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/requests/42/review', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          ok: true,
          request_id: 42,
          status: 'approved',
          vehicle_id: 10,
          replayed: false,
        })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useReviewRequest(), { wrapper: wrapperFor(qc) })
    result.current.mutate({
      requestId: 42,
      payload: { action: 'approve', comment: 'ок', zone_id: 1 },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ action: 'approve', comment: 'ок', zone_id: 1 })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-requests'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-vehicles'] })
    expect(toast.success).toHaveBeenCalledWith('Заявка подтверждена')
  })

  it('reject шлёт action=reject + toast отклонения', async () => {
    server.use(
      http.post('*/api/v1/access/requests/42/review', () =>
        HttpResponse.json({
          ok: true,
          request_id: 42,
          status: 'rejected',
          vehicle_id: null,
          replayed: false,
        }),
      ),
    )
    const qc = makeClient()
    const { result } = rawRenderHook(() => useReviewRequest(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ requestId: 42, payload: { action: 'reject', comment: 'нет' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith('Заявка отклонена')
  })
})
