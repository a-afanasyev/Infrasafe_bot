import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import { ELEVATORS_BASE, STALE_MS, cleanParams, elevatorKeys, useApiLang } from './useElevators'
import type {
  ElevatorOccurrence,
  ElevatorOccurrenceCompleteIn,
  ElevatorOccurrenceGenerateIn,
  OccurrenceFilters,
  OccurrenceKind,
} from '../types/elevators'

/**
 * График ТО/освидетельствований: записи одного лифта и общий календарь
 * (`GET /occurrences`), мутации создания/генерации/переноса/отмены/закрытия.
 * Все мутации инвалидируют оба списка + карточку (флаги maintenance_overdue,
 * cert_* пересчитываются на бэке) и сводку. GET'ы несут `lang` (elevator_label).
 */

export function useElevatorOccurrences(elevatorId: number, filters: OccurrenceFilters = {}) {
  const lang = useApiLang()
  return useQuery<ElevatorOccurrence[]>({
    queryKey: ['elevator-occurrences', elevatorId, filters, lang],
    queryFn: () =>
      apiClient
        .get(`${ELEVATORS_BASE}/${elevatorId}/occurrences`, { params: { ...cleanParams(filters), lang } })
        .then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useAllOccurrences(filters: OccurrenceFilters) {
  const lang = useApiLang()
  return useQuery<ElevatorOccurrence[]>({
    queryKey: ['elevators-occurrences', filters, lang],
    queryFn: () =>
      apiClient
        .get(`${ELEVATORS_BASE}/occurrences`, { params: { ...cleanParams(filters), lang } })
        .then((r) => r.data),
    staleTime: STALE_MS,
  })
}

function useOccurrenceInvalidator(elevatorId: number) {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: elevatorKeys.occurrences(elevatorId) })
    queryClient.invalidateQueries({ queryKey: elevatorKeys.allOccurrences })
    queryClient.invalidateQueries({ queryKey: elevatorKeys.detail(elevatorId) })
    queryClient.invalidateQueries({ queryKey: elevatorKeys.list })
    queryClient.invalidateQueries({ queryKey: elevatorKeys.summary })
  }
}

function useOccurrenceMutation<TVars>(
  elevatorId: number,
  mutationFn: (vars: TVars) => Promise<unknown>,
  successKey: string,
) {
  const { t } = useTranslation()
  const invalidate = useOccurrenceInvalidator(elevatorId)
  return useMutation({
    mutationFn,
    onSuccess: () => {
      invalidate()
      toast.success(t(successKey))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useCreateOccurrence(elevatorId: number) {
  return useOccurrenceMutation(
    elevatorId,
    (vars: { kind: OccurrenceKind; due_on: string }) =>
      apiClient.post(`${ELEVATORS_BASE}/${elevatorId}/occurrences`, vars).then((r) => r.data),
    'elevators.toast.occurrenceCreated',
  )
}

export function useGenerateOccurrences(elevatorId: number) {
  return useOccurrenceMutation(
    elevatorId,
    (vars: ElevatorOccurrenceGenerateIn) =>
      apiClient
        .post(`${ELEVATORS_BASE}/${elevatorId}/occurrences/generate`, vars)
        .then((r) => r.data as ElevatorOccurrence[]),
    'elevators.toast.generated',
  )
}

export function useRescheduleOccurrence(elevatorId: number) {
  return useOccurrenceMutation(
    elevatorId,
    (vars: { id: number; due_on: string }) =>
      apiClient
        .patch(`${ELEVATORS_BASE}/occurrences/${vars.id}`, { due_on: vars.due_on })
        .then((r) => r.data),
    'elevators.toast.rescheduled',
  )
}

export function useCancelOccurrence(elevatorId: number) {
  return useOccurrenceMutation(
    elevatorId,
    (occurrenceId: number) =>
      apiClient.post(`${ELEVATORS_BASE}/occurrences/${occurrenceId}/cancel`).then((r) => r.data),
    'elevators.toast.cancelled',
  )
}

export function useCompleteOccurrence(elevatorId: number) {
  return useOccurrenceMutation(
    elevatorId,
    (vars: { id: number } & ElevatorOccurrenceCompleteIn) => {
      const { id, ...payload } = vars
      return apiClient
        .post(`${ELEVATORS_BASE}/occurrences/${id}/complete`, payload)
        .then((r) => r.data)
    },
    'elevators.toast.completed',
  )
}
