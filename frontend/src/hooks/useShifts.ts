import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'

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
  start_time: string  // ISO UTC
  end_time: string | null
  max_requests: number
  current_request_count: number
  load_percentage: number
}

export interface ShiftDetail extends ShiftBrief {
  notes: string | null
  specialization_focus: string[] | null
  coverage_areas: string[] | null
  priority_level: number
  completed_requests: number
  efficiency_score: number | null
  quality_rating: number | null
  template_id: number | null
  created_at: string | null
}

export interface TransferOut {
  id: number
  shift_id: number
  from_executor_name: string | null
  to_executor_name: string | null
  status: string
  reason: string
  urgency_level: string
  comment: string | null
  created_at: string
}

export interface ShiftStatsOut {
  active_shifts: number
  active_executors: number
  coverage_pct: number
  avg_efficiency: number | null
  shifts_today: number
  pending_transfers: number
}

export interface TemplateBrief {
  id: number
  name: string
  description: string | null
  start_hour: number
  start_minute: number
  duration_hours: number
  default_shift_type: string
  days_of_week: number[] | null
  is_active: boolean
  min_executors: number
  max_executors: number
  auto_create: boolean
  required_specializations: string[] | null
  default_max_requests: number
  priority_level: number
}

export function useShifts(filters: Record<string, string | undefined> = {}) {
  const queryClient = useQueryClient()
  useWebSocket('shifts', (event) => {
    if (typeof event.type === 'string' && event.type.startsWith('shift.')) {
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
    }
  })
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
  const queryClient = useQueryClient()
  useWebSocket('shifts', (event) => {
    if (typeof event.type === 'string' && event.type.startsWith('transfer.')) {
      queryClient.invalidateQueries({ queryKey: ['shift-transfers'] })
    }
  })
  return useQuery<TransferOut[]>({
    queryKey: ['shift-transfers'],
    queryFn: () => apiClient.get('/api/v2/shifts/transfers').then(r => r.data),
    staleTime: 30_000,
  })
}

export function useShiftStats(period: string = '7d') {
  return useQuery<ShiftStatsOut>({
    queryKey: ['shift-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/shifts/stats', { params: { period } }).then(r => r.data),
    staleTime: 30_000,
  })
}

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
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
    },
  })
}

export function useEndShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/api/v2/shifts/${id}/end`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
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
      queryClient.invalidateQueries({ queryKey: ['shift-transfers'] })
      queryClient.invalidateQueries({ queryKey: ['shift-stats'] })
    },
  })
}

export function useEmployees() {
  return useQuery<EmployeeBrief[]>({
    queryKey: ['shift-employees'],
    queryFn: () => apiClient.get('/api/v2/shifts/employees').then(r => r.data),
    staleTime: 60_000,
  })
}
