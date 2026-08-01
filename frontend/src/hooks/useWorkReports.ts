import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  WorkReport,
  WorkReportListOut,
  WorkReportCreatePayload,
  WorkReportPatchPayload,
  WorkReportsSettingsPayload,
} from '../types/workReports'
import type { WorkReportsCfg } from '../types/boardConfig'

/**
 * React-Query хуки менеджерского API визуальных отчётов «до/после»
 * (/api/v2/work-reports, T7). Паттерн useMaterials: READ через useQuery,
 * мутации инвалидируют связанные ключи через onSuccess.
 *
 * НЕТ отдельного read-хука настроек (`GET /work-reports/settings` не
 * существует на бэкенде) — текущие настройки читаются через уже существующий
 * useBoardConfig()'s `data.work_reports` (board_config уже отдаёт этот блок).
 * useUpdateWorkReportsSettings ниже — только запись, и инвалидирует
 * ['board-config'] (не ['work-reports']) — именно этот кэш реально держит
 * то, что читает useBoardConfig().
 */

const BASE = '/api/v2/work-reports'
const STALE_MS = 15_000

// ── READ ────────────────────────────────────────────────────────────

export function useWorkReports(
  params: { status?: string | string[]; limit?: number; offset?: number } = {},
) {
  return useQuery<WorkReportListOut>({
    queryKey: ['work-reports', params],
    queryFn: () => {
      // AUD6-P2-08: статус может быть списком; бэкенд ждёт повторяемый ключ
      // (?status=a&status=b), а дефолтная axios-сериализация массивов даёт
      // несовместимый `status[]=` — собираем строку сами.
      const search = new URLSearchParams()
      const statuses = Array.isArray(params.status)
        ? params.status
        : params.status
          ? [params.status]
          : []
      for (const s of statuses) search.append('status', s)
      if (params.limit !== undefined) search.set('limit', String(params.limit))
      if (params.offset !== undefined) search.set('offset', String(params.offset))
      const qs = search.toString()
      return apiClient.get(qs ? `${BASE}?${qs}` : BASE).then((r) => r.data)
    },
    staleTime: STALE_MS,
  })
}

// ── MUTATIONS ───────────────────────────────────────────────────────

function useWorkReportsInvalidator() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['work-reports'] })
}

export function useSyncWorkReports() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: () => apiClient.post(`${BASE}/sync`).then((r) => r.data),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.synced'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useCreateWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: (payload: WorkReportCreatePayload) =>
      apiClient.post(BASE, payload).then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.created'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

// Фоновая/техническая операция — без success-тоста, только инвалидация +
// error-тост.
export function useAutofillWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`${BASE}/${id}/autofill`).then((r) => r.data as WorkReport),
    onSuccess: () => invalidate(),
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function usePatchWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: ({ id, ...payload }: WorkReportPatchPayload & { id: number }) =>
      apiClient.patch(`${BASE}/${id}`, payload).then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.updated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function usePublishWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`${BASE}/${id}/publish`).then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.published'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useUnpublishWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      apiClient
        .post(`${BASE}/${id}/unpublish`, { reason })
        .then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.unpublished'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useRejectWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiClient
        .post(`${BASE}/${id}/reject`, { reason })
        .then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.rejected'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useReopenWorkReport() {
  const { t } = useTranslation()
  const invalidate = useWorkReportsInvalidator()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`${BASE}/${id}/reopen`).then((r) => r.data as WorkReport),
    onSuccess: () => {
      invalidate()
      toast.success(t('workReports.toast.reopened'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

// Инвалидирует ['board-config'], НЕ ['work-reports'] — это PUT-эндпоинт
// пишет в board_config.work_reports, и именно ['board-config'] — ключ,
// который читает useBoardConfig() (единственный read-хук для этих настроек,
// см. заголовок файла).
export function useUpdateWorkReportsSettings() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: WorkReportsSettingsPayload) =>
      apiClient.put(`${BASE}/settings`, payload).then((r) => r.data as WorkReportsCfg),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board-config'] })
      toast.success(t('workReports.toast.settingsUpdated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
