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
  useAllOccurrences,
  useCancelOccurrence,
  useCompleteOccurrence,
  useElevatorOccurrences,
  useGenerateOccurrences,
  useRescheduleOccurrence,
} from './useElevatorCalendar'

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

/** Головы инвалидированных ключей + сам ключ `['elevator', 7]`. */
function invalidatedKeys(spy: ReturnType<typeof vi.spyOn>) {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey)
}

const EXPECTED_AFTER_MUTATION = [
  ['elevator-occurrences', 7],
  ['elevators-occurrences'],
  ['elevator', 7],
  ['elevators'],
  ['elevators-summary'],
]

describe('useElevatorOccurrences / useAllOccurrences (lang)', () => {
  it('передают lang и очищенные фильтры', async () => {
    let url: URL | null = null
    server.use(
      http.get('*/api/v2/elevators/7/occurrences', ({ request }) => {
        url = new URL(request.url)
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useElevatorOccurrences(7, { state: 'planned', kind: undefined }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url!.searchParams.get('lang')).toBe('ru')
    expect(url!.searchParams.get('state')).toBe('planned')
    expect(url!.searchParams.has('kind')).toBe(false)
  })

  it('общий календарь: from/to/state + lang', async () => {
    let url: URL | null = null
    server.use(
      http.get('*/api/v2/elevators/occurrences', ({ request }) => {
        url = new URL(request.url)
        return HttpResponse.json([])
      }),
    )
    const { result } = renderHook(() => useAllOccurrences({ from: '2026-09-01', to: '2026-10-31', state: 'planned' }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url!.searchParams.get('from')).toBe('2026-09-01')
    expect(url!.searchParams.get('to')).toBe('2026-10-31')
    expect(url!.searchParams.get('lang')).toBe('ru')
  })
})

describe('мутации графика инвалидируют оба списка, карточку, реестр и сводку', () => {
  it('complete', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/elevators/occurrences/31/complete', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 31, state: 'done' })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useCompleteOccurrence(7), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 31, comment: 'ок', request_number: null })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toEqual({ comment: 'ок', request_number: null }) // id не уходит в тело
    for (const key of EXPECTED_AFTER_MUTATION) expect(invalidatedKeys(spy)).toContainEqual(key)
    expect(toast.success).toHaveBeenCalledWith(testI18n.t('elevators.toast.completed'))
  })

  it('reschedule', async () => {
    server.use(http.patch('*/api/v2/elevators/occurrences/31', () => HttpResponse.json({ id: 31 })))
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useRescheduleOccurrence(7), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 31, due_on: '2026-11-01' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    for (const key of EXPECTED_AFTER_MUTATION) expect(invalidatedKeys(spy)).toContainEqual(key)
  })

  it('cancel', async () => {
    server.use(http.post('*/api/v2/elevators/occurrences/31/cancel', () => HttpResponse.json({ id: 31 })))
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useCancelOccurrence(7), { wrapper: wrapperFor(qc) })
    result.current.mutate(31)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    for (const key of EXPECTED_AFTER_MUTATION) expect(invalidatedKeys(spy)).toContainEqual(key)
  })

  it('generate', async () => {
    server.use(
      http.post('*/api/v2/elevators/7/occurrences/generate', () => HttpResponse.json([{ id: 40 }, { id: 41 }], { status: 201 })),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useGenerateOccurrences(7), { wrapper: wrapperFor(qc) })
    result.current.mutate({ kind: 'maintenance', start: '2026-10-01', every_months: 1, count: 2 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
    for (const key of EXPECTED_AFTER_MUTATION) expect(invalidatedKeys(spy)).toContainEqual(key)
  })

  it('ошибка: toast.error с detail', async () => {
    server.use(
      http.post('*/api/v2/elevators/occurrences/31/cancel', () =>
        HttpResponse.json({ detail: 'уже выполнено' }, { status: 409 }),
      ),
    )
    const { result } = renderHook(() => useCancelOccurrence(7))
    result.current.mutate(31)
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('уже выполнено')
  })
})
