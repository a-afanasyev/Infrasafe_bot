import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

export interface EmployeeBrief {
  id: number
  first_name: string | null
  last_name: string | null
  phone: string | null
  specialization: string[]
  active_shift_id: number | null
  verification_status: string
}

export interface ShiftBrief {
  id: number
  user_id: number | null
  executor_name: string | null
  status: string
  shift_type: string | null
  start_time: string
  end_time: string | null
  max_requests: number
  current_request_count: number
  load_percentage: number
}

export interface EmployeeDetail extends EmployeeBrief {
  active_shift: ShiftBrief | null
  rating: number | null
  total_shifts: number
  total_completed: number
}

export function useEmployees(filters: Record<string, string | boolean | undefined> = {}) {
  return useQuery<EmployeeBrief[]>({
    queryKey: ['employees', filters],
    queryFn: () =>
      apiClient
        .get('/api/v2/shifts/employees', { params: { limit: 50, offset: 0, ...filters } })
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
