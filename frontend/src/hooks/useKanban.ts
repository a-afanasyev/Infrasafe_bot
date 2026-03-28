import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'

export interface RequestCard {
  request_number: string
  status: string
  category: string
  urgency: string | null
  source: string | null
  description: string | null
  address: string | null
  executor_id: number | null
  executor_name: string | null
  notes: string | null
  completion_report: string | null
  requested_materials: string | null
  return_reason: string | null
  created_at: string
  updated_at: string | null
  manager_confirmed: boolean
}

export interface KanbanColumn {
  status: string
  count: number
  requests: RequestCard[]
}

export function useKanban(filters: Record<string, string | undefined> = {}) {
  const queryClient = useQueryClient()

  const { data, isLoading, isError } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['kanban', filters],
    queryFn: () => apiClient.get('/api/v2/requests/kanban', { params: filters }).then((r) => r.data),
    staleTime: 30_000,
  })

  useWebSocket('kanban', (event) => {
    if (['request.created', 'request.status_changed', 'request.assigned', 'request.updated'].includes(event.type)) {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
    }
  })

  return { columns: data?.columns ?? [], isLoading, isError }
}
