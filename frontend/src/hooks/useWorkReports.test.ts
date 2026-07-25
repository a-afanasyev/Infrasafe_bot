import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { renderHook as rawRenderHook } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { renderHook, testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useWorkReports,
  usePatchWorkReport,
  useUpdateWorkReportsSettings,
  useSyncWorkReports,
  usePublishWorkReport,
  useRejectWorkReport,
} from './useWorkReports'

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

const REPORT = {
  id: 1,
  request_number: '260701-001',
  category_key: 'plumbing',
  address_public: 'дом 1',
  performed_at: '2026-07-01T10:00:00',
  before_media_ids: [1],
  after_media_ids: [2],
  media_meta: [],
  locked_media_ids: [],
  status: 'pending',
  source: 'manual',
  reject_reason: null,
  created_at: '2026-07-01T10:00:00',
  published_at: null,
  media_synced_at: null,
  state_changed_at: null,
  moderated_by: null,
}

describe('useWorkReports', () => {
  it('передаёт status/limit/offset в query params, когда заданы', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('*/api/v2/work-reports', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 5 })
      }),
    )
    const { result } = renderHook(() =>
      useWorkReports({ status: 'pending', limit: 10, offset: 5 }),
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedUrl?.searchParams.get('status')).toBe('pending')
    expect(capturedUrl?.searchParams.get('limit')).toBe('10')
    expect(capturedUrl?.searchParams.get('offset')).toBe('5')
  })

  it('не передаёт params, которые не заданы вызывающим', async () => {
    let capturedUrl: URL | null = null
    server.use(
      http.get('*/api/v2/work-reports', ({ request }) => {
        capturedUrl = new URL(request.url)
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })
      }),
    )
    const { result } = renderHook(() => useWorkReports())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedUrl?.searchParams.has('status')).toBe(false)
    expect(capturedUrl?.searchParams.has('limit')).toBe(false)
    expect(capturedUrl?.searchParams.has('offset')).toBe(false)
  })
})

describe('usePatchWorkReport', () => {
  it('шлёт PATCH на /{id} с телом БЕЗ id (id вырезается через деструктуризацию)', async () => {
    let capturedBody: Record<string, unknown> | null = null
    let capturedUrl: string | null = null
    server.use(
      http.patch('*/api/v2/work-reports/:id', async ({ request, params }) => {
        capturedUrl = String(params.id)
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(REPORT)
      }),
    )
    const { result } = renderHook(() => usePatchWorkReport())
    result.current.mutate({ id: 1, category_key: 'electric' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(capturedUrl).toBe('1')
    expect(capturedBody).toEqual({ category_key: 'electric' })
    expect(capturedBody).not.toHaveProperty('id')
    expect(toast.success).toHaveBeenCalled()
  })
})

describe('useUpdateWorkReportsSettings', () => {
  it('инвалидирует ["board-config"], НЕ ["work-reports"]', async () => {
    server.use(
      http.put('*/api/v2/work-reports/settings', () =>
        HttpResponse.json({ autopost: true, autopost_since: null, limit: 6, title: { ru: '', uz: '' } }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useUpdateWorkReportsSettings(), {
      wrapper: wrapperFor(qc),
    })
    result.current.mutate({ autopost: true })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0])
    expect(keys).toContain('board-config')
    expect(keys).not.toContain('work-reports')
  })
})

describe('useSyncWorkReports', () => {
  it('POST /sync, успех инвалидирует work-reports и показывает тост', async () => {
    server.use(
      http.post('*/api/v2/work-reports/sync', () =>
        HttpResponse.json({ sync: {}, revoked: 0, reconcile: null }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useSyncWorkReports(), { wrapper: wrapperFor(qc) })
    result.current.mutate()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0])
    expect(keys).toContain('work-reports')
    expect(toast.success).toHaveBeenCalled()
  })
})

describe('usePublishWorkReport', () => {
  it('POST /{id}/publish, ошибка показывает detail из ответа', async () => {
    server.use(
      http.post('*/api/v2/work-reports/1/publish', () =>
        HttpResponse.json({ detail: 'заблокированные media' }, { status: 409 }),
      ),
    )
    const { result } = renderHook(() => usePublishWorkReport())
    result.current.mutate(1)
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('заблокированные media')
  })
})

describe('useRejectWorkReport', () => {
  it('POST /{id}/reject с телом { reason }', async () => {
    let capturedBody: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/work-reports/1/reject', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(REPORT)
      }),
    )
    const { result } = renderHook(() => useRejectWorkReport())
    result.current.mutate({ id: 1, reason: 'плохое фото' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(capturedBody).toEqual({ reason: 'плохое фото' })
  })
})
