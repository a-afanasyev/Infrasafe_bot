import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  ElevatorBulkConfirmItem,
  ElevatorCreateIn,
  ElevatorDetail,
  ElevatorEvent,
  ElevatorListFilters,
  ElevatorListOut,
  ElevatorPatchIn,
  ElevatorRepairIn,
  ElevatorRequestRow,
  ElevatorStatusChangeOut,
  ElevatorStatusIn,
  ElevatorSummary,
} from '../types/elevators'

/**
 * React-Query хуки реестра лифтов (/api/v2/elevators): список, сводка,
 * карточка, журнал, заявки + мутации паспорта/статуса/приёмки. График —
 * `useElevatorCalendar.ts`, конфиг — `useElevatorsConfig.ts`.
 * Паттерн useMaterials: `cleanParams`, инвалидация ключей после мутаций,
 * `toast` + `safeErrorMessage`.
 */

export const ELEVATORS_BASE = '/api/v2/elevators'
const STALE_MS = 15_000
/** FastAPI читает списки как `flag=a&flag=b` (без `[]` axios-дефолта). */
export const REPEAT_PARAMS = { indexes: null } as const

export function cleanParams<T extends object>(filters: T): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v) && v.length === 0) continue
    out[k] = v
  }
  return out
}

export const elevatorKeys = {
  list: ['elevators'] as const,
  summary: ['elevators-summary'] as const,
  detail: (id: number) => ['elevator', id] as const,
  events: (id: number) => ['elevator-events', id] as const,
  requests: (id: number) => ['elevator-requests', id] as const,
  occurrences: (id: number) => ['elevator-occurrences', id] as const,
  allOccurrences: ['elevators-occurrences'] as const,
}

// ── READ ────────────────────────────────────────────────────────────

export function useElevators(filters: ElevatorListFilters = {}, enabled = true) {
  return useQuery<ElevatorListOut>({
    queryKey: ['elevators', filters],
    queryFn: () =>
      apiClient
        .get(ELEVATORS_BASE, { params: cleanParams(filters), paramsSerializer: REPEAT_PARAMS })
        .then((r) => r.data),
    staleTime: STALE_MS,
    enabled,
  })
}

export function useElevatorsSummary() {
  return useQuery<ElevatorSummary>({
    queryKey: ['elevators-summary'],
    queryFn: () => apiClient.get(`${ELEVATORS_BASE}/summary`).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useElevator(id: number | null) {
  return useQuery<ElevatorDetail>({
    queryKey: ['elevator', id],
    queryFn: () => apiClient.get(`${ELEVATORS_BASE}/${id}`).then((r) => r.data),
    enabled: id !== null && Number.isFinite(id),
    staleTime: STALE_MS,
  })
}

export function useElevatorEvents(id: number, limit = 200) {
  return useQuery<ElevatorEvent[]>({
    queryKey: ['elevator-events', id, limit],
    queryFn: () =>
      apiClient.get(`${ELEVATORS_BASE}/${id}/events`, { params: { limit } }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useElevatorRequests(id: number, includeClosed: boolean) {
  return useQuery<ElevatorRequestRow[]>({
    queryKey: ['elevator-requests', id, includeClosed],
    queryFn: () =>
      apiClient
        .get(`${ELEVATORS_BASE}/${id}/requests`, { params: { include_closed: includeClosed } })
        .then((r) => r.data),
    staleTime: STALE_MS,
  })
}

// ── MUTATIONS ───────────────────────────────────────────────────────

function useElevatorInvalidator(id?: number) {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: elevatorKeys.list })
    queryClient.invalidateQueries({ queryKey: elevatorKeys.summary })
    if (id !== undefined) {
      queryClient.invalidateQueries({ queryKey: elevatorKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: elevatorKeys.events(id) })
    }
  }
}

function useErrorToast() {
  const { t } = useTranslation()
  return (err: unknown) => toast.error(safeErrorMessage(err, t('common.error')))
}

export function useCreateElevator() {
  const { t } = useTranslation()
  const invalidate = useElevatorInvalidator()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (payload: ElevatorCreateIn) =>
      apiClient.post(ELEVATORS_BASE, payload).then((r) => r.data as ElevatorDetail),
    onSuccess: () => {
      invalidate()
      toast.success(t('elevators.toast.created'))
    },
    onError,
  })
}

/** PATCH с `expected_version`: 409 = карточку изменил кто-то другой. */
export function usePatchElevator(id: number) {
  const { t } = useTranslation()
  const invalidate = useElevatorInvalidator(id)
  return useMutation({
    mutationFn: (payload: ElevatorPatchIn) =>
      apiClient.patch(`${ELEVATORS_BASE}/${id}`, payload).then((r) => r.data as ElevatorDetail),
    onSuccess: () => {
      invalidate()
      toast.success(t('elevators.toast.updated'))
    },
    onError: (err) => {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        toast.error(t('elevators.toast.conflict'))
        return
      }
      toast.error(safeErrorMessage(err, t('common.error')))
    },
  })
}

export function useCommissionElevator(id: number) {
  const { t } = useTranslation()
  const invalidate = useElevatorInvalidator(id)
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (commissionedAt?: string | null) =>
      apiClient
        .post(`${ELEVATORS_BASE}/${id}/commission`, { commissioned_at: commissionedAt ?? null })
        .then((r) => r.data as ElevatorDetail),
    onSuccess: () => {
      invalidate()
      toast.success(t('elevators.toast.commissioned'))
    },
    onError,
  })
}

export function useArchiveElevator(id: number) {
  const { t } = useTranslation()
  const invalidate = useElevatorInvalidator(id)
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (reason: string) =>
      apiClient.post(`${ELEVATORS_BASE}/${id}/archive`, { reason }).then((r) => r.data as ElevatorDetail),
    onSuccess: () => {
      invalidate()
      toast.success(t('elevators.toast.archived'))
    },
    onError,
  })
}

export function useSetElevatorStatus(id: number) {
  const { t } = useTranslation()
  const invalidate = useElevatorInvalidator(id)
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (payload: ElevatorStatusIn) =>
      apiClient
        .put(`${ELEVATORS_BASE}/${id}/status`, payload)
        .then((r) => r.data as ElevatorStatusChangeOut),
    onSuccess: (data) => {
      invalidate()
      toast.success(
        data.changed
          ? t('elevators.toast.statusChanged', { count: data.notified_residents })
          : t('elevators.toast.statusUnchanged'),
      )
    },
    onError,
  })
}

/** Групповая приёмка: per-item результат — показывает вызывающий компонент. */
export function useBulkConfirmRequests(elevatorId: number) {
  const queryClient = useQueryClient()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (requestNumbers: string[]) =>
      apiClient
        .post(`${ELEVATORS_BASE}/requests/bulk-confirm`, { request_numbers: requestNumbers })
        .then((r) => r.data as ElevatorBulkConfirmItem[]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: elevatorKeys.requests(elevatorId) })
      queryClient.invalidateQueries({ queryKey: elevatorKeys.list })
      queryClient.invalidateQueries({ queryKey: elevatorKeys.summary })
    },
    onError,
  })
}

/**
 * «Создать ремонт» из карточки — колл-центровый эндпоинт. Поля `elevator_id`,
 * `elevator_operational`, `acceptance_mode` бэкенд начнёт читать в T6; до
 * этого заявка создаётся без привязки к лифту.
 */
export function useCreateElevatorRepair(elevatorId: number) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (payload: ElevatorRepairIn) =>
      apiClient
        .post('/api/v2/callcenter/requests', payload)
        .then((r) => r.data as { request_number?: string }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: elevatorKeys.requests(elevatorId) })
      queryClient.invalidateQueries({ queryKey: elevatorKeys.list })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      toast.success(t('elevators.toast.repairCreated'))
    },
    onError,
  })
}
