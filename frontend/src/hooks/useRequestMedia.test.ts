import { describe, it, expect, vi, afterEach } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/test/msw/server'
import { apiClient } from '../api/client'
import { fetchFileAsDataUrl } from '../api/fileDataUrl'
import { mediaBlobQueryKey, requestMediaQueryKey, useMediaBlob, useRequestMediaList } from './useRequestMedia'
import { useCreateCallCenterRequest } from './useCallCenter'
import { kanbanQueryKey, useKanbanSnapshot } from './useKanban'

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } })
}
function wrapperFor(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: qc }, children)
}

afterEach(() => vi.restoreAllMocks())

describe('fetchFileAsDataUrl', () => {
  it('возвращает data: URL и MIME блоба', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: new Blob(['hi'], { type: 'image/png' }) })
    const file = await fetchFileAsDataUrl('/api/v2/media/1/file')
    expect(apiClient.get).toHaveBeenCalledWith('/api/v2/media/1/file', { responseType: 'blob' })
    expect(file.type).toBe('image/png')
    expect(file.dataUrl.startsWith('data:image/png;base64,')).toBe(true)
  })
})

describe('useRequestMediaList / useMediaBlob', () => {
  it('список медиа лежит под ключом request-media (его инвалидирует загрузка)', async () => {
    server.use(http.get('*/api/v2/media/request/:n', () => HttpResponse.json([{ id: 1, file_type: 'photo', mime_type: 'image/jpeg' }])))
    const qc = makeClient()
    const { result } = renderHook(() => useRequestMediaList('260101-001'), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(qc.getQueryData(requestMediaQueryKey('260101-001'))).toHaveLength(1)
  })

  it('превью и лайтбокс делят один data:-URL кэш — второй наблюдатель не качает заново', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: new Blob(['x'], { type: 'image/jpeg' }) })
    const qc = makeClient()
    const first = renderHook(() => useMediaBlob(7), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true))
    const second = renderHook(() => useMediaBlob(7), { wrapper: wrapperFor(qc) })
    expect(second.result.current.data).toMatch(/^data:image\/jpeg/)
    expect(get).toHaveBeenCalledTimes(1)
    expect(qc.getQueryData(mediaBlobQueryKey(7))).toBe(first.result.current.data)
  })
})

describe('useKanbanSnapshot', () => {
  it('пишет в тот же ключ, что useKanban без фильтров', async () => {
    server.use(http.get('*/api/v2/requests/kanban', () => HttpResponse.json({ columns: [] })))
    const qc = makeClient()
    const { result } = renderHook(() => useKanbanSnapshot(), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(qc.getQueryData(kanbanQueryKey())).toEqual({ columns: [] })
  })
})

describe('useCreateCallCenterRequest', () => {
  it('создание заявки инвалидирует канбан', async () => {
    server.use(http.post('*/api/v2/callcenter/requests', () => HttpResponse.json({ request_number: '260101-009' })))
    const qc = makeClient()
    qc.setQueryData(kanbanQueryKey({ status: 'Новая' }), { columns: [] })
    const { result } = renderHook(() => useCreateCallCenterRequest(), { wrapper: wrapperFor(qc) })
    await act(() => result.current.mutateAsync({ category: 'plumbing', urgency: 'low', description: '', address: 'a' }))
    expect(qc.getQueryState(kanbanQueryKey({ status: 'Новая' }))?.isInvalidated).toBe(true)
  })
})
