import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { AccountBalance, PaymentImport } from '../types/paymentControl'

const BASE = '/api/v2/payment-control'

/**
 * Ключи кэша контроля платежей — одно место на раздел и карточку квартиры
 * (A9-P3-21). Активация/деактивация импорта обязана сбросить их все, плюс
 * батч-балансы таблицы квартир (`useApartmentBalances`).
 */
export const paymentKeys = {
  imports: ['payment-imports'] as const,
  importsPage: (offset: number) => ['payment-imports', offset] as const,
  import: ['payment-import'] as const,
  importPage: (importId: number | null, rowOffset: number) => ['payment-import', importId, rowOffset] as const,
  account: ['payment-account'] as const,
  accountOf: (account: string) => ['payment-account', account] as const,
  apartment: ['apartment-payment'] as const,
  apartmentOf: (apartmentId: number, accountNumber?: string | null) =>
    ['apartment-payment', apartmentId, accountNumber] as const,
  apartmentBalances: ['apartment-balances'] as const,
}

export function usePaymentImports(offset: number) {
  return useQuery<PaymentImport[]>({
    queryKey: paymentKeys.importsPage(offset),
    queryFn: () => apiClient.get(`${BASE}/imports`, { params: { offset } }).then(r => r.data),
    retry: false,
  })
}

export function usePaymentImport(importId: number | null, rowOffset: number) {
  return useQuery<PaymentImport>({
    queryKey: paymentKeys.importPage(importId, rowOffset),
    queryFn: () => apiClient.get(`${BASE}/imports/${importId}`, { params: { offset: rowOffset } }).then(r => r.data),
    enabled: !!importId,
    retry: false,
  })
}

export function usePaymentAccount(account: string) {
  return useQuery<AccountBalance>({
    queryKey: paymentKeys.accountOf(account),
    queryFn: () => apiClient.get(`${BASE}/account`, { params: { account_number: account } }).then(r => r.data),
    enabled: !!account,
    retry: false,
  })
}

/** Баланс квартиры для карточки «Адреса»; без лицевого счёта не запрашивается. */
export function useApartmentPayment(apartmentId: number, accountNumber?: string | null) {
  return useQuery<AccountBalance>({
    queryKey: paymentKeys.apartmentOf(apartmentId, accountNumber),
    queryFn: () => apiClient.get(`${BASE}/apartments/${apartmentId}`).then(r => r.data),
    enabled: !!accountNumber,
    staleTime: 0,
    refetchInterval: 60_000,
    retry: false,
  })
}

/** Сброс всех представлений платежей (раздел, карточка квартиры, таблица квартир). */
export function useRefreshPaymentControl() {
  const qc = useQueryClient()
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: paymentKeys.imports }),
      qc.invalidateQueries({ queryKey: paymentKeys.import }),
      qc.invalidateQueries({ queryKey: paymentKeys.account }),
      qc.invalidateQueries({ queryKey: paymentKeys.apartment }),
      // Список квартир в разделе «Адреса» показывает те же суммы — активация
      // импорта обязана обновить и его, иначе таблица останется на старой дате.
      qc.invalidateQueries({ queryKey: paymentKeys.apartmentBalances }),
    ])
  }
}

export interface PaymentImportUpload {
  kind: string
  asOf: string
  source: string
  file: File | null
}

export function useUploadPaymentImport(onUploaded: (report: PaymentImport) => Promise<void> | void) {
  return useMutation({
    mutationFn: async ({ kind, asOf, source, file }: PaymentImportUpload) => {
      const body = new FormData()
      body.append('kind', kind); body.append('as_of', asOf); body.append('source', source.trim())
      if (file) body.append('file', file)
      return (await apiClient.post<PaymentImport>(`${BASE}/imports/preview`, body)).data
    },
    onSuccess: onUploaded,
  })
}

export function useChangePaymentImport(onChanged: () => Promise<void> | void) {
  return useMutation({
    mutationFn: ({ importId, action, reason }: { importId: number | null; action: 'activate' | 'deactivate'; reason: string }) =>
      apiClient.post(`${BASE}/imports/${importId}/${action}`, action === 'deactivate' ? { reason: reason.trim() } : undefined),
    onSuccess: () => onChanged(),
  })
}
