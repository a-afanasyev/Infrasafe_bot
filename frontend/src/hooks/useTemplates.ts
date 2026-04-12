import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../api/client'
import i18n from '../i18n'
import { safeErrorMessage } from '@/utils/errorMessage'
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
      toast.success(i18n.t('toast.templateCreated'))
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
    },
    onError: (error: unknown) => {
      console.error('Create template failed:', error)
      toast.error(i18n.t('toast.templateCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
      apiClient.patch(`/api/v2/shifts/templates/${id}`, body).then(r => r.data),
    onSuccess: (_, variables) => {
      toast.success(i18n.t('toast.templateUpdated'))
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
      queryClient.invalidateQueries({ queryKey: ['shift-template', variables.id] })
    },
    onError: (error: unknown) => {
      console.error('Update template failed:', error)
      toast.error(i18n.t('toast.templateUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/shifts/templates/${id}`).then(r => r.data),
    onSuccess: (_, id) => {
      toast.success(i18n.t('toast.templateDeleted'))
      queryClient.invalidateQueries({ queryKey: ['shift-templates'] })
      queryClient.removeQueries({ queryKey: ['shift-template', id] })
    },
    onError: (error: unknown) => {
      console.error('Delete template failed:', error)
      toast.error(i18n.t('toast.templateDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useCreateShiftFromTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { template_id: number; date: string }) =>
      apiClient.post('/api/v2/shifts/from-template', body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.shiftFromTemplate'))
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      queryClient.invalidateQueries({ queryKey: ['shift-schedule'] })
    },
    onError: (error: unknown) => {
      console.error('Create shift from template failed:', error)
      toast.error(i18n.t('toast.shiftFromTemplateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}
