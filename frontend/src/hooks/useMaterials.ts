import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  CreateAdjustmentPayload,
  CreateIssuePayload,
  CreateMaterialPayload,
  CreateReceiptPayload,
  MaterialCard,
  MaterialsFilters,
  OperationsFilters,
  OperationsPage,
  ProcurementOut,
  RequestMaterialsOut,
  StockRow,
  UpdateMaterialPayload,
} from '../types/materials'

/**
 * React-Query хуки складского учёта материалов (/api/v2/materials).
 * Паттерн useAccessRegistry: READ через useQuery, мутации инвалидируют
 * связанные ключи (остатки/журнал/«на закуп» пересчитываются после операций).
 */

const BASE = '/api/v2/materials'
const STALE_MS = 15_000

function cleanParams<T extends object>(filters: T): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

// ── READ ────────────────────────────────────────────────────────────

export function useMaterials(filters: MaterialsFilters = {}) {
  return useQuery<MaterialCard[]>({
    queryKey: ['materials', filters],
    queryFn: () =>
      apiClient.get(BASE, { params: cleanParams(filters) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useMaterialsStock(params: { q?: string; only_low?: boolean } = {}) {
  return useQuery<StockRow[]>({
    queryKey: ['materials-stock', params],
    queryFn: () =>
      apiClient.get(`${BASE}/stock`, { params: cleanParams(params) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useMaterialOperations(filters: OperationsFilters = {}) {
  return useQuery<OperationsPage>({
    queryKey: ['materials-operations', filters],
    queryFn: () =>
      apiClient
        .get(`${BASE}/operations`, { params: cleanParams(filters) })
        .then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useRequestMaterials(requestNumber: string | null) {
  return useQuery<RequestMaterialsOut>({
    queryKey: ['request-materials', requestNumber],
    queryFn: () =>
      apiClient.get(`${BASE}/by-request/${requestNumber}`).then((r) => r.data),
    enabled: requestNumber !== null && requestNumber !== '',
    staleTime: STALE_MS,
  })
}

export function useProcurement() {
  return useQuery<ProcurementOut>({
    queryKey: ['materials-procurement'],
    queryFn: () => apiClient.get(`${BASE}/procurement`).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

// ── CSV (fetch-blob + скачивание, cookie-auth сохраняется) ─────────

async function downloadCsv(url: string, params: Record<string, unknown>, filename: string) {
  const resp = await apiClient.get(url, { params, responseType: 'blob' })
  const href = URL.createObjectURL(resp.data as Blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}

export function exportOperationsCsv(filters: OperationsFilters) {
  return downloadCsv(
    `${BASE}/operations/export`,
    cleanParams(filters),
    'material_operations.csv',
  )
}

export function exportProcurementCsv() {
  return downloadCsv(`${BASE}/procurement/export`, {}, 'material_procurement.csv')
}

// ── MUTATIONS ───────────────────────────────────────────────────────

function useMaterialsInvalidator() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['materials'] })
    queryClient.invalidateQueries({ queryKey: ['materials-stock'] })
    queryClient.invalidateQueries({ queryKey: ['materials-operations'] })
    queryClient.invalidateQueries({ queryKey: ['materials-procurement'] })
    queryClient.invalidateQueries({ queryKey: ['request-materials'] })
  }
}

export function useCreateMaterial() {
  const { t } = useTranslation()
  const invalidate = useMaterialsInvalidator()
  return useMutation({
    mutationFn: (payload: CreateMaterialPayload) =>
      apiClient.post(BASE, payload).then((r) => r.data as MaterialCard),
    onSuccess: () => {
      invalidate()
      toast.success(t('materials.toast.created'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useUpdateMaterial() {
  const { t } = useTranslation()
  const invalidate = useMaterialsInvalidator()
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateMaterialPayload & { id: number }) =>
      apiClient.patch(`${BASE}/${id}`, payload).then((r) => r.data as MaterialCard),
    onSuccess: () => {
      invalidate()
      toast.success(t('materials.toast.updated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useCreateReceipt() {
  const { t } = useTranslation()
  const invalidate = useMaterialsInvalidator()
  return useMutation({
    mutationFn: (payload: CreateReceiptPayload) =>
      apiClient.post(`${BASE}/receipts`, payload).then((r) => r.data),
    onSuccess: () => {
      invalidate()
      toast.success(t('materials.toast.receiptCreated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useCreateIssue() {
  const { t } = useTranslation()
  const invalidate = useMaterialsInvalidator()
  return useMutation({
    mutationFn: (payload: CreateIssuePayload) =>
      apiClient.post(`${BASE}/issues`, payload).then((r) => r.data),
    onSuccess: () => {
      invalidate()
      toast.success(t('materials.toast.issueCreated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useCreateAdjustment() {
  const { t } = useTranslation()
  const invalidate = useMaterialsInvalidator()
  return useMutation({
    mutationFn: (payload: CreateAdjustmentPayload) =>
      apiClient.post(`${BASE}/adjustments`, payload).then((r) => r.data),
    onSuccess: () => {
      invalidate()
      toast.success(t('materials.toast.adjustmentCreated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
