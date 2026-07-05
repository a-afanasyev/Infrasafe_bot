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
  useCreateIssue,
  useCreateMaterial,
  useMaterialsStock,
  useProcurement,
} from './useMaterials'

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

describe('useMaterialsStock', () => {
  it('возвращает остатки с low_stock-флагом', async () => {
    server.use(
      http.get('*/api/v2/materials/stock', () =>
        HttpResponse.json([
          {
            material_id: 1, name: 'Кабель', unit: 'm', category: null,
            min_stock: '10.000', stock: '4.000', stock_value: '400.00', low_stock: true,
          },
        ]),
      ),
    )
    const { result } = renderHook(() => useMaterialsStock())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].low_stock).toBe(true)
    expect(result.current.data?.[0].stock).toBe('4.000')
  })
})

describe('useProcurement', () => {
  it('возвращает дефицит и открытые заявки в «Закуп»', async () => {
    server.use(
      http.get('*/api/v2/materials/procurement', () =>
        HttpResponse.json({
          deficit: [{ material_id: 1, name: 'Кабель', unit: 'm', stock: '3', min_stock: '10', to_buy: '7' }],
          open_purchase_requests: [
            { request_number: '260705-002', requested_materials: 'гвозди', executor_name: 'Иван' },
          ],
        }),
      ),
    )
    const { result } = renderHook(() => useProcurement())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.deficit[0].to_buy).toBe('7')
    expect(result.current.data?.open_purchase_requests[0].request_number).toBe('260705-002')
  })
})

describe('useCreateIssue', () => {
  it('успех: инвалидирует ключи склада и показывает тост', async () => {
    server.use(
      http.post('*/api/v2/materials/issues', () =>
        HttpResponse.json({ id: 1, total_cost: '600.00' }, { status: 201 }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = rawRenderHook(() => useCreateIssue(), { wrapper: wrapperFor(qc) })
    result.current.mutate({
      material_id: 1, qty: '5', doc_type: 'request', request_number: '260705-001',
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0])
    expect(keys).toContain('materials-stock')
    expect(keys).toContain('materials-operations')
    expect(keys).toContain('materials-procurement')
    expect(toast.success).toHaveBeenCalled()
  })

  it('409 (нехватка остатка): показывает detail из ответа', async () => {
    server.use(
      http.post('*/api/v2/materials/issues', () =>
        HttpResponse.json({ detail: 'недостаточно остатка: доступно 2' }, { status: 409 }),
      ),
    )
    const { result } = renderHook(() => useCreateIssue())
    result.current.mutate({
      material_id: 1, qty: '5', doc_type: 'request', request_number: '260705-001',
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('недостаточно остатка: доступно 2')
  })
})

describe('useCreateMaterial', () => {
  it('409 (дубль имени): показывает detail', async () => {
    server.use(
      http.post('*/api/v2/materials', () =>
        HttpResponse.json({ detail: 'материал «Кабель» уже существует' }, { status: 409 }),
      ),
    )
    const { result } = renderHook(() => useCreateMaterial())
    result.current.mutate({ name: 'Кабель', unit: 'm' })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('материал «Кабель» уже существует')
  })
})
