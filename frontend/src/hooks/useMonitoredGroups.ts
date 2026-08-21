import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { isAxiosError } from 'axios'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'

export type MonitoredGroupKind = 'residents' | 'staff'

export interface MonitoredGroup {
  id: number
  chat_id: number
  title?: string | null
  kind: MonitoredGroupKind
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface MonitoredGroupListResponse {
  items: MonitoredGroup[]
  total: number
}

export interface MonitoredGroupCreateBody {
  chat_id: number
  title?: string
  kind: MonitoredGroupKind
}

export interface MonitoredGroupUpdateBody {
  is_active?: boolean
  title?: string
  kind?: MonitoredGroupKind
}

const QUERY_KEY = ['monitored-groups']

export function useMonitoredGroups() {
  return useQuery<MonitoredGroupListResponse>({
    queryKey: QUERY_KEY,
    queryFn: () => apiClient.get('/api/v2/monitored-groups').then((r) => r.data),
    staleTime: 30_000,
  })
}

export function useCreateMonitoredGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: MonitoredGroupCreateBody) =>
      apiClient.post('/api/v2/monitored-groups', body).then((r) => r.data),
    onSuccess: () => {
      toast.success(i18n.t('groups.added'))
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (error: unknown) => {
      // 409 — дубль chat_id: отдельное человеческое сообщение вместо сырого detail
      const duplicate = isAxiosError(error) && error.response?.status === 409
      toast.error(
        i18n.t(duplicate ? 'groups.duplicate' : 'groups.addFailed'),
        duplicate ? undefined : { description: safeErrorMessage(error, 'Error') },
      )
    },
  })
}

export function useUpdateMonitoredGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: MonitoredGroupUpdateBody }) =>
      apiClient.patch(`/api/v2/monitored-groups/${id}`, body).then((r) => r.data),
    onSuccess: () => {
      toast.success(i18n.t('groups.updated'))
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('groups.updateFailed'), {
        description: safeErrorMessage(error, 'Error'),
      })
    },
  })
}

export function useDeleteMonitoredGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/v2/monitored-groups/${id}`),
    onSuccess: () => {
      toast.success(i18n.t('groups.deleted'))
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('groups.deleteFailed'), {
        description: safeErrorMessage(error, 'Error'),
      })
    },
  })
}
