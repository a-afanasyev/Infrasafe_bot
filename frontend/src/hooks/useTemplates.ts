import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { TemplateBrief, CreateTemplatePayload } from '../types/api'

export type { TemplateBrief, CreateTemplatePayload }

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
    mutationFn: (body: CreateTemplatePayload) =>
      apiClient.post('/api/v2/shifts/templates', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
    },
    onError: (error) => console.error('Create template failed:', error),
  })
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
      apiClient.patch(`/api/v2/shifts/templates/${id}`, body).then(r => r.data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
      queryClient.invalidateQueries({ queryKey: ['shift-template', variables.id] })
    },
    onError: (error) => console.error('Update template failed:', error),
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/shifts/templates/${id}`).then(r => r.data),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
      queryClient.removeQueries({ queryKey: ['shift-template', id] })
    },
    onError: (error) => console.error('Delete template failed:', error),
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
    onError: (error) => console.error('Create shift from template failed:', error),
  })
}
