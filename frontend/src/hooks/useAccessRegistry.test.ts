import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useAccessEvents,
  useAccessVehicles,
  useResolveEvent,
} from './useAccessRegistry'

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
