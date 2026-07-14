import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'
import type {
  VerificationStatus,
  EmployeeBrief,
  ShiftBrief,
  EmployeeDetail,
} from '../types/api'

export type { VerificationStatus, EmployeeBrief, ShiftBrief, EmployeeDetail }

export function useEmployees(
  filters: Record<string, string | boolean | undefined> = {},
  search?: string,
) {
  return useQuery<EmployeeBrief[]>({
    queryKey: ['employees', filters, search],
    queryFn: () =>
      apiClient
        .get('/api/v2/shifts/employees', {
          params: {
            limit: 50,
            offset: 0,
            ...filters,
            ...(search ? { search } : {}),
          },
        })
        .then(r => r.data),
    staleTime: 30_000,
  })
}

export function useEmployee(id: number | null) {
  return useQuery<EmployeeDetail>({
    queryKey: ['employee', id],
    queryFn: () => apiClient.get(`/api/v2/shifts/employees/${id}`).then(r => r.data),
    enabled: id !== null,
  })
}

/** Сотрудники (менеджеры/исполнители) со status='pending' — очередь активации. */
export function usePendingStaff() {
  return useQuery<EmployeeBrief[]>({
    queryKey: ['pending-staff'],
    queryFn: () => apiClient.get('/api/v2/shifts/employees/pending').then(r => r.data),
    staleTime: 30_000,
  })
}

export function useApproveEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/approve`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeApproved'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Approve employee failed:', error)
      toast.error(i18n.t('toast.employeeApproveFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

/** Выдать/снять роль контролёра показаний (resource_meter_entry) — капабилити
 *  для Mini App «Ввод показаний» в «Учёте ресурсов». */
export function useToggleMeterEntry(employeeId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      apiClient
        .patch(`/api/v2/shifts/employees/${employeeId}/meter-entry`, { enabled })
        .then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.meterEntryUpdated'))
      queryClient.invalidateQueries({ queryKey: ['employee', employeeId] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Toggle meter-entry failed:', error)
      toast.error(i18n.t('toast.meterEntryFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useRejectEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/reject`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeRejected'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Reject employee failed:', error)
      toast.error(i18n.t('toast.employeeRejectFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useBlockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/block`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeBlocked'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Block employee failed:', error)
      toast.error(i18n.t('toast.employeeBlockFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUnblockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/unblock`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeUnblocked'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Unblock employee failed:', error)
      toast.error(i18n.t('toast.employeeUnblockFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useActiveRequestsCount(userId: number | null) {
  return useQuery<{ count: number }>({
    queryKey: ['active-requests-count', userId],
    queryFn: () =>
      apiClient
        .get(`/api/v2/shifts/employees/${userId}/active-requests-count`)
        .then(r => r.data),
    enabled: userId !== null,
  })
}

/** Активировать pending-стафф аккаунт (status→approved). Допускает менеджеров. */
export function useActivateEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/activate`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeApproved'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      queryClient.invalidateQueries({ queryKey: ['pending-staff'] })
    },
    onError: (error: unknown) => {
      console.error('Activate employee failed:', error)
      toast.error(i18n.t('toast.employeeApproveFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

/** Отклонить pending-стафф заявку (status→blocked). */
export function useDeclineEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/decline`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeRejected'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      queryClient.invalidateQueries({ queryKey: ['pending-staff'] })
    },
    onError: (error: unknown) => {
      console.error('Decline employee failed:', error)
      toast.error(i18n.t('toast.employeeRejectFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useCreateInvite() {
  return useMutation({
    mutationFn: (data: {
      role: string
      specializations: string[]
      hours: number
    }) =>
      apiClient
        .post('/api/v2/shifts/employees/invite', data)
        .then(r => r.data as { token: string; bot_link: string; expires_at: string }),
    onError: (error: unknown) => {
      console.error('Create invite failed:', error)
      toast.error(i18n.t('toast.inviteCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason, reassign_to }: { id: number; reason: string; reassign_to?: number }) =>
      apiClient
        .patch(`/api/v2/shifts/employees/${id}/delete`, { reason, reassign_to })
        .then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.employeeDeleted'))
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: unknown) => {
      console.error('Delete employee failed:', error)
      toast.error(i18n.t('toast.employeeDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}
