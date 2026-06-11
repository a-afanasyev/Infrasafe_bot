import { useCallback } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'
import i18n from '../i18n'
import { safeErrorMessage } from '@/utils/errorMessage'
import type {
  EmployeeBrief,
  ShiftBrief,
  ShiftDetail,
  TransferOut,
  ShiftStatsOut,
  TemplateBrief,
} from '../types/api'

export type {
  EmployeeBrief,
  ShiftBrief,
  ShiftDetail,
  TransferOut,
  ShiftStatsOut,
  TemplateBrief,
}

export function useShifts(filters: Record<string, string | undefined> = {}) {
  return useQuery<ShiftBrief[]>({
    queryKey: ['shifts', filters],
    queryFn: () => apiClient.get('/api/v2/shifts', { params: filters }).then(r => r.data),
    staleTime: 30_000,
  })
}

export function useShift(id: number | null) {
  return useQuery<ShiftDetail>({
    queryKey: ['shift', id],
    queryFn: () => apiClient.get(`/api/v2/shifts/${id}`).then(r => r.data),
    enabled: id !== null,
  })
}

export function useShiftSchedule(dateFrom: string, dateTo: string) {
  return useQuery<ShiftBrief[]>({
    queryKey: ['shift-schedule', dateFrom, dateTo],
    queryFn: () =>
      apiClient
        .get('/api/v2/shifts/schedule', { params: { date_from: dateFrom, date_to: dateTo } })
        .then(r => r.data),
    staleTime: 30_000,
  })
}

export function useShiftTransfers() {
  return useQuery<TransferOut[]>({
    queryKey: ['shift-transfers'],
    queryFn: () => apiClient.get('/api/v2/shifts/transfers').then(r => r.data),
    staleTime: 30_000,
  })
}

// FE-02: единственная реализация useShiftStats живёт в useAnalytics.ts.
// Здесь был дубль на тот же queryKey ['shift-stats', period] с другими
// опциями (без keepPreviousData) — два хука делили кэш и конфликтовали.
export { useShiftStats } from './useAnalytics'

export function useShiftTemplates() {
  return useQuery<TemplateBrief[]>({
    queryKey: ['shift-templates'],
    queryFn: () => apiClient.get('/api/v2/shifts/templates').then(r => r.data),
    staleTime: 60_000,
  })
}

export function useCreateShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: object) =>
      apiClient.post('/api/v2/shifts', body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.shiftCreated'))
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('toast.shiftCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUpdateShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
      apiClient.patch(`/api/v2/shifts/${id}`, body).then(r => r.data),
    onSuccess: (_, variables) => {
      toast.success(i18n.t('toast.shiftUpdated'))
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
      queryClient.invalidateQueries({ queryKey: ['shift', variables.id] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('toast.shiftUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/shifts/${id}`).then(r => r.data),
    onSuccess: (_, id) => {
      toast.success(i18n.t('toast.shiftDeleted'))
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
      queryClient.removeQueries({ queryKey: ['shift', id] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('toast.shiftDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useEndShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/api/v2/shifts/${id}/end`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.shiftEnded'))
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('toast.shiftEndFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useHandleTransfer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      action,
      to_executor_id,
    }: {
      id: number
      action: string
      to_executor_id?: number
    }) =>
      apiClient
        .post(`/api/v2/shifts/transfers/${id}/handle`, { action, to_executor_id })
        .then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.transferHandled'))
      queryClient.invalidateQueries({ queryKey: ['shift-transfers'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('toast.transferHandleFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useShiftsWebSocket() {
  const queryClient = useQueryClient()
  const onEvent = useCallback((event: { type: string; data: unknown }) => {
    if (typeof event.type === 'string') {
      if (event.type.startsWith('shift.') || event.type === 'shift_created' || event.type === 'shift_updated' || event.type === 'shift_ended') {
        queryClient.invalidateQueries({ queryKey: ['shifts'] })
        queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
        queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
      }
      if (event.type.startsWith('transfer.') || event.type === 'transfer_created' || event.type === 'transfer_updated') {
        queryClient.invalidateQueries({ queryKey: ['shift-transfers'] })
      }
    }
  }, [queryClient])
  useWebSocket('shifts', onEvent)
}

export { useEmployees } from './useEmployees'
