import { describe, it, expect, vi, beforeEach } from 'vitest'
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
  useBulkConfirmRequests,
  useElevators,
  usePatchElevator,
  useSetElevatorStatus,
} from './useElevators'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

beforeEach(() => {
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

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

describe('useElevators (список)', () => {
  it('передаёт только заполненные фильтры, flag — повторяющимся параметром', async () => {
    let url: URL | null = null
    server.use(
      http.get('*/api/v2/elevators', ({ request }) => {
        url = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0 })
      }),
    )
    const { result } = renderHook(() =>
      useElevators({
        yard_id: 3,
        building_id: undefined,
        status: 'working',
        flag: ['no_contract', 'cert_expired'],
        include_archived: false,
        limit: 50,
        offset: 0,
      }),
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const params = url!.searchParams
    expect(params.get('yard_id')).toBe('3')
    expect(params.has('building_id')).toBe(false)
    expect(params.get('status')).toBe('working')
    expect(params.getAll('flag')).toEqual(['no_contract', 'cert_expired'])
    expect(params.get('include_archived')).toBe('false')
    expect(params.get('limit')).toBe('50')
    expect(params.get('offset')).toBe('0')
    expect(result.current.data?.total).toBe(0)
  })
})

describe('useSetElevatorStatus', () => {
  it('успех: инвалидирует detail/list/events/summary и показывает тост с notified_residents', async () => {
    server.use(
      http.put('*/api/v2/elevators/7/status', () =>
        HttpResponse.json({
          changed: true, old_status: 'working', new_status: 'not_working',
          status_since: '2026-09-05T10:00:00Z', notified_residents: 12,
        }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useSetElevatorStatus(7), { wrapper: wrapperFor(qc) })
    result.current.mutate({ status: 'not_working', reason: 'застрял' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey)
    expect(keys).toContainEqual(['elevators'])
    expect(keys).toContainEqual(['elevator', 7])
    expect(keys).toContainEqual(['elevator-events', 7])
    expect(keys).toContainEqual(['elevators-summary'])
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('12'))
  })
})

describe('useBulkConfirmRequests', () => {
  it('возвращает per-item результат', async () => {
    server.use(
      http.post('*/api/v2/elevators/requests/bulk-confirm', () =>
        HttpResponse.json([
          { request_number: '260905-001', ok: true, error_kind: null, error: null },
          { request_number: '260905-002', ok: false, error_kind: 'wrong_status', error: 'статус Новая' },
        ]),
      ),
    )
    const { result } = renderHook(() => useBulkConfirmRequests(7))
    result.current.mutate(['260905-001', '260905-002'])
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
    expect(result.current.data?.[1].ok).toBe(false)
    expect(result.current.data?.[1].error_kind).toBe('wrong_status')
  })
})

describe('usePatchElevator', () => {
  it('409 (гонка версий): toast.error с подсказкой обновить карточку', async () => {
    server.use(
      http.patch('*/api/v2/elevators/7', () =>
        HttpResponse.json({ detail: 'version conflict' }, { status: 409 }),
      ),
    )
    const { result } = renderHook(() => usePatchElevator(7))
    result.current.mutate({ manufacturer: 'OTIS', expected_version: 3 })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith(testI18n.t('elevators.toast.conflict'))
  })

  it('иная ошибка: показывает detail из ответа', async () => {
    server.use(
      http.patch('*/api/v2/elevators/7', () =>
        HttpResponse.json({ detail: 'подъезд вне диапазона' }, { status: 422 }),
      ),
    )
    const { result } = renderHook(() => usePatchElevator(7))
    result.current.mutate({ entrance_number: 99 })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('подъезд вне диапазона')
  })
})
