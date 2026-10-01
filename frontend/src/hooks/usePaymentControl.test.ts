import { describe, it, expect, vi, afterEach } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import {
  paymentKeys,
  useApartmentPayment,
  useChangePaymentImport,
  useRefreshPaymentControl,
  useUploadPaymentImport,
} from './usePaymentControl'

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } })
}
function wrapperFor(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: qc }, children)
}

afterEach(() => vi.restoreAllMocks())

describe('usePaymentControl', () => {
  it('useApartmentPayment: без лицевого счёта не запрашивает', () => {
    const get = vi.spyOn(apiClient, 'get')
    const qc = makeClient()
    const { result } = renderHook(() => useApartmentPayment(5, null), { wrapper: wrapperFor(qc) })
    expect(result.current.fetchStatus).toBe('idle')
    expect(get).not.toHaveBeenCalled()
  })

  it('useApartmentPayment: ключ под префиксом apartment-payment', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { status: 'no_data', current: null } })
    const qc = makeClient()
    const { result } = renderHook(() => useApartmentPayment(5, '001'), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.get).toHaveBeenCalledWith('/api/v2/payment-control/apartments/5')
    expect(qc.getQueryData(paymentKeys.apartmentOf(5, '001'))).toEqual({ status: 'no_data', current: null })
  })

  it('useRefreshPaymentControl сбрасывает раздел, карточку квартиры и таблицу балансов', async () => {
    const qc = makeClient()
    const keys = [
      paymentKeys.importsPage(0),
      paymentKeys.importPage(3, 0),
      paymentKeys.accountOf('001'),
      paymentKeys.apartmentOf(5, '001'),
      [...paymentKeys.apartmentBalances, ['001']],
    ]
    for (const k of keys) qc.setQueryData(k, {})
    const { result } = renderHook(() => useRefreshPaymentControl(), { wrapper: wrapperFor(qc) })
    await act(() => result.current())
    for (const k of keys) expect(qc.getQueryState(k)?.isInvalidated).toBe(true)
  })

  it('useUploadPaymentImport шлёт multipart с обрезанным source и отдаёт отчёт', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { id: 9 } })
    const onUploaded = vi.fn()
    const qc = makeClient()
    const { result } = renderHook(() => useUploadPaymentImport(onUploaded), { wrapper: wrapperFor(qc) })
    const file = new File(['x'], 'debt.xlsx')
    await act(() => result.current.mutateAsync({ kind: 'balances', asOf: '2026-10-01', source: ' Accounting ', file }))
    const [url, body] = post.mock.calls[0] as [string, FormData]
    expect(url).toBe('/api/v2/payment-control/imports/preview')
    expect(body.get('source')).toBe('Accounting')
    expect(body.get('file')).toBeInstanceOf(File)
    expect(onUploaded).toHaveBeenCalledWith({ id: 9 }, expect.anything(), undefined, expect.anything())
  })

  it('useChangePaymentImport: деактивация несёт причину, активация — без тела', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} })
    const onChanged = vi.fn()
    const qc = makeClient()
    const { result } = renderHook(() => useChangePaymentImport(onChanged), { wrapper: wrapperFor(qc) })
    await act(() => result.current.mutateAsync({ importId: 3, action: 'deactivate', reason: ' дубль ' }))
    await act(() => result.current.mutateAsync({ importId: 3, action: 'activate', reason: '' }))
    expect(post).toHaveBeenNthCalledWith(1, '/api/v2/payment-control/imports/3/deactivate', { reason: 'дубль' })
    expect(post).toHaveBeenNthCalledWith(2, '/api/v2/payment-control/imports/3/activate', undefined)
    expect(onChanged).toHaveBeenCalledTimes(2)
  })
})
