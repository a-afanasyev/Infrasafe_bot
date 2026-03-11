import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['employees'] }),
    onError: (error) => console.error('Approve employee failed:', error),
  })
}

export function useRejectEmployee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.patch(`/api/v2/shifts/employees/${id}/reject`).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['employees'] }),
    onError: (error) => console.error('Reject employee failed:', error),
  })
}
