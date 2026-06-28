import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { waitFor, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useAccessSpots,
  useCreateSpot,
  useUpdateSpot,
  useAccessSpotAssignments,
  useCreateSpotAssignment,
  useUpdateSpotAssignment,
  useZoneOccupancy,
} from './useParkingAdmin'

// Тосты мутаций мокаем (как в useAccessEquipment.test) — проверяем текст i18n.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

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

describe('useAccessSpots', () => {
  it('GET /admin/spots с фильтром zone_id', async () => {
    let seenUrl = ''
    server.use(
      http.get('*/api/v1/access/admin/spots', ({ request }) => {
        seenUrl = request.url
        return HttpResponse.json({
          items: [{ id: 1, zone_id: 5, code: 'A-01', status: 'active' }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      }),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useAccessSpots({ zone_id: 5 }), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenUrl).toContain('/admin/spots')
    expect(seenUrl).toContain('zone_id=5')
    expect(result.current.data?.items[0].code).toBe('A-01')
  })
})

describe('useCreateSpot', () => {
  it('POST /admin/spots + инвалидирует access-spots + toast', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/spots', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 2, zone_id: 5, code: 'A-02', status: 'active' }, { status: 201 })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateSpot(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ zone_id: 5, code: 'A-02' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ zone_id: 5, code: 'A-02' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-spots'] })
    expect(toast.success).toHaveBeenCalledWith('Место создано')
  })

  it('409 → toast «уже существует»', async () => {
    server.use(
      http.post('*/api/v1/access/admin/spots', () =>
        HttpResponse.json({ detail: 'duplicate' }, { status: 409 }),
      ),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useCreateSpot(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ zone_id: 5, code: 'A-02' })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('Такой элемент уже существует')
  })
})

describe('useUpdateSpot', () => {
  it('PATCH /admin/spots/{id} с code/status + инвалидирует', async () => {
    let body: unknown = null
    server.use(
      http.patch('*/api/v1/access/admin/spots/7', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 7, zone_id: 5, code: 'A-07', status: 'inactive' })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useUpdateSpot(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 7, payload: { status: 'inactive' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ status: 'inactive' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-spots'] })
    expect(toast.success).toHaveBeenCalledWith('Изменения сохранены')
  })
})

describe('useAccessSpotAssignments', () => {
  it('GET /admin/spot-assignments с фильтрами spot_id/apartment_id', async () => {
    let seenUrl = ''
    server.use(
      http.get('*/api/v1/access/admin/spot-assignments', ({ request }) => {
        seenUrl = request.url
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })
      }),
    )
    const qc = makeClient()
    const { result } = renderHook(
      () => useAccessSpotAssignments({ spot_id: 3, apartment_id: 12 }),
      { wrapper: wrapperFor(qc) },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenUrl).toContain('spot_id=3')
    expect(seenUrl).toContain('apartment_id=12')
  })
})

describe('useCreateSpotAssignment', () => {
  it('POST /admin/spot-assignments + инвалидирует + toast', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/spot-assignments', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          { id: 1, spot_id: 3, apartment_id: 12, ownership_type: 'rented', valid_from: null, valid_until: '2026-12-31T00:00:00Z', status: 'active', approved_by_user_id: 7, approved_at: null },
          { status: 201 },
        )
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateSpotAssignment(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ spot_id: 3, apartment_id: 12, ownership_type: 'rented', valid_until: '2026-12-31T00:00:00Z' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ spot_id: 3, apartment_id: 12, ownership_type: 'rented', valid_until: '2026-12-31T00:00:00Z' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-spot-assignments'] })
    expect(toast.success).toHaveBeenCalledWith('Место закреплено')
  })
})

describe('useUpdateSpotAssignment', () => {
  it('PATCH status=revoked → toast «отозвано» + инвалидирует', async () => {
    let body: unknown = null
    server.use(
      http.patch('*/api/v1/access/admin/spot-assignments/4', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 4, spot_id: 1, apartment_id: 23, ownership_type: 'owned', valid_from: null, valid_until: null, status: 'revoked', approved_by_user_id: 7, approved_at: null })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useUpdateSpotAssignment(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 4, payload: { status: 'revoked' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ status: 'revoked' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-spot-assignments'] })
    expect(toast.success).toHaveBeenCalledWith('Закрепление отозвано')
  })

  it('PATCH valid_until (продление) → toast «сохранено»', async () => {
    server.use(
      http.patch('*/api/v1/access/admin/spot-assignments/4', () =>
        HttpResponse.json({ id: 4, spot_id: 1, apartment_id: 23, ownership_type: 'rented', valid_from: null, valid_until: '2027-01-01T00:00:00Z', status: 'active', approved_by_user_id: 7, approved_at: null }),
      ),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useUpdateSpotAssignment(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 4, payload: { valid_until: '2027-01-01T00:00:00Z' } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalledWith('Изменения сохранены')
  })
})

describe('useZoneOccupancy', () => {
  it('GET /admin/zones/{id}/occupancy → occupancy/capacity', async () => {
    server.use(
      http.get('*/api/v1/access/admin/zones/2/occupancy', () =>
        HttpResponse.json({ zone_id: 2, entries: 120, exits: 63, occupancy: 57, capacity: 80 }),
      ),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useZoneOccupancy(2), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.occupancy).toBe(57)
    expect(result.current.data?.capacity).toBe(80)
  })
})
