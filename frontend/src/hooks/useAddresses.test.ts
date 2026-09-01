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
  useAddressStats,
  useYards,
  useBuildings,
  useApartments,
  useAllBuildings,
  useAllApartments,
  useApartmentDetail,
  usePendingModeration,
  useCreateYard,
  useUpdateYard,
  useDeleteYard,
  usePurgeYard,
  useCreateBuilding,
  useUpdateBuilding,
  useDeleteBuilding,
  usePurgeBuilding,
  useCreateApartment,
  useUpdateApartment,
  useDeleteApartment,
  usePurgeApartment,
  useBulkCreateApartments,
  useApproveModeration,
  useRejectModeration,
  useAddressesWebSocket,
} from './useAddresses'

// TEST-068 Phase 3: адресные хуки были 0/154 строк — единственный крупный
// data-слой целиком без тестов. Мутации однородны (toast + invalidate),
// поэтому покрываются таблицей: каждая — успех и серверная ошибка.

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

// useAddressesWebSocket подписывается на канал — сокет в jsdom не нужен,
// важен только колбэк, который хук отдаёт подписке.
const wsSpy = vi.hoisted(() => ({
  channel: '' as string,
  onEvent: undefined as ((e: { type: string; data: unknown }) => void) | undefined,
}))
vi.mock('./useWebSocket', () => ({
  useWebSocket: (channel: string, onEvent: (e: { type: string; data: unknown }) => void) => {
    wsSpy.channel = channel
    wsSpy.onEvent = onEvent
  },
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

// ── Queries ──────────────────────────────────────────────────────────

describe('address queries', () => {
  it('useAddressStats fetches KPI', async () => {
    server.use(
      http.get('*/api/v2/addresses/stats', () =>
        HttpResponse.json({ yards: 3, buildings: 7, apartments: 100 }),
      ),
    )
    const { result } = renderHook(() => useAddressStats())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.yards).toBe(3)
  })

  it('useYards fetches the list', async () => {
    server.use(
      http.get('*/api/v2/addresses/yards', () =>
        HttpResponse.json([{ id: 1, name: 'Двор 1' }]),
      ),
    )
    const { result } = renderHook(() => useYards())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })

  it('useBuildings does not fetch while yardId is null', () => {
    // Хендлер не зарегистрирован: onUnhandledRequest="error" упал бы на fetch.
    const { result } = renderHook(() => useBuildings(null))
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('useBuildings fetches once yardId is set', async () => {
    server.use(
      http.get('*/api/v2/addresses/yards/5/buildings', () =>
        HttpResponse.json([{ id: 10, address: 'Дом 1' }]),
      ),
    )
    const { result } = renderHook(() => useBuildings(5))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].id).toBe(10)
  })

  it('useApartments gates on buildingId', async () => {
    const idle = renderHook(() => useApartments(null))
    expect(idle.result.current.fetchStatus).toBe('idle')

    server.use(
      http.get('*/api/v2/addresses/buildings/7/apartments', () =>
        HttpResponse.json([{ id: 70, number: '12' }]),
      ),
    )
    const { result } = renderHook(() => useApartments(7))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('useAllBuildings passes yard filter as query param', async () => {
    let seenYardId: string | null = null
    server.use(
      http.get('*/api/v2/addresses/buildings', ({ request }) => {
        seenYardId = new URL(request.url).searchParams.get('yard_id')
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useAllBuildings(3))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenYardId).toBe('3')
  })

  it('useAllApartments passes both filters', async () => {
    let params: URLSearchParams | null = null
    server.use(
      http.get('*/api/v2/addresses/apartments/all', ({ request }) => {
        params = new URL(request.url).searchParams
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useAllApartments(2, 9))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(params!.get('yard_id')).toBe('2')
    expect(params!.get('building_id')).toBe('9')
  })

  it('useApartmentDetail gates on id and fetches by id', async () => {
    const idle = renderHook(() => useApartmentDetail(null))
    expect(idle.result.current.fetchStatus).toBe('idle')

    server.use(
      http.get('*/api/v2/addresses/apartments/44', () =>
        HttpResponse.json({ id: 44, number: '44' }),
      ),
    )
    const { result } = renderHook(() => useApartmentDetail(44))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.id).toBe(44)
  })

  it('usePendingModeration fetches the queue', async () => {
    server.use(
      http.get('*/api/v2/addresses/moderation', () =>
        HttpResponse.json([{ id: 1, status: 'pending' }]),
      ),
    )
    const { result } = renderHook(() => usePendingModeration())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })
})

// ── Mutations (таблица: у всех контракт toast + invalidate одинаковый) ──

type AnyMutation = { mutate: (v: never) => void; isSuccess: boolean; isError: boolean }

const MUTATIONS: Array<{
  name: string
  hook: () => AnyMutation
  method: 'post' | 'patch' | 'delete'
  path: string
  payload: unknown
}> = [
  { name: 'useCreateYard', hook: useCreateYard as never, method: 'post', path: '*/api/v2/addresses/yards', payload: { name: 'Двор' } },
  { name: 'useUpdateYard', hook: useUpdateYard as never, method: 'patch', path: '*/api/v2/addresses/yards/1', payload: { id: 1, name: 'Двор 2' } },
  { name: 'useDeleteYard', hook: useDeleteYard as never, method: 'delete', path: '*/api/v2/addresses/yards/1', payload: 1 },
  { name: 'usePurgeYard', hook: usePurgeYard as never, method: 'delete', path: '*/api/v2/addresses/yards/1/purge', payload: 1 },
  { name: 'useCreateBuilding', hook: useCreateBuilding as never, method: 'post', path: '*/api/v2/addresses/buildings', payload: { address: 'Дом', yard_id: 1 } },
  { name: 'useUpdateBuilding', hook: useUpdateBuilding as never, method: 'patch', path: '*/api/v2/addresses/buildings/1', payload: { id: 1 } },
  { name: 'useDeleteBuilding', hook: useDeleteBuilding as never, method: 'delete', path: '*/api/v2/addresses/buildings/1', payload: 1 },
  { name: 'usePurgeBuilding', hook: usePurgeBuilding as never, method: 'delete', path: '*/api/v2/addresses/buildings/1/purge', payload: 1 },
  { name: 'useCreateApartment', hook: useCreateApartment as never, method: 'post', path: '*/api/v2/addresses/apartments', payload: { number: '1', building_id: 1 } },
  { name: 'useUpdateApartment', hook: useUpdateApartment as never, method: 'patch', path: '*/api/v2/addresses/apartments/1', payload: { id: 1 } },
  { name: 'useDeleteApartment', hook: useDeleteApartment as never, method: 'delete', path: '*/api/v2/addresses/apartments/1', payload: 1 },
  { name: 'usePurgeApartment', hook: usePurgeApartment as never, method: 'delete', path: '*/api/v2/addresses/apartments/1/purge', payload: 1 },
  { name: 'useBulkCreateApartments', hook: useBulkCreateApartments as never, method: 'post', path: '*/api/v2/addresses/apartments/bulk', payload: { building_id: 1, apartment_numbers: ['1'] } },
  { name: 'useApproveModeration', hook: useApproveModeration as never, method: 'post', path: '*/api/v2/addresses/moderation/1/approve', payload: 1 },
  { name: 'useRejectModeration', hook: useRejectModeration as never, method: 'post', path: '*/api/v2/addresses/moderation/1/reject', payload: { id: 1, comment: 'кривой адрес' } },
]

describe('address mutations', () => {
  it.each(MUTATIONS)('$name: success → toast.success + invalidate', async ({ hook, method, path, payload }) => {
    vi.mocked(toast.success).mockClear()
    server.use(http[method](path, () => HttpResponse.json({ ok: true })))

    const qc = makeClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => hook(), { wrapper: wrapperFor(qc) })
    result.current.mutate(payload as never)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(toast.success).toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalled()
  })

  it.each(MUTATIONS)('$name: server error → toast.error', async ({ hook, method, path, payload }) => {
    vi.mocked(toast.error).mockClear()
    server.use(http[method](path, () => new HttpResponse(null, { status: 500 })))

    const { result } = renderHook(() => hook())
    result.current.mutate(payload as never)

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalled()
  })
})

// ── Real-time ────────────────────────────────────────────────────────

describe('useAddressesWebSocket', () => {
  it('building.* events invalidate address queries; чужие — нет', () => {
    const qc = makeClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    rawRenderHook(() => useAddressesWebSocket(), { wrapper: wrapperFor(qc) })

    expect(wsSpy.channel).toBe('buildings')
    wsSpy.onEvent?.({ type: 'request.updated', data: {} })
    expect(invalidate).not.toHaveBeenCalled()

    wsSpy.onEvent?.({ type: 'building.updated', data: {} })
    const keys = invalidate.mock.calls.map(c => (c[0] as { queryKey: unknown[] }).queryKey[0])
    expect(keys).toEqual(
      expect.arrayContaining(['buildings', 'all-buildings', 'yards', 'address-stats']),
    )
  })
})
