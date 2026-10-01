import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { act, waitFor, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  categoryChangeWarning,
  useAssignRequestExecutor,
  useRequestMutations,
  type CategoryChangeOut,
} from './useRequestMutations'
import { requestCommentsQueryKey, requestQueryKey, useRequest, useRequestComments } from './useRequestDetail'
import { kanbanQueryKey } from './useKanban'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
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

function categoryOut(over: Partial<CategoryChangeOut> = {}): CategoryChangeOut {
  return {
    no_op: false,
    new_category: 'plumbing',
    redispatched: false,
    executor_spec_mismatch: false,
    can_reassign: true,
    ...over,
  }
}

/** Ключи, которые читают карточка/канбан — заранее положены в кэш «свежими». */
function seed(qc: QueryClient, n: string) {
  qc.setQueryData(requestQueryKey(n), { request_number: n })
  qc.setQueryData(requestCommentsQueryKey(n), [])
  qc.setQueryData(kanbanQueryKey({ status: 'Новая' }), { columns: [] })
  qc.setQueryData(['employees', 'page'], [])
}
const stale = (qc: QueryClient, key: readonly unknown[]) => qc.getQueryState(key)?.isInvalidated

beforeEach(() => {
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
  vi.mocked(toast.info).mockClear()
})

describe('categoryChangeWarning', () => {
  it('no_op и обычный передиспетч — без баннера', () => {
    expect(categoryChangeWarning(categoryOut({ no_op: true, executor_spec_mismatch: true }))).toBeNull()
    expect(categoryChangeWarning(categoryOut({ dispatch_kind: 'assigned' }))).toBeNull()
  })

  it('несоответствие специализации важнее «без группы»', () => {
    expect(categoryChangeWarning(categoryOut({ executor_spec_mismatch: true, dispatch_kind: 'failed' })))
      .toEqual({ kind: 'mismatch', canReassign: true })
  })

  it.each(['disabled', 'failed', 'no_spec'])('dispatch_kind=%s → unassigned', (kind) => {
    expect(categoryChangeWarning(categoryOut({ dispatch_kind: kind, can_reassign: false })))
      .toEqual({ kind: 'unassigned', canReassign: false })
  })
})

describe('useRequest / useRequestComments', () => {
  it('читают карточку и комментарии по общим ключам', async () => {
    server.use(
      http.get('*/api/v2/requests/:n/comments', () => HttpResponse.json([{ id: 1, comment_text: 'x', is_internal: true, created_at: '' }])),
      http.get('*/api/v2/requests/:n', ({ params }) => HttpResponse.json({ request_number: params.n })),
    )
    const qc = makeClient()
    const { result } = renderHook(() => ({ req: useRequest('260101-001'), comments: useRequestComments('260101-001') }), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.comments.isSuccess && result.current.req.isSuccess).toBe(true))
    expect(qc.getQueryData(requestQueryKey('260101-001'))).toEqual({ request_number: '260101-001' })
    expect(qc.getQueryData(requestCommentsQueryKey('260101-001'))).toHaveLength(1)
  })

  it('без номера заявки не запрашивают', () => {
    const qc = makeClient()
    const { result } = renderHook(() => useRequest(null), { wrapper: wrapperFor(qc) })
    expect(result.current.fetchStatus).toBe('idle')
  })
})

describe('useRequestMutations', () => {
  const N = '260101-001'

  it('updateRequest: PATCH карточки, инвалидирует карточку и канбан (все фильтры), зовёт onUpdated', async () => {
    let body: unknown = null
    server.use(http.patch('*/api/v2/requests/:n', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({})
    }))
    const qc = makeClient()
    seed(qc, N)
    const onUpdated = vi.fn()
    const { result } = renderHook(() => useRequestMutations(N, { onUpdated }), { wrapper: wrapperFor(qc) })
    await act(() => result.current.updateRequest.mutateAsync({ urgency: 'high' }))
    expect(body).toEqual({ urgency: 'high' })
    expect(onUpdated).toHaveBeenCalledOnce()
    expect(toast.success).toHaveBeenCalled()
    expect(stale(qc, requestQueryKey(N))).toBe(true)
    expect(stale(qc, kanbanQueryKey({ status: 'Новая' }))).toBe(true)
    expect(stale(qc, requestCommentsQueryKey(N))).toBe(false)
  })

  it('changeCategory no_op: info-тост, обработчик получает ответ, кэш не трогается', async () => {
    server.use(http.patch('*/api/v2/requests/:n/category', () => HttpResponse.json(categoryOut({ no_op: true }))))
    const qc = makeClient()
    seed(qc, N)
    const onCategoryChanged = vi.fn()
    const { result } = renderHook(() => useRequestMutations(N, { onCategoryChanged }), { wrapper: wrapperFor(qc) })
    await act(() => result.current.changeCategory.mutateAsync('plumbing'))
    expect(toast.info).toHaveBeenCalled()
    expect(onCategoryChanged).toHaveBeenCalledWith(expect.objectContaining({ no_op: true }))
    expect(stale(qc, requestQueryKey(N))).toBe(false)
  })

  it('changeCategory: инвалидирует карточку, канбан и комментарии', async () => {
    server.use(http.patch('*/api/v2/requests/:n/category', () => HttpResponse.json(categoryOut())))
    const qc = makeClient()
    seed(qc, N)
    const { result } = renderHook(() => useRequestMutations(N), { wrapper: wrapperFor(qc) })
    await act(() => result.current.changeCategory.mutateAsync('plumbing'))
    expect(stale(qc, requestQueryKey(N))).toBe(true)
    expect(stale(qc, kanbanQueryKey({ status: 'Новая' }))).toBe(true)
    expect(stale(qc, requestCommentsQueryKey(N))).toBe(true)
  })

  it('postComment: внутренняя заметка, инвалидирует только комментарии', async () => {
    let body: unknown = null
    server.use(http.post('*/api/v2/requests/:n/comments', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ id: 2 })
    }))
    const qc = makeClient()
    seed(qc, N)
    const onCommentPosted = vi.fn()
    const { result } = renderHook(() => useRequestMutations(N, { onCommentPosted }), { wrapper: wrapperFor(qc) })
    await act(() => result.current.postComment.mutateAsync('note'))
    expect(body).toEqual({ text: 'note', is_internal: true })
    expect(onCommentPosted).toHaveBeenCalledOnce()
    expect(stale(qc, requestCommentsQueryKey(N))).toBe(true)
    expect(stale(qc, requestQueryKey(N))).toBe(false)
  })

  it('remindApplicant: ошибка сервера — error-тост с причиной', async () => {
    server.use(http.post('*/api/v2/requests/:n/remind-applicant', () =>
      HttpResponse.json({ detail: 'Житель заблокировал бота' }, { status: 409 })))
    const qc = makeClient()
    const { result } = renderHook(() => useRequestMutations(N), { wrapper: wrapperFor(qc) })
    await act(async () => {
      await result.current.remindApplicant.mutateAsync().catch(() => undefined)
    })
    expect(toast.error).toHaveBeenCalledWith(expect.any(String), { description: 'Житель заблокировал бота' })
  })
})

describe('useAssignRequestExecutor', () => {
  const N = '260101-002'

  it.each([
    [7, { executor_id: 7 }],
    ['duty' as const, { status: 'В работе', assign_to_duty: true }],
  ])('executor=%s → тело PATCH %j; инвалидирует канбан, карточку и сотрудников', async (executor, expected) => {
    let body: unknown = null
    server.use(http.patch('*/api/v2/requests/:n', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({})
    }))
    const qc = makeClient()
    seed(qc, N)
    const onSuccess = vi.fn()
    const { result } = renderHook(() => useAssignRequestExecutor({ onSuccess }), { wrapper: wrapperFor(qc) })
    await act(() => result.current.mutateAsync({ requestNumber: N, executor }))
    expect(body).toEqual(expected)
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(stale(qc, requestQueryKey(N))).toBe(true)
    expect(stale(qc, kanbanQueryKey({ status: 'Новая' }))).toBe(true)
    expect(stale(qc, ['employees', 'page'])).toBe(true)
  })

  it('ошибка — onError с исключением', async () => {
    server.use(http.patch('*/api/v2/requests/:n', () => HttpResponse.json({ detail: 'нет дежурного' }, { status: 409 })))
    const qc = makeClient()
    const onError = vi.fn()
    const { result } = renderHook(() => useAssignRequestExecutor({ onError }), { wrapper: wrapperFor(qc) })
    await act(async () => {
      await result.current.mutateAsync({ requestNumber: N, executor: 'duty' }).catch(() => undefined)
    })
    expect(onError).toHaveBeenCalledOnce()
  })
})
