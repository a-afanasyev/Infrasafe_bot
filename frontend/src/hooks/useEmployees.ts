import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../api/client'
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

export function useApproveEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/approve`).then(r => r.data),
    onSuccess: () => {
      toast.success('Сотрудник одобрен')
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: Error) => {
      console.error('Approve employee failed:', error)
      toast.error('Не удалось одобрить сотрудника', { description: error.message })
    },
  })
}

export function useRejectEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/reject`).then(r => r.data),
    onSuccess: () => {
      toast.success('Сотрудник отклонён')
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: Error) => {
      console.error('Reject employee failed:', error)
      toast.error('Не удалось отклонить сотрудника', { description: error.message })
    },
  })
}

export function useBlockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/block`).then(r => r.data),
    onSuccess: () => {
      toast.success('Сотрудник заблокирован')
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: Error) => {
      console.error('Block employee failed:', error)
      toast.error('Не удалось заблокировать сотрудника', { description: error.message })
    },
  })
}

export function useUnblockEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/unblock`).then(r => r.data),
    onSuccess: () => {
      toast.success('Сотрудник разблокирован')
      queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (error: Error) => {
      console.error('Unblock employee failed:', error)
      toast.error('Не удалось разблокировать сотрудника', { description: error.message })
    },
  })
}
