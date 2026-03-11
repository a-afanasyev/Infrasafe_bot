import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'

export interface TemplateBrief {
  id: number
  name: string
  description: string | null
  start_hour: number
  start_minute: number
  duration_hours: number
  default_shift_type: string
  days_of_week: number[] | null  // 0=Mon ... 6=Sun
  is_active: boolean
  min_executors: number
  max_executors: number
  auto_create: boolean
  required_specializations: string[] | null
  default_max_requests: number
  priority_level: number
}

export function useTemplates() {
  return useQuery<TemplateBrief[]>({
    queryKey: ['shift-templates'],
    queryFn: () =>
      apiClient
        .get('/api/v2/shifts/templates', { params: { limit: 50 } })
        .then(r => r.data),
    staleTime: 60_000,
  })
}

export function useTemplate(id: number | null) {
  return useQuery<TemplateBrief>({
    queryKey: ['shift-template', id],
    queryFn: () =>
      apiClient.get(`/api/v2/shifts/templates/${id}`).then(r => r.data),
    enabled: id !== null,
    staleTime: 60_000,
  })
}

export function useCreateTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: object) =>
      apiClient.post('/api/v2/shifts/templates', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
    },
  })
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
      apiClient.patch(`/api/v2/shifts/templates/${id}`, body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
    },
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/shifts/templates/${id}`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
    },
  })
}

export function useCreateShiftFromTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { template_id: number; date: string }) =>
      apiClient.post('/api/v2/shifts/from-template', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
    },
  })
}
